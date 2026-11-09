"""Instalación sin formularios de un negocio en pretix (la llama `reservas crear`).

Datos (JSON):
    slug, tipo ("clases" | "salas"), negocio, email, clave, zona, color, web, privacidad, aviso_legal,
    logo (data URI png/jpg/webp), demo (bool), fuente (URL del código fuente publicado),
    vista (opcional): «week», «calendar» o «list», la vista de la agenda (clases: semana, si no se dice otra),
    portada (opcional): el texto de arriba de la página de reservas, si no vale el de su tipo,
    clases:  servicios: [{nombre, precio, descripcion, plazas, duracion (min), dias [0=lunes…], hora "HH:MM"}]
             bonos (opcional): [{nombre, precio, usos, meses, descripcion, servicios: [comienzos de nombre]}]
             Cada bono se vende en su propia agenda «bonos» (sin fechas) y da una membresía de pretix con
             `usos` usos y `meses` de validez; en cada sesión de los servicios que cubre (los que empiezan
             por alguno de `servicios`) se añade «<servicio> con bono», a 0 €, que exige esa membresía.
             El cliente necesita cuenta (se activan las cuentas de cliente del negocio).
             cuenta_prueba (solo demos): {email, clave}: cuenta de cliente con un bono de cada tipo, para
             probar la reserva con bono sin comprarlo (en las demos no sale ningún correo).
             matriculas (opcional): [{nombre, periodo: "trimestre" | "intensivo", precio, plazas, descripcion}]
             La matrícula de un grupo para todo un periodo, en su propia agenda «matriculas»: una sesión por
             grupo y periodo (el próximo trimestre: enero-marzo, abril-junio u octubre-diciembre; el intensivo,
             el próximo julio), con «plazas» de cupo. Se paga en el local, como las clases.
    salas:   horario: {dias, desde "HH:MM", hasta "HH:MM", minutos, nombre (opcional, el de cada franja: «Pista»;
             si no, «Cita»), duracion (opcional: lo que dura cada franja si es menos que el paso: consultas de 45 min
             que empiezan cada hora)}, o una lista de esos tramos (mañana y tarde, otro horario el viernes…)
             recursos: [{nombre, cantidad}]
             servicios: [{nombre, precio, descripcion, usa: [nombres de recursos]}]
             preguntas (opcional): [{texto, opciones: [..], obligatoria, clave, tipo}]: preguntas que hace la reserva,
             para todos los servicios: de elegir una opción («¿Presencial o por videollamada?») o, con tipo «texto»,
             de escribir. Con clave («modalidad», «nota»), la web del negocio la puede dejar contestada:
             /reservas/?…&modalidad=Por videollamada&nota=… (la persona aún puede cambiarla).
             ocupadas (solo demos): fracción de 0 a 1 de recursos de una unidad que salen ya ocupados en cada franja,
             siempre los mismos para la misma franja (más por la tarde, menos por la mañana). Así la demo de un club
             enseña pistas ocupadas sin reservas de verdad, y la limpieza de cada noche no las vacía.
Sin servicios, la agenda se crea vacía y el dueño los da de alta en su panel: no inventamos precios.
"""
import base64
import hashlib
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils.timezone import now
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString

ES = lambda t: LazyI18nString({"es": t})  # noqa: E731
SLUG_EVENTO = {"clases": "clases", "salas": "citas"}
# Correos al cliente: el negocio cobra en su local, así que no hay «pago pendiente» que recordar.
CORREO_RESERVA = """Hola:

tu reserva en {event} está hecha. Te esperamos.

Importe: {total_with_currency}. Lo pagas en el local el día de tu reserva.

Para ver tu reserva, cambiarla o anularla:
{url}

Hasta pronto,
{event}"""
CORREO_GRATIS = """Hola:

tu reserva en {event} está hecha. Te esperamos.

Para ver tu reserva, cambiarla o anularla:
{url}

Hasta pronto,
{event}"""
PORTADA = {
    "clases": "Elige la sesión en el calendario y reserva tu plaza. Te llegará la confirmación por correo y un recordatorio el día antes.",
    "salas": "Elige el día y la hora de tu cita. Te llegará la confirmación por correo y un recordatorio el día antes.",
}


def _hora(t):
    h, m = (int(x) for x in t.split(":"))
    return time(h, m)


