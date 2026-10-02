"""Todas las reservas en una hoja de cálculo (CSV abierto, VivaWebs #254): la misma descarga que en
citas, mesas y alojamiento. La pide el portal del cliente (vw-exportar.php, con la clave en una
cabecera) o `reservas exportar` desde el servidor (comando vw_exportar)."""
import csv
import io
import re
from zoneinfo import ZoneInfo

from django_scopes import scopes_disabled

ESTADOS = {"n": "Pendiente de pago", "p": "Pagada", "c": "Anulada", "e": "Caducada"}
COLUMNAS = ["Reserva", "Estado", "Servicio", "Día", "Hora", "Hasta", "Nombre", "Correo", "Teléfono",
            "Importe", "Reservada el"]


def _celda(v):
    v = "" if v is None else str(v).strip()
    return "'" + v if re.match(r"^[=+\-@\t\r]", v) else v   # que la hoja de cálculo no lo tome como fórmula


def csv_reservas() -> bytes:
    from pretix.base.models import OrderPosition

    out = io.StringIO()
    out.write("﻿")   # así Excel lo abre con tildes
    w = csv.writer(out, delimiter=";", lineterminator="\r\n")
    w.writerow(COLUMNAS)
    with scopes_disabled():
        qs = (OrderPosition.all.select_related("order", "order__event", "item", "subevent")
              .order_by("subevent__date_from", "order__datetime"))
        for p in qs:
            o, ev = p.order, p.order.event
            tz = ZoneInfo(ev.settings.timezone)
            ini = p.subevent.date_from.astimezone(tz) if p.subevent else None
            fin = p.subevent.date_to.astimezone(tz) if p.subevent and p.subevent.date_to else None
            ia = getattr(o, "invoice_address", None)
            nombre = (p.attendee_name or (ia.name if ia else "") or "")
            estado = "Anulada" if p.canceled else ESTADOS.get(o.status, o.status)
            w.writerow([_celda(x) for x in (
                o.code, estado, str(p.item.name),
                ini.strftime("%d/%m/%Y") if ini else "", ini.strftime("%H:%M") if ini else "", fin.strftime("%H:%M") if fin else "",
                nombre, o.email, str(o.phone or ""), f"{p.price:.2f}".replace(".", ","),
                o.datetime.astimezone(tz).strftime("%d/%m/%Y %H:%M"))])
    return out.getvalue().encode("utf-8")
