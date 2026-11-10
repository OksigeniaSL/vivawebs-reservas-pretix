from django.urls import re_path

from . import views

urlpatterns = [
    re_path(r"^$", views.inicio, name="inicio"),
    re_path(r"^vw-exportar\.php$", views.exportar, name="exportar"),
    re_path(r"^vw-libres$", views.libres, name="libres"),
    re_path(r"^vw-proximas$", views.proximas, name="proximas"),
    re_path(r"^vw-semana$", views.semana, name="semana"),
]
