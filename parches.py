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
for fichero, viejo, nuevo, veces in CAMBIOS:
    p = Path(fichero)
    s = p.read_text()
    if s.count(viejo) != veces:
        sys.exit(f"parches: en {fichero} esperaba {veces} vez/veces «{viejo.strip()}» y hay {s.count(viejo)}")
    p.write_text(s.replace(viejo, nuevo))
print("parches aplicados")
