import hmac
import os
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
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


@csrf_exempt   # a static website posts here; all it can do is fill in the person's own booking form
def inicio(request):
    """/reservas/ abre directamente la página de reservas del negocio (cada instalación tiene una).
    Lo que la persona ha escrito (una nota sobre su caso) mejor por POST, con un formulario: así no queda en la
    dirección, ni en los registros del servidor ni en el historial; por GET vale para lo que no es personal.
    Con ?dia=AAAA-MM-DD&hora=HH:MM (y ?servicio=, el comienzo del nombre: «Pista 6») abre esa franja con ese servicio
    ya elegido: así la web del negocio lleva a la reserva con todo puesto. Si la franja no existe, la página de reservas."""
    from pretix.multidomain.urlreverse import eventreverse

    ev = _evento()
    if not ev:
        raise Http404()
    with scopes_disabled():
        claves = set(ev.questions.exclude(identifier="").values_list("identifier", flat=True))
    datos = request.POST if request.method == "POST" else request.GET
    previas = {k: v[:1000] for k, v in datos.items() if k in claves and v.strip()}
    if previas:   # answers already given on the website (modalidad, nota…): the booking comes with them filled in
        request.session["vw_respuestas"] = previas
    dia, hora = datos.get("dia", ""), datos.get("hora", "")
    if _DIA.match(dia) and _HORA.match(hora):
        with scopes_disabled():
            try:
                sesiones, tz = _sesiones_del_dia(ev, date.fromisoformat(dia))
            except ValueError:
                sesiones = None
            se = next((x for x in sesiones if x.date_from.astimezone(tz).strftime("%H:%M") == hora), None) if sesiones is not None else None
            if se:
                return HttpResponseRedirect(_url_sesion(ev, se, _servicio(ev, datos.get("servicio", "")[:80])))
    return HttpResponseRedirect(eventreverse(ev, "presale:event.index"))


def proximas(request):
    """/reservas/vw-proximas: the next free slot of each service (within the slots already created), with its link:
    «la próxima, el martes a las 10:00» on the business's website."""
    ev = _evento()
    if not ev or not ev.has_subevents:
        raise Http404()
    with scopes_disabled():
        tz = ZoneInfo(ev.settings.timezone)
        items = list(ev.items.filter(active=True).order_by("position", "pk"))
        faltan = {it.pk: it for it in items}
        out = {}
        for se in ev.subevents.filter(active=True, date_from__gt=datetime.now(tz)).order_by("date_from")[:600]:
            for pk, it in list(faltan.items()):
                codigo, _ = it.check_quotas(subevent=se, fail_on_no_quotas=True)
                if codigo == 100:
                    local = se.date_from.astimezone(tz)
                    out[str(it.name)] = {"dia": local.date().isoformat(), "hora": local.strftime("%H:%M"),
                                         "reservar": _url_sesion(ev, se, it)}
                    del faltan[pk]
            if not faltan:
                break
    r = JsonResponse({"negocio": str(ev.name), "servicios": out}, json_dumps_params={"ensure_ascii": False})
    r["Cache-Control"] = "public, max-age=60"
    r["X-Robots-Tag"] = "noindex"
    return r


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


_SEMANA = re.compile(r"^(\d{4})-W(\d{2})$")


def semana(request):
    """/reservas/vw-semana?semana=AAAA-Wnn: for each session of that week (by its id, the one in /<evento>/<id>/),
    how many services are free (courts, rooms) and how many places are left at most (classes; null when unlimited).
    For the booking skin to write «quedan 2» or «4 pistas libres» on each card. Without ?semana, this week. Cached a
    minute: it asks every quota of the week."""
    from django.core.cache import cache
    ev = _evento()
    if not ev or not ev.has_subevents:
        raise Http404()
    with scopes_disabled():
        tz = ZoneInfo(ev.settings.timezone)
        m = _SEMANA.match(request.GET.get("semana", ""))
        try:
            lunes = date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1) if m else \
                datetime.now(tz).date() - timedelta(days=datetime.now(tz).weekday())
        except ValueError:
            raise Http404()
        clave = f"vw-semana:{ev.pk}:{lunes.isoformat()}"
        datos = cache.get(clave)
        if datos is None:
            ini = datetime.combine(lunes, datetime.min.time(), tz)
            from collections import defaultdict
            from pretix.base.models import Quota
            from pretix.base.services.quotas import QuotaAvailability
            sesiones = list(ev.subevents.filter(active=True, date_from__gte=ini, date_from__lt=ini + timedelta(days=7)))
            # Every quota of the week in one go (asking item by item took seconds).
            quotas = list(Quota.objects.filter(event=ev, subevent__in=sesiones).prefetch_related("items"))
            qa = QuotaAvailability(full_results=False)
            qa.queue(*quotas)
            qa.compute()
            por_sesion = defaultdict(lambda: defaultdict(list))   # session → item → [(state, places left)]
            for q in quotas:
                for it in q.items.all():
                    if it.active:
                        por_sesion[q.subevent_id][it.pk].append(qa.results[q])
            ahora = datetime.now(tz)
            datos = {}
            for se in sesiones:
                libres, plazas = 0, 0
                for resultados in por_sesion[se.pk].values():
                    if se.date_from > ahora and all(estado == Quota.AVAILABILITY_OK for estado, _ in resultados):
                        libres += 1
                        nums = [n for _, n in resultados if n is not None]
                        n = min(nums) if nums else None
                        plazas = None if (n is None or plazas is None) else max(plazas, n)
                datos[str(se.pk)] = {"libres": libres, "plazas": plazas if libres else 0}
            cache.set(clave, datos, 60)
    r = JsonResponse({"semana": lunes.isoformat(), "sesiones": datos}, json_dumps_params={"ensure_ascii": False})
    r["Cache-Control"] = "public, max-age=60"
    r["X-Robots-Tag"] = "noindex"
    return r
