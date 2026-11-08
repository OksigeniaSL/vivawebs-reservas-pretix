from django.core.management.base import BaseCommand
from django.db.models import ProtectedError
from django_scopes import scopes_disabled


class Command(BaseCommand):
    help = "Demos de escaparate: borra las reservas de prueba que hayan hecho los visitantes (cron nocturno)."

    def handle(self, *args, **options):
        from pretix.base.models import Customer, Membership, Order, Organizer

        with scopes_disabled():
            n = 0
            for o in Order.objects.filter(testmode=True, event__testmode=True):
                o.gracefully_delete(user=None)
                n += 1
            # Demos with passes: drop the passes and accounts visitors created; keep the test account.
            cuentas = 0
            for org in Organizer.objects.all():
                prueba = org.settings.get("vw_cuenta_prueba")
                if not prueba:
                    continue
                Membership.objects.filter(customer__organizer=org, testmode=True, granted_in__isnull=True,
                                          orderposition__isnull=True).exclude(customer__email=prueba).delete()
                for c in Customer.objects.filter(organizer=org).exclude(email=prueba):
                    try:
                        c.delete()
                        cuentas += 1
                    except ProtectedError:
                        pass
        self.stdout.write(f"borradas {n} reservas de prueba y {cuentas} cuentas de visitantes")
