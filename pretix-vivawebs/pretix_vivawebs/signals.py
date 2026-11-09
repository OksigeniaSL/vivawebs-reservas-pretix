"""Enganches de VivaWebs en pretix (señales: la forma prevista de ampliar pretix sin tocar su código)."""
import json
import logging
import os
from datetime import timedelta

import requests
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.dispatch import receiver
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.timezone import now
from django_scopes import scopes_disabled
from pretix.base.middleware import add_to_response_csp
from pretix.base.signals import periodic_task
from pretix.presale.signals import question_form_fields_overrides
from pretix.presale.signals import (
    contact_form_fields, global_html_head, global_html_page_header, html_head, process_response,
)

logger = logging.getLogger(__name__)

CLOUDFLARE = "https://challenges.cloudflare.com"
VERIFICAR = CLOUDFLARE + "/turnstile/v0/siteverify"
MARCA = os.path.join(settings.MEDIA_ROOT, "vw", "marca.css")


def _sitekey():
    return os.environ.get("TURNSTILE_SITEKEY", "")


def _secreto():
    return os.environ.get("TURNSTILE_SECRET", "")


def _en_reserva(request):
    """Pasos de la reserva (añadir datos, pago, confirmación): ahí va la comprobación anti-robots."""
    return "/checkout/" in (getattr(request, "path_info", "") or "")


# ─── Marca del negocio y comprobación anti-robots en la cabecera ───────────────────────────────

@receiver(global_html_head, dispatch_uid="vivawebs_global_html_head")
def hojas(sender, request=None, **kwargs):
    """Our skin and the business's brand on every page: the event pages and also the organizer ones (log in,
    customer account), which do not get the event signals."""
    partes = [format_html('<link rel="stylesheet" href="{}"><script src="{}" defer></script>',
                          static("pretix_vivawebs/vivawebs.css"), static("pretix_vivawebs/piel.js"))]
    if os.path.isfile(MARCA):
        partes.append(format_html('<link rel="stylesheet" href="/vendor/fonts/fonts.css">'
                                  '<link rel="stylesheet" href="{}vw/marca.css?m={}">',
                                  settings.MEDIA_URL, int(os.path.getmtime(MARCA))))
    return "".join(partes)


@receiver(html_head, dispatch_uid="vivawebs_html_head")
def cabecera(sender, request=None, **kwargs):
    partes = []
    if request is not None and _en_reserva(request) and _sitekey():
        partes.append(format_html('<script src="{}/turnstile/v0/api.js?render=explicit" async defer></script>', CLOUDFLARE))
        partes.append(format_html('<script src="{}" defer></script>', static("pretix_vivawebs/captcha.js")))
    return "".join(partes)


@receiver(global_html_page_header, dispatch_uid="vivawebs_cuenta_prueba")
def cuenta_prueba(sender, request=None, **kwargs):
    """Demos with passes: the test account on every page, also on the checkout step and the page that ask to
    log in. Only demos set vw_cuenta_prueba_datos; an event out of test mode never shows it."""
    org = getattr(request, "organizer", None)
    if org is None:
        return ""
    cuenta = org.settings.get("vw_cuenta_prueba_datos", as_type=dict)
    ev = getattr(request, "event", None)
    if not cuenta or (ev is not None and not ev.testmode):
        return ""
    return format_html('<p class="vw-prueba">Para reservar con bono sin comprarlo, entra con la cuenta de prueba: '
                       'correo <strong>{}</strong>, contraseña <strong>{}</strong>. Tiene un bono de cada tipo.</p>',
                       cuenta.get("email", ""), cuenta.get("clave", ""))


@receiver(process_response, dispatch_uid="vivawebs_csp")
def permitir_cloudflare(sender, request=None, response=None, **kwargs):
    if request is not None and _en_reserva(request) and _sitekey():
        add_to_response_csp(response, {"script-src": [CLOUDFLARE], "frame-src": [CLOUDFLARE], "connect-src": [CLOUDFLARE]})
    return response


class CasillaWidget(forms.Widget):
    """La pinta captcha.js con Turnstile en modo «solo si hace falta» (invisible salvo que Cloudflare
    pida un clic; nunca puzles). El token llega en el campo de este mismo nombre."""

    def render(self, name, value, attrs=None, renderer=None):
        return format_html('<div class="vw-captcha" data-sitekey="{}" data-campo="{}"></div>', _sitekey(), name)

    def value_from_datadict(self, data, files, name):
        return data.get(name, "")


class CasillaField(forms.CharField):
    widget = CasillaWidget

    def __init__(self, ip="", **kwargs):
        self.ip = ip
        super().__init__(label="", required=False, **kwargs)

    def clean(self, value):
        if not value:
            raise ValidationError("Estamos comprobando que no eres un robot. Espera un segundo y vuelve a pulsar el botón.")
        try:
            r = requests.post(VERIFICAR, data={"secret": _secreto(), "response": value, "remoteip": self.ip}, timeout=10)
            ok = r.json().get("success") is True
        except Exception:
            logger.exception("Turnstile: no se pudo comprobar el token")
            ok = False
        if not ok:
            raise ValidationError("No hemos podido comprobar que no eres un robot. Si ves una casilla, márcala y vuelve a pulsar el botón.")
        return "ok"


