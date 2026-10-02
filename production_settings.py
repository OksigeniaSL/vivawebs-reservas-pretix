# VivaWebs: pretix vive en https://<negocio>.vivawebs.com/reservas/. FORCE_SCRIPT_NAME hace que TODAS
# las direcciones (también las de los correos, que genera el proceso de tareas) lleven /reservas.
import os

from pretix.settings import *  # noqa: F401,F403

LOGGING["handlers"]["mail_admins"]["include_html"] = True  # noqa: F405
STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"  # noqa: F405
FORCE_SCRIPT_NAME = "/reservas"

# Demos de escaparate: ningún correo sale (si no, servirían para mandar correos a terceros).
if os.environ.get("VW_DEMO") == "1":
    EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
