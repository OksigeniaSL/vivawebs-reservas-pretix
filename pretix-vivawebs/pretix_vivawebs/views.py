import hmac
import os
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django_scopes import scopes_disabled

from .exportar import csv_reservas


def exportar(request):
    """Descarga de las reservas para el portal del cliente. Sin la clave correcta: 404."""
    clave = os.environ.get("EXPORTAR_TOKEN", "")
    if not clave or not hmac.compare_digest(clave, request.headers.get("X-Vw-Exportar", "")):
        raise Http404()
    r = HttpResponse(csv_reservas(), content_type="text/csv; charset=utf-8")
    r["Content-Disposition"] = 'attachment; filename="reservas.csv"'
    r["Cache-Control"] = "no-store"
    r["X-Robots-Tag"] = "noindex"
    return r


_DIA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HORA = re.compile(r"^\d{2}:\d{2}$")


def _evento():
    """The business's booking page (one per installation; with matrículas or bonos, the main one comes first)."""
    from pretix.base.models import Event
    with scopes_disabled():
        return Event.objects.filter(live=True, has_subevents=True).order_by("pk").first() \
            or Event.objects.filter(live=True).order_by("pk").first()


def _sesiones_del_dia(ev, dia: date):
    tz = ZoneInfo(ev.settings.timezone)
    ini = datetime.combine(dia, datetime.min.time(), tz)
    return ev.subevents.filter(active=True, date_from__gte=ini, date_from__lt=ini + timedelta(days=1)).order_by("date_from"), tz


def _servicio(ev, nombre: str):
    """The service (item) whose name starts with `nombre`: «Pista 6» finds «Pista 6 (panorámica de cristal)»."""
    nombre = (nombre or "").strip().lower()
    if not nombre:
        return None
    return next((i for i in ev.items.filter(active=True).order_by("position", "pk") if str(i.name).lower().startswith(nombre)), None)


def _url_sesion(ev, se, item=None) -> str:
    from pretix.multidomain.urlreverse import eventreverse
    return eventreverse(ev, "presale:event.index", kwargs={"subevent": se.pk}) + (f"?item={item.pk}" if item else "")


def inicio(request):
    """/reservas/ abre directamente la página de reservas del negocio (cada instalación tiene una).
    Con ?dia=AAAA-MM-DD&hora=HH:MM (y ?servicio=, el comienzo del nombre: «Pista 6») abre esa franja con ese servicio
    ya elegido: así la web del negocio lleva a la reserva con todo puesto. Si la franja no existe, la página de reservas."""
    from pretix.multidomain.urlreverse import eventreverse

    ev = _evento()
    if not ev:
        raise Http404()
    dia, hora = request.GET.get("dia", ""), request.GET.get("hora", "")
    if _DIA.match(dia) and _HORA.match(hora):
        with scopes_disabled():
            try:
                sesiones, tz = _sesiones_del_dia(ev, date.fromisoformat(dia))
            except ValueError:
                sesiones = None
            se = next((x for x in sesiones if x.date_from.astimezone(tz).strftime("%H:%M") == hora), None) if sesiones is not None else None
            if se:
                return HttpResponseRedirect(_url_sesion(ev, se, _servicio(ev, request.GET.get("servicio", "")[:80])))
    return HttpResponseRedirect(eventreverse(ev, "presale:event.index"))


def libres(request):
    """/reservas/vw-libres?dia=AAAA-MM-DD: las franjas de ese día con cada servicio libre o no, su precio y el enlace
    que lo reserva. Para que la web del negocio enseñe lo libre (las pistas encendidas, las salas vacías) con los
    datos de verdad. Sin ?dia, hoy."""
    ev = _evento()
    if not ev or not ev.has_subevents:
        raise Http404()
    with scopes_disabled():
        tz = ZoneInfo(ev.settings.timezone)
        dia = request.GET.get("dia", "")
        try:
            dia = date.fromisoformat(dia) if _DIA.match(dia) else datetime.now(tz).date()
        except ValueError:
            raise Http404()
        sesiones, tz = _sesiones_del_dia(ev, dia)
        items = list(ev.items.filter(active=True).order_by("position", "pk"))
        ahora = datetime.now(tz)
        franjas = []
        for se in sesiones:
            servicios = {}
            for it in items:
                codigo, _ = it.check_quotas(subevent=se, fail_on_no_quotas=True)   # no quota in this slot: not free
                servicios[str(it.name)] = {
                    "libre": codigo == 100 and se.date_from > ahora,   # Quota.AVAILABILITY_OK
                    "precio": f"{se.item_price_overrides.get(it.pk, it.default_price):.2f}",
                    "reservar": _url_sesion(ev, se, it),
                }
            franjas.append({"hora": se.date_from.astimezone(tz).strftime("%H:%M"),
                            "fin": se.date_to.astimezone(tz).strftime("%H:%M") if se.date_to else "",
                            "servicios": servicios})
    r = JsonResponse({"negocio": str(ev.name), "dia": dia.isoformat(), "franjas": franjas},
                     json_dumps_params={"ensure_ascii": False})
    r["Cache-Control"] = "public, max-age=60"
    r["X-Robots-Tag"] = "noindex"
    return r
