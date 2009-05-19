from tracker.templatetags import reverse_geocode_intersection
from django.contrib.gis.geos.geometries import Point
from django.core.management.base import BaseCommand

import sys

class Command(BaseCommand):
    help = "Reverse geocode a point"

    def handle(self, lng, lat, **kw):
        lng = lng.strip(",")
        lat = lat.strip(",")
        p = Point(float(lng), float(lat))
        print reverse_geocode_intersection(p)


