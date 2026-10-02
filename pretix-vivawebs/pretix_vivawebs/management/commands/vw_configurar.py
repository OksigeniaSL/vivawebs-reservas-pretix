import json

from django.core.management.base import BaseCommand

from pretix_vivawebs.configurar import configurar


class Command(BaseCommand):
    help = "Instala o actualiza el negocio a partir de un JSON (reservas crear)."

    def add_arguments(self, parser):
        parser.add_argument("datos", help="ruta del JSON con los datos del negocio")

    def handle(self, *args, **options):
        with open(options["datos"], encoding="utf-8") as f:
            res = configurar(json.load(f))
        self.stdout.write("listo " + json.dumps(res, ensure_ascii=False))