def _ocupada(plan, ini, recurso) -> bool:
    """Demo: whether this one-unit resource comes already taken in this slot (same answer every time it's asked)."""
    parte = float(plan.get("ocupadas") or 0)
    if parte <= 0 or int(recurso["cantidad"]) != 1:
        return False
    parte *= 1.5 if ini.hour >= 18 else 0.6 if ini.hour < 12 else 1   # evenings fill up, mornings are quiet
    huella = hashlib.sha256(f"{ini.isoformat()}|{recurso['nombre']}".encode()).digest()
    return huella[0] / 256 < min(parte, 0.9)


def crear_sesiones(ev, plan, semanas=8, desde=None):
    """Crea (sin duplicar) las sesiones o franjas de las próximas semanas según el plan."""
    from pretix.base.models import Item, Quota, SubEvent

    tz = ZoneInfo(ev.settings.timezone)
    hoy = desde or datetime.now(tz).date()
    # The name is an I18n string (not hashable): compare its text.
    existentes = {(d, str(n)) for d, n in ev.subevents.values_list("date_from", "name")}
    items = {str(i.name): i for i in Item.objects.filter(event=ev)}
    nuevas = 0

    def nueva(ini, fin, nombre, cupos):
        nonlocal nuevas
        if ini <= now() or any(d == ini and str(n) == nombre for d, n in existentes):
            return
        se = SubEvent.objects.create(event=ev, name=ES(nombre), date_from=ini, date_to=fin, active=True)
        for nombre_cupo, tam, servicios in cupos:
            q = Quota.objects.create(event=ev, subevent=se, name=nombre_cupo, size=tam)
            q.items.add(*[items[s] for s in servicios if s in items])
        nuevas += 1

    for d in (hoy + timedelta(days=k) for k in range(7 * semanas)):
        if plan["tipo"] == "clases":
            for s in plan.get("servicios", []):
                if d.weekday() in s.get("dias", []):
                    ini = datetime.combine(d, _hora(s["hora"]), tz)
                    nueva(ini, ini + timedelta(minutes=int(s.get("duracion", 60))), s["nombre"],
                          [(s["nombre"], int(s["plazas"]), [s["nombre"]] + plan.get("con_bono", {}).get(s["nombre"], []))])
        else:
            tramos = plan.get("horario") or []
            for h in (tramos if isinstance(tramos, list) else [tramos]):
                if d.weekday() not in h.get("dias", []):
                    continue
                ini, fin_dia = datetime.combine(d, _hora(h["desde"]), tz), datetime.combine(d, _hora(h["hasta"]), tz)
                paso = timedelta(minutes=int(h.get("minutos", 60)))
                dura = timedelta(minutes=int(h.get("duracion") or h.get("minutos", 60)))
                while ini + dura <= fin_dia:
                    cupos = [(r["nombre"], 0 if _ocupada(plan, ini, r) else int(r["cantidad"]),
                              [s["nombre"] for s in plan.get("servicios", []) if r["nombre"] in s.get("usa", [])])
                             for r in plan.get("recursos", [])]
                    nueva(ini, ini + dura, h.get("nombre") or "Cita", cupos)
                    ini += paso
    return nuevas


def _logo(ev, data_uri):
    m = re.match(r"^data:image/(png|jpe?g|webp);base64,(.+)$", data_uri or "", re.S)
    if not m:
        return
    ext = "jpg" if m.group(1).startswith("jp") else m.group(1)
    nombre = default_storage.save(f"pub/{ev.organizer.slug}/{ev.slug}/logo.{ext}", ContentFile(base64.b64decode(m.group(2))))
    ev.settings.set("logo_image", "file://" + nombre)


PORTADA_BONOS = ("Compra aquí tu bono. Lo pagas en {negocio} y, desde ese momento, reservas tus clases con tu "
                 "cuenta: cada clase descuenta un uso.")


PORTADA_MATRICULAS = ("Reserva tu plaza en el grupo para todo el periodo. La matrícula la pagas en {negocio} el primer "
                      "día de clase.")
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
         "diciembre"]


def _periodo(tipo: str, hoy: date) -> tuple[date, date, str]:
    """The next term (January-March, April-June, October-December) or the next July intensive, from today."""
    if tipo == "intensivo":
        y = hoy.year if hoy < date(hoy.year, 7, 1) else hoy.year + 1
        return date(y, 7, 1), date(y, 7, 31), f"julio de {y}"
    for y in (hoy.year, hoy.year + 1):
        for m_ini, m_fin, fin in ((1, 3, 31), (4, 6, 30), (10, 12, 20)):
            ini = date(y, m_ini, 1)
            if ini > hoy:
                return ini, date(y, m_fin, fin), f"{MESES[m_ini - 1]} a {MESES[m_fin - 1]} de {y}"
    raise ValueError("sin periodo")


