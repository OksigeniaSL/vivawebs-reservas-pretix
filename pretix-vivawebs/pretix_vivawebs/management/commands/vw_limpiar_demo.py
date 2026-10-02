from django.core.management.base import BaseCommand
from django_scopes import scopes_disabled


class Command(BaseCommand):
    help = "Demos de escaparate: borra las reservas de prueba que hayan hecho los visitantes (cron nocturno)."

    def handle(self, *args, **options):
        from pretix.base.models import Order

        with scopes_disabled():
            n = 0
            for o in Order.objects.filter(testmode=True, event__testmode=True):
                o.gracefully_delete(user=None)
                n += 1
        self.stdout.write(f"borradas {n} reservas de prueba")
