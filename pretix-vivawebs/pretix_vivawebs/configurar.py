"""Instalación sin formularios de un negocio en pretix (la llama `reservas crear`).

Datos (JSON):
    slug, tipo ("clases" | "salas"), negocio, email, clave, zona, color, web, privacidad, aviso_legal,
    logo (data URI png/jpg/webp), demo (bool), fuente (URL del código fuente publicado),
    clases:  servicios: [{nombre, precio, descripcion, plazas, duracion (min), dias [0=lunes…], hora "HH:MM"}]
    salas:   horario: {dias, desde "HH:MM", hasta "HH:MM", minutos}
             recursos: [{nombre, cantidad}]
             servicios: [{nombre, precio, descripcion, usa: [nombres de recursos]}]
Sin servicios, la agenda se crea vacía y el dueño los da de alta en su panel: no inventamos precios.
"""
import base64
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


def crear_sesiones(ev, plan, semanas=8, desde=None):
    """Crea (sin duplicar) las sesiones o franjas de las próximas semanas según el plan."""
    from pretix.base.models import Item, Quota, SubEvent

    tz = ZoneInfo(ev.settings.timezone)
    hoy = desde or datetime.now(tz).date()
    existentes = set(ev.subevents.values_list("date_from", "name"))
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
                          [(s["nombre"], int(s["plazas"]), [s["nombre"]])])
        else:
            h = plan.get("horario")
            if not h or d.weekday() not in h.get("dias", []):
                continue
            ini, fin_dia = datetime.combine(d, _hora(h["desde"]), tz), datetime.combine(d, _hora(h["hasta"]), tz)
            paso = timedelta(minutes=int(h.get("minutos", 60)))
            while ini + paso <= fin_dia:
                cupos = [(r["nombre"], int(r["cantidad"]),
                          [s["nombre"] for s in plan.get("servicios", []) if r["nombre"] in s.get("usa", [])])
                         for r in plan.get("recursos", [])]
                nueva(ini, ini + paso, "Cita", cupos)
                ini += paso
    return nuevas


def _logo(ev, data_uri):
    m = re.match(r"^data:image/(png|jpe?g|webp);base64,(.+)$", data_uri or "", re.S)
    if not m:
        return
    ext = "jpg" if m.group(1).startswith("jp") else m.group(1)
    nombre = default_storage.save(f"pub/{ev.organizer.slug}/{ev.slug}/logo.{ext}", ContentFile(base64.b64decode(m.group(2))))
    ev.settings.set("logo_image", "file://" + nombre)


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

        ev = Event.objects.filter(organizer=o).first()
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
        s.frontpage_text = ES(PORTADA[tipo])
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
        for sv in d.get("servicios", []):
            it, _ = Item.objects.get_or_create(event=ev, name=ES(sv["nombre"]),
                                               defaults={"default_price": sv.get("precio") or 0, "admission": True})
            it.default_price = sv.get("precio") or 0
            if sv.get("descripcion"):
                it.description = ES(sv["descripcion"])
            it.save()
        plan = {"tipo": tipo, "servicios": d.get("servicios", []), "horario": d.get("horario"),
                "recursos": d.get("recursos", []), "renovar": bool(d.get("demo")), "semanas": 6}
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
