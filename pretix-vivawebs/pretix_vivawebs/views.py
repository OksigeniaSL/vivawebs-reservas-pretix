import hmac
import os

from django.http import Http404, HttpResponse, HttpResponseRedirect
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


def inicio(request):
    """/reservas/ abre directamente la página de reservas del negocio (cada instalación tiene una)."""
    from pretix.base.models import Event
    from pretix.multidomain.urlreverse import eventreverse

    with scopes_disabled():
        ev = Event.objects.filter(live=True).order_by("pk").first()
    if not ev:
        raise Http404()
    return HttpResponseRedirect(eventreverse(ev, "presale:event.index"))
