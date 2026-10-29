import shutil
from datetime import date

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "RNF-06: copia de seguridad (datos + comprobantes). Prográmala a diario con cron o el Programador de tareas."

    def handle(self, *args, **opts):
        carpeta = settings.BASE_DIR / "respaldos"
        carpeta.mkdir(exist_ok=True)
        hoy = date.today().isoformat()
        with open(carpeta / f"datos_{hoy}.json", "w", encoding="utf-8") as f:
            call_command("dumpdata", "--natural-foreign", "--indent", "2", "--exclude", "contenttypes",
                         "--exclude", "sessions", stdout=f)
        shutil.make_archive(str(carpeta / f"comprobantes_{hoy}"), "zip", settings.MEDIA_ROOT)
        self.stdout.write(self.style.SUCCESS(f"Respaldo guardado en {carpeta}"))
