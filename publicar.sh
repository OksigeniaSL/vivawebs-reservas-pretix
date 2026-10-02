#!/bin/sh
# Publica esta carpeta en el repositorio público que exige la licencia de pretix (AGPLv3):
# https://github.com/OksigeniaSL/vivawebs-reservas-pretix. Ejecutar tras cada cambio desplegado.
set -e
ORIGEN=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d)
git clone -q https://github.com/OksigeniaSL/vivawebs-reservas-pretix.git "$T"
find "$T" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -a "$ORIGEN"/. "$T"/
find "$T" -name __pycache__ -prune -exec rm -rf {} +
cd "$T"
git add -A
if git diff --cached --quiet; then echo "sin cambios"; else
  git -c user.name="Oksigenia S.L." -c user.email="legal@vivawebs.com" commit -q -m "${1:-Actualización desde VivaWebs}"
  git push -q origin main && echo "publicado"
fi
rm -rf "$T"
