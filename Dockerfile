# Clases y actividades, y salas y espacios, del servicio de reservas de VivaWebs: pretix 2026.8.0
# (AGPLv3) con nuestro complemento, nuestra traducción y un arreglo de una línea. El código de lo que
# se ejecuta está publicado (lo exige su licencia, ver README). Versiones FIJADAS.
FROM pretix/standalone:2026.8.0
USER root

# Arreglo: pretix no tenía en cuenta la subcarpeta /reservas/ en tres comparaciones (el panel de cada
# evento daba error). Es un fallo de pretix; si cambian esas líneas en una versión nueva, el build falla.
COPY parches.py /tmp/parches.py
RUN python3 /tmp/parches.py && rm /tmp/parches.py

# Vive en https://<negocio>.vivawebs.com/reservas/ (también los enlaces de los correos).
COPY production_settings.py /pretix/src/production_settings.py
# Un solo proceso de tareas por negocio (por defecto arranca uno por procesador del servidor).
COPY pretixtask.conf /etc/supervisord/pretixtask.conf

# Nuestro complemento y nuestra traducción (español de España, tuteo y vocabulario de reservas).
COPY pretix-vivawebs /tmp/pretix-vivawebs
RUN pip install --no-cache-dir --no-deps /tmp/pretix-vivawebs && rm -rf /tmp/pretix-vivawebs
COPY locale /vivawebs/locale
RUN for d in django djangojs; do msgfmt -o /vivawebs/locale/es/LC_MESSAGES/$d.mo /vivawebs/locale/es/LC_MESSAGES/$d.po; done

# Estáticos (también los del complemento) con la ruta /reservas/static/.
COPY build.cfg /tmp/build.cfg
RUN cd /pretix/src && PRETIX_CONFIG_FILE=/tmp/build.cfg DATA_DIR=/tmp/data python3 -m pretix rebuild \
 && rm -rf /tmp/build.cfg /tmp/data && chown -R pretixuser:pretixuser /pretix/src/pretix/static.dist
USER pretixuser
