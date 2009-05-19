from tracker.views import geocode
from django.contrib.gis.geos.geometries import Point
from django.core.management.base import BaseCommand

import sys

class Command(BaseCommand):
    help = "Geocode an address"

    def handle(self, address, **kw):
        print geocode(address)


