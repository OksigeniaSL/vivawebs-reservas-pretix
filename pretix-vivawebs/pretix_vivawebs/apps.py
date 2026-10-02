from pretix.base.plugins import PluginConfig

from . import __version__


class PluginApp(PluginConfig):
    default = True
    name = "pretix_vivawebs"
    verbose_name = "VivaWebs"

    class PretixPluginMeta:
        name = "VivaWebs"
        author = "Oksigenia S.L."
        description = ("Reservas de VivaWebs: comprobación anti-robots, recordatorios, marca del negocio "
                       "y descarga de reservas.")
        visible = False          # siempre activo: el negocio no lo ve ni lo puede quitar
        version = __version__
        category = "INTEGRATION"
        compatibility = "pretix>=2026.8.0"

    def ready(self):
        from . import signals  # noqa: F401
