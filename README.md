# pretix para el servicio de reservas de VivaWebs

Este es el código de la versión de [pretix](https://pretix.eu/) con la que funciona el servicio de reservas de **VivaWebs** (Oksigenia S.L.) para **clases y actividades** y para **salas y espacios**. Se publica porque así lo exige la licencia de pretix (GNU AGPLv3 con condiciones adicionales): quien usa el servicio tiene derecho a conocer el código de lo que se ejecuta.

**No es una distribución oficial de pretix** ni está respaldada por pretix GmbH. Es pretix 2026.8.0 sin tocar, más lo que se describe aquí.

## Qué hay aquí y qué cambia respecto a pretix

| Fichero | Qué es |
|---|---|
| `Dockerfile` | Parte de la imagen oficial `pretix/standalone:2026.8.0` y le añade lo de abajo. |
| `parches.py` | **Único cambio en el código de pretix**: tres comparaciones de la ruta (`request.path`) pasan a `request.path_info`, como hace el resto de pretix. Sin esto, instalado en una subcarpeta (`/reservas/`), el panel de cada evento daba error 500. Es un fallo de pretix: cuando lo corrijan, este parche desaparece. |
| `production_settings.py` | Ajustes de Django: pretix vive en `/reservas/` (`FORCE_SCRIPT_NAME`), también en los enlaces de los correos; en las demos no se envía ningún correo. |
| `pretixtask.conf` | Un solo proceso de tareas por negocio (por defecto arranca uno por procesador). |
| `pretix-vivawebs/` | Nuestro complemento (AGPLv3): comprobación anti-robots invisible (Cloudflare Turnstile) al reservar, recordatorio por correo el día antes, tipografía del negocio, descarga de las reservas en CSV, redirección de `/reservas/` a la página de reservas e instalación sin formularios (`vw_configurar`). |
| `locale/es/` | Traducción propia al español de España: tuteo al cliente y vocabulario de reservas en lugar del de venta de entradas (reserva, plaza, servicio, sesión…). Corrige además varios errores de la traducción oficial (variables mal escritas, textos cruzados). Generada con `traducir.py` y revisada. |
| `ejemplo-*.json` | Datos de las demos de escaparate. |

El resto (la base de datos, el servidor web, las copias de seguridad, la vigilancia) lo gestiona la herramienta de reservas de VivaWebs, que no forma parte de pretix.

## Licencia

pretix es © pretix GmbH y colaboradores, bajo GNU AGPLv3 con las condiciones adicionales de su [licencia](https://github.com/pretix/pretix/blob/master/LICENSE). Nuestros cambios y nuestro complemento se publican bajo la misma licencia (fichero `LICENSE`). Las páginas de reservas indican en su pie que están basadas en pretix y enlazan a este código, como piden esas condiciones.

---

*English:* This is the source code of the pretix-based booking service run by VivaWebs (Oksigenia S.L.), published to comply with pretix's AGPLv3 license. It is pretix 2026.8.0 plus: a one-line fix for running under a URL path prefix, Django settings for the `/reservas/` prefix, our plugin `pretix-vivawebs`, and a Spanish (Spain) translation adapted to bookings. Not an official pretix distribution.