def crear_matriculas(em, entradas, hoy=None) -> int:
    """The enrolment sessions of each group for its next period (without duplicates), in the «matriculas» event."""
    from pretix.base.models import Item, Quota, SubEvent

    tz = ZoneInfo(em.settings.timezone)
    hoy = hoy or datetime.now(tz).date()
    items = {str(i.name): i for i in Item.objects.filter(event=em)}
    existentes = {str(n) for n in em.subevents.values_list("name", flat=True)}
    nuevas = 0
    for m in entradas:
        ini, fin, etiqueta = _periodo(m.get("periodo", "trimestre"), hoy)
        nombre = f"{m['nombre']} · {etiqueta}"
        if nombre in existentes or m["nombre"] not in items:
            continue
        se = SubEvent.objects.create(event=em, name=ES(nombre), active=True,
                                     date_from=datetime.combine(ini, time(9, 0), tz),
                                     date_to=datetime.combine(fin, time(21, 0), tz),
                                     presale_end=datetime.combine(fin, time(12, 0), tz))
        q = Quota.objects.create(event=em, subevent=se, name=m["nombre"], size=int(m["plazas"]))
        q.items.add(items[m["nombre"]])
        nuevas += 1
    return nuevas


def _matriculas(o, ev, d) -> int:
    """Group enrolments for a whole term or the summer intensive (academies): their own event, like the passes."""
    from pretix.base.models import Event, Item

    em = Event.objects.filter(organizer=o, slug="matriculas").first()
    if not em:
        em = Event.objects.create(organizer=o, slug="matriculas", name=ES(f"Matrículas de {d['negocio']}"), currency="EUR",
                                  date_from=now(), has_subevents=True, live=False)
        em.set_defaults()
    em.name = ES(f"Matrículas de {d['negocio']}")
    em.testmode = ev.testmode
    for p in ("pretix.plugins.ticketoutputpdf", "pretix.plugins.ticketoutputpassbook"):
        if p in (em.plugins or ""):
            em.disable_plugin(p)
    em.enable_plugin("pretix.plugins.manualpayment")
    em.enable_plugin("pretix_vivawebs")
    for clave in ("locale", "locales", "region", "timezone", "order_phone_asked", "order_phone_required",
                  "invoice_address_asked", "invoice_name_required", "ticket_download",
                  "payment_term_expire_automatically", "payment_pending_hidden", "mail_days_order_expire_warning",
                  "mail_subject_order_placed", "mail_text_order_placed", "mail_subject_order_free",
                  "mail_text_order_free", "cancel_allow_user", "mail_from_name", "contact_mail", "primary_color",
                  "privacy_url", "imprint_url", "payment_manual__enabled", "payment_manual_public_name",
                  "payment_manual_checkout_description", "payment_manual_email_instructions",
                  "payment_manual_pending_description", "meta_noindex", "logo_image", "waiting_list_enabled"):
        if ev.settings.get(clave) is not None:
            em.settings.set(clave, ev.settings.get(clave))
    em.settings.frontpage_text = ES(PORTADA_MATRICULAS.format(negocio=d["negocio"]))
    em.settings.event_list_type = "list"
    em.settings.show_date_to = True
    em.settings.show_times = False
    for n, m in enumerate(d["matriculas"]):
        it, _ = Item.objects.get_or_create(event=em, name=ES(m["nombre"]),
                                           defaults={"default_price": m["precio"], "admission": True})
        it.default_price = m["precio"]
        it.position = n * 10
        if m.get("descripcion"):
            it.description = ES(m["descripcion"])
        it.save()
    nuevas = crear_matriculas(em, d["matriculas"])
    if d.get("demo"):
        em.settings.vw_matriculas = d["matriculas"]   # the demo makes the next period's by itself
    em.live = True
    em.save()
    return nuevas


