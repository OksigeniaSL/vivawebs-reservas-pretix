import sys

from django.core.management.base import BaseCommand

from pretix_vivawebs.exportar import csv_reservas


class Command(BaseCommand):
    help = "Todas las reservas en CSV por la salida estándar (reservas exportar)."

    def handle(self, *args, **options):
        sys.stdout.buffer.write(csv_reservas())
        sys.stdout.flush()
