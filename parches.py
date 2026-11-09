"""Arreglo de pretix 2026.8.0 al construir la imagen: tres comparaciones de la ruta que no tenían en
cuenta la subcarpeta de instalación (FORCE_SCRIPT_NAME). Con /reservas/, el panel de cada evento
daba error 500. Comparan request.path (con el prefijo) donde deben comparar request.path_info,
como hace el resto de pretix. Si el texto no aparece (otra versión), el build falla para revisarlo."""
import sys
from pathlib import Path

CAMBIOS = [
    ("/pretix/src/pretix/presale/context.py",
     "    if request.path.startswith('/control'):\n", "    if request.path_info.startswith('/control'):\n", 1),
    ("/pretix/src/pretix/api/middleware.py",
     "        if not request.path.startswith('/api/'):\n", "        if not request.path_info.startswith('/api/'):\n", 2),
]
# The week selector, in Spanish words: «Semana del 9 al 15 de noviembre» (the installations are in Spanish only).
CAMBIOS.append((
    "/pretix/src/pretix/presale/templates/pretixpresale/event/fragment_subevent_calendar_week.html",
    "                                        {{ w.0|date:subevent_list.week_format }}\n"
    "                                    ({{ w.0|date:subevent_list.short_month_day_format }} – {{ w.1|date:subevent_list.short_month_day_format }})\n",
    "                                        Semana del {{ w.0|date:\"j\" }}{% if w.0.month != w.1.month %} de {{ w.0|date:\"F\" }}{% endif %}"
    " al {{ w.1|date:\"j \\d\\e F\" }}\n",
    1))
for fichero, viejo, nuevo, veces in CAMBIOS:
    p = Path(fichero)
    s = p.read_text()
    if s.count(viejo) != veces:
        sys.exit(f"parches: en {fichero} esperaba {veces} vez/veces «{viejo.strip()}» y hay {s.count(viejo)}")
    p.write_text(s.replace(viejo, nuevo))
print("parches aplicados")