def _cuenta_prueba(o, tipos, cp) -> None:
    """Demos: a customer with one test-mode pass of each type, so visitors can book with a pass."""
    from pretix.base.models import Customer, Membership

    nombre = {"_scheme": "full", "full_name": "Cliente de prueba"}
    c = Customer.objects.filter(organizer=o, email=cp["email"]).first() or Customer(organizer=o, email=cp["email"])
    c.name_parts = nombre
    c.is_active = True
    c.is_verified = True
    c.locale = "es"
    c.set_password(cp["clave"])
    c.save()
    for mt in tipos:
        m = Membership.objects.filter(customer=c, membership_type=mt, testmode=True).first() or \
            Membership(customer=c, membership_type=mt, testmode=True)
        m.canceled = False
        m.date_start = now() - timedelta(days=1)
        m.date_end = now() + timedelta(days=365 * 5)
        m.attendee_name_parts = nombre
        m.save()
    o.settings.vw_cuenta_prueba = cp["email"]
    o.settings.vw_cuenta_prueba_datos = {"email": cp["email"], "clave": cp["clave"]}


def _bonos(o, ev, d) -> dict:
    """Bonos de clases con las membresías de pretix. Devuelve {servicio: [artículos «con bono»]}."""
    from pretix.base.models import Event, Item, MembershipType, Quota

    o.settings.customer_accounts = True
    o.settings.customer_accounts_native = True
    eb = Event.objects.filter(organizer=o, slug="bonos").first()
    if not eb:
        eb = Event.objects.create(organizer=o, slug="bonos", name=ES(f"Bonos de {d['negocio']}"), currency="EUR",
                                  date_from=now(), has_subevents=False, live=False)
        eb.set_defaults()
    eb.name = ES(f"Bonos de {d['negocio']}")
    eb.testmode = ev.testmode
    for p in ("pretix.plugins.ticketoutputpdf", "pretix.plugins.ticketoutputpassbook"):
        if p in (eb.plugins or ""):
            eb.disable_plugin(p)
    eb.enable_plugin("pretix.plugins.manualpayment")
    eb.enable_plugin("pretix_vivawebs")
    # Same settings as the classes (language, texts, payment at the studio, colour, logo, contact).
    for clave in ("locale", "locales", "region", "timezone", "order_phone_asked", "order_phone_required",
                  "invoice_address_asked", "invoice_name_required", "ticket_download",
                  "payment_term_expire_automatically", "payment_pending_hidden", "mail_days_order_expire_warning",
                  "mail_subject_order_placed", "mail_text_order_placed", "mail_subject_order_free",
                  "mail_text_order_free", "cancel_allow_user", "mail_from_name", "contact_mail", "primary_color",
                  "privacy_url", "imprint_url", "payment_manual__enabled", "payment_manual_public_name",
                  "payment_manual_checkout_description", "payment_manual_email_instructions",
                  "payment_manual_pending_description", "meta_noindex", "logo_image", "vw_recordatorio_horas"):
        if ev.settings.get(clave) is not None:
            eb.settings.set(clave, ev.settings.get(clave))
    eb.settings.frontpage_text = ES(PORTADA_BONOS.format(negocio=d["negocio"]))
    # A shop without dates: no date on the page, no calendar file, and the sale never closes.
    eb.settings.show_dates_on_frontpage = False
    eb.settings.show_date_to = False
    eb.settings.show_times = False
    eb.presale_end = now() + timedelta(days=365 * 20)
    cupo, _ = Quota.objects.get_or_create(event=eb, name="Bonos", defaults={"size": None})
    cupo.size = None
    cupo.save()

    con_bono = {}
    tipos = []
    servicios = [sv["nombre"] for sv in d.get("servicios", [])]
    for b in d["bonos"]:
        # Names are stored as JSON (with escaped characters): compare the text in Python, not in SQL.
        mt = next((m for m in MembershipType.objects.filter(organizer=o) if str(m.name) == b["nombre"]), None)
        if not mt:
            mt = MembershipType(organizer=o, name=ES(b["nombre"]))
        mt.name = ES(b["nombre"])
        mt.max_usages = int(b["usos"])
        mt.transferable = False
        mt.allow_parallel_usage = False
        mt.save()
        tipos.append(mt)
        it, _ = Item.objects.get_or_create(event=eb, name=ES(b["nombre"]), defaults={"default_price": b["precio"]})
        it.default_price = b["precio"]
        it.admission = False
        it.grant_membership_type = mt
        it.grant_membership_duration_like_event = False
        it.grant_membership_duration_months = int(b.get("meses", 4))
        it.grant_membership_duration_days = 0
        if b.get("descripcion"):
            it.description = ES(b["descripcion"])
        it.save()
        cupo.items.add(it)
        for nombre in servicios:
            if not any(nombre.startswith(pref) for pref in b.get("servicios", [])):
                continue
            nb = f"{nombre} con bono"
            ib, _ = Item.objects.get_or_create(event=ev, name=ES(nb), defaults={"default_price": 0, "admission": True})
            ib.default_price = 0
            ib.admission = True
            ib.require_membership = True
            ib.description = ES(f"Con tu {b['nombre'][:1].lower()}{b['nombre'][1:]}: descuenta un uso.")
            base = next((i for i in Item.objects.filter(event=ev) if str(i.name) == nombre), None)
            ib.position = (base.position if base else 0) + 1   # right after the class itself
            ib.save()
            ib.require_membership_types.set([mt])
            con_bono.setdefault(nombre, [])
            if nb not in con_bono[nombre]:
                con_bono[nombre].append(nb)
    # Sessions already created: their quota also takes the pass item.
    for nombre, nbs in con_bono.items():
        items = [i for i in Item.objects.filter(event=ev) if str(i.name) in nbs]
        for q in Quota.objects.filter(event=ev, name=nombre, subevent__date_from__gte=now()):
            q.items.add(*items)
    if d.get("demo") and d.get("cuenta_prueba"):
        _cuenta_prueba(o, tipos, d["cuenta_prueba"])
    eb.live = True
    eb.save()
    return con_bono