@receiver(contact_form_fields, dispatch_uid="vivawebs_casilla")
def casilla(sender, request=None, **kwargs):
    if request is None or not _en_reserva(request) or not (_sitekey() and _secreto()):
        return {}
    ip = request.headers.get("X-Real-IP") or request.META.get("REMOTE_ADDR", "")
    return {"vw_captcha": CasillaField(ip=ip)}


# ─── Tareas periódicas (las lanza `pretix cron`, cada 5 minutos desde el cron del servidor) ────

TEXTO_RECORDATORIO = """Hola:

te recordamos tu reserva en {event}:

{vw_detalle}

Si no puedes venir, anúlala o cámbiala aquí, así otra persona puede aprovechar el hueco:
{url}

Hasta pronto,
{event}"""


def _detalle(order, tz):
    lineas = []
    for p in order.positions.select_related("item", "subevent"):
        cuando = p.subevent.date_from.astimezone(tz) if p.subevent else None
        texto = str(p.item.name)
        if cuando:
            texto = f"· {cuando:%d/%m/%Y} a las {cuando:%H:%M}: {texto}"
        lineas.append(texto)
    return "\n".join(lineas)


def _recordatorios():
    """Recordatorio por correo antes de cada reserva (ajuste vw_recordatorio_horas; vacío = ninguno).
    Se apunta en la reserva para no repetirlo."""
    from zoneinfo import ZoneInfo

    from i18nfield.strings import LazyI18nString
    from pretix.base.email import get_email_context
    from pretix.base.i18n import language
    from pretix.base.models import Event, Order

    ahora = now()
    with scopes_disabled():
        for ev in Event.objects.filter(live=True, plugins__contains="pretix_vivawebs"):
            horas = ev.settings.get("vw_recordatorio_horas", as_type=int, default=0)
            if not horas:
                continue
            tz = ZoneInfo(ev.settings.timezone)
            pedidos = (ev.orders.filter(status__in=(Order.STATUS_PENDING, Order.STATUS_PAID),
                                        all_positions__subevent__date_from__gt=ahora,
                                        all_positions__subevent__date_from__lte=ahora + timedelta(hours=horas),
                                        all_positions__canceled=False)
                       .distinct())
            for o in pedidos:
                if (o.meta_info_data or {}).get("vw_recordatorio"):
                    continue
                if o.datetime > ahora - timedelta(hours=2):   # reservada hace nada: ya tiene la confirmación
                    continue
                with language(o.locale, ev.settings.region):
                    ctx = get_email_context(event=ev, order=o)
                    ctx["vw_detalle"] = _detalle(o, tz)
                    o.send_mail(LazyI18nString({"es": "Recordatorio de tu reserva en {event}"}),
                                LazyI18nString({"es": TEXTO_RECORDATORIO}), ctx, "pretix_vivawebs.recordatorio")
                meta = o.meta_info_data or {}
                meta["vw_recordatorio"] = ahora.isoformat()
                o.meta_info = json.dumps(meta)
                o.save(update_fields=["meta_info"])
                logger.info("recordatorio enviado: %s %s", ev.slug, o.code)


def _mantener_demos():
    """Las demos de escaparate (ajuste vw_plan) generan solas sus sesiones de las próximas semanas."""
    from pretix.base.models import Event

    from .configurar import crear_matriculas, crear_sesiones

    with scopes_disabled():
        for ev in Event.objects.filter(plugins__contains="pretix_vivawebs"):
            plan = ev.settings.get("vw_plan", as_type=dict, default=None)
            if plan and plan.get("renovar"):
                crear_sesiones(ev, plan, semanas=plan.get("semanas", 6))
            matriculas = ev.settings.get("vw_matriculas", as_type=list, default=None)
            if matriculas:   # demos: the enrolments of the next term and of the next July intensive
                crear_matriculas(ev, matriculas)


@receiver(periodic_task, dispatch_uid="vivawebs_periodico")
def periodico(sender, **kwargs):
    for tarea in (_recordatorios, _mantener_demos):
        try:
            tarea()
        except Exception:
            logger.exception("tarea periódica de VivaWebs: %s", tarea.__name__)


@receiver(question_form_fields_overrides, dispatch_uid="vivawebs_respuestas_previas")
def respuestas_previas(sender, position=None, request=None, **kwargs):
    """Questions already answered on the business's website (/reservas/?modalidad=…&nota=…, kept in the session):
    they come filled in, and the person can still change them. Keys are the questions' identifiers."""
    if request is None or not hasattr(request, "session"):
        return {}
    previas = request.session.get("vw_respuestas") or {}
    if not previas:
        return {}
    from pretix.base.models import Question
    out = {}
    for q in sender.questions.filter(identifier__in=list(previas)):
        valor = str(previas[q.identifier])
        if q.type in (Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE):
            op = next((o for o in q.options.all() if str(o.answer).lower().startswith(valor.lower())), None)
            if op:
                out[q.identifier] = {"initial": [op] if q.type == Question.TYPE_CHOICE_MULTIPLE else op}
        elif q.type in (Question.TYPE_TEXT, Question.TYPE_STRING):
            out[q.identifier] = {"initial": valor}
    return out