def _preguntas(ev, preguntas) -> None:
    """Choice questions the booking asks, for every service (same text: the same question, updated)."""
    from pretix.base.models import Item, Question, QuestionOption
    items = list(Item.objects.filter(event=ev))
    for n, p in enumerate(preguntas):
        tipo_q = Question.TYPE_TEXT if p.get("tipo") == "texto" else Question.TYPE_CHOICE
        q = next((x for x in Question.objects.filter(event=ev) if str(x.question) == p["texto"]), None)
        if not q:
            q = Question.objects.create(event=ev, question=ES(p["texto"]), type=tipo_q)
        if p.get("clave"):
            q.identifier = p["clave"]
        q.required = bool(p.get("obligatoria", True))
        q.position = n
        q.save()
        q.items.set(items)
        tienen = {str(o.answer) for o in q.options.all()}
        for k, texto in enumerate(p.get("opciones", [])):
            if texto not in tienen:
                QuestionOption.objects.create(question=q, answer=ES(texto), position=k)


def configurar(d: dict) -> dict:
    from pretix.base.models import (
        Event, Item, NotificationSetting, Organizer, Team, User,
    )
    from pretix.base.settings import GlobalSettingsObject

    tipo = d["tipo"]
    zona = d.get("zona") or "Atlantic/Canary"
    with scopes_disabled(), transaction.atomic():
        # Instalación: sin envío de datos a pretix y con la declaración de licencia (AGPL, código publicado).
        gs = GlobalSettingsObject().settings
        gs.update_check_perform = False
        gs.update_check_ack = True
        gs.license_check_input = {
            "base_changes": "yes", "usage": "saas", "base_license": "agpl",
            "plugins_free": False, "plugins_copyleft": True, "plugins_own": False, "plugins_enterprise": False,
            "poweredby_name": "VivaWebs", "poweredby_url": "https://vivawebs.com/",
            "source_notice": ("Este servicio de reservas de VivaWebs (Oksigenia S.L.) funciona con pretix, con cambios "
                              "propios. El código fuente completo de lo que se ejecuta, con su licencia (GNU AGPLv3), "
                              f"está en {d.get('fuente', '')}"),
        }
        gs.license_check_completed = now()
        User.objects.filter(email="admin@localhost").delete()   # el administrador de serie, con clave conocida

        o, _ = Organizer.objects.get_or_create(slug=d["slug"], defaults={"name": d["negocio"]})
        o.name = d["negocio"]
        o.save()
        o.settings.locale = "es"
        o.settings.timezone = zona

        ev = Event.objects.filter(organizer=o, slug=SLUG_EVENTO[tipo]).first()
        if not ev:
            ev = Event.objects.create(organizer=o, slug=SLUG_EVENTO[tipo], name=ES(d["negocio"]), currency="EUR",
                                      date_from=now(), has_subevents=True, live=False)
            ev.set_defaults()
        ev.name = ES(d["negocio"])
        ev.testmode = bool(d.get("demo"))
        for p in ("pretix.plugins.ticketoutputpdf", "pretix.plugins.ticketoutputpassbook"):
            if p in (ev.plugins or ""):
                ev.disable_plugin(p)
        ev.enable_plugin("pretix.plugins.manualpayment")
        ev.enable_plugin("pretix_vivawebs")

        s = ev.settings
        s.locale, s.locales, s.region, s.timezone = "es", ["es"], "ES", zona
        s.show_quota_left = True
        s.show_times = True
        s.show_date_to = True
        s.waiting_list_enabled = tipo == "clases"
        # Classes repeat every week: the week reads better than the whole month (the month stays as an option).
        if d.get("vista") or tipo == "clases":
            s.event_list_type = d.get("vista") or "week"
        s.order_phone_asked = True
        s.order_phone_required = True
        s.invoice_address_asked = False
        s.invoice_name_required = True
        s.ticket_download = False
        s.payment_term_expire_automatically = False
        s.payment_pending_hidden = True
        s.mail_days_order_expire_warning = 0   # sin avisos de «pago pendiente»: se paga en el local
        s.mail_subject_order_placed = ES("Tu reserva en {event}: {code}")
        s.mail_text_order_placed = ES(CORREO_RESERVA)
        s.mail_subject_order_free = ES("Tu reserva en {event}: {code}")
        s.mail_text_order_free = ES(CORREO_GRATIS)
        s.cancel_allow_user = True
        s.mail_from_name = d["negocio"]
        s.contact_mail = d.get("email", "")
        if d.get("color"):
            s.primary_color = d["color"]
        for clave, valor in (("privacy_url", d.get("privacidad")), ("imprint_url", d.get("aviso_legal"))):
            if valor:
                s.set(clave, ES(valor))
        portada = d.get("portada") or PORTADA[tipo]   # a business's own words for its booking page
        if tipo == "clases" and d.get("bonos"):
            portada += " ¿Tienes bono? Elige la opción «con bono» de tu clase y entra con tu cuenta."
        s.frontpage_text = ES(portada)
        s.payment_manual__enabled = True
        s.payment_manual_public_name = ES("Pago en el local")
        texto_pago = f"Pagas en {d['negocio']} el día de tu reserva."
        for k in ("payment_manual_checkout_description", "payment_manual_email_instructions",
                  "payment_manual_pending_description"):
            s.set(k, ES(texto_pago))
        s.vw_recordatorio_horas = 0 if d.get("demo") else 24
        if d.get("demo"):
            s.meta_noindex = True
        _logo(ev, d.get("logo"))

        # Servicios: precio y descripción del negocio (vienen en los datos o los pone él en su panel).
        for n, sv in enumerate(d.get("servicios", [])):
            it, _ = Item.objects.get_or_create(event=ev, name=ES(sv["nombre"]),
                                               defaults={"default_price": sv.get("precio") or 0, "admission": True})
            it.default_price = sv.get("precio") or 0
            it.position = n * 10
            if sv.get("descripcion"):
                it.description = ES(sv["descripcion"])
            it.save()
        _preguntas(ev, d.get("preguntas") or [])
        con_bono = _bonos(o, ev, d) if tipo == "clases" and d.get("bonos") else {}
        if tipo == "clases" and d.get("matriculas"):
            _matriculas(o, ev, d)
        plan = {"tipo": tipo, "servicios": d.get("servicios", []), "horario": d.get("horario"),
                "recursos": d.get("recursos", []), "renovar": bool(d.get("demo")), "semanas": 6,
                "ocupadas": d.get("ocupadas", 0) if d.get("demo") else 0,
                "con_bono": con_bono}
        if d.get("demo"):
            s.vw_plan = plan
        sesiones = crear_sesiones(ev, plan) if d.get("servicios") else 0
        ev.live = True
        ev.save()

        # El dueño: usuario de su panel, en su equipo, con aviso por correo de cada reserva y anulación.
        u = User.objects.filter(email=d["email"]).first()
        if not u:
            u = User.objects.create_user(d["email"], d["clave"], locale="es", timezone=zona, fullname=d["negocio"])
        t, _ = Team.objects.get_or_create(organizer=o, name="Administración", defaults={
            "all_events": True, "all_event_permissions": True, "all_organizer_permissions": True})
        t.members.add(u)
        if not d.get("demo"):
            for accion in ("pretix.event.order.placed", "pretix.event.order.canceled"):
                NotificationSetting.objects.get_or_create(user=u, action_type=accion, event=None, method="mail",
                                                          defaults={"enabled": True})
        return {"organizador": o.slug, "evento": ev.slug, "sesiones": sesiones, "usuario": u.email}
