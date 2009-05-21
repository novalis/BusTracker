#!/usr/bin/python
# Dump out a list of bus stops that a bus route passes through,
# with lat and long

from django.core.management.base import BaseCommand
from optparse import make_option, OptionParser
from simplejson import dumps
from tracker.models import *

import sys

class Command(BaseCommand):
    help = "Dumps bus stops with location data as a JSON string"

    def handle(self, route_name=None, route_direction=None, route_path=None, **kw):
        if route_name:
            routes = Route.objects.filter(name=route_name, direction=route_direction, path=route_path)
        else:
            routes = Route.objects.all()

        bus_stops_by_route = {}

        for route in routes:
            try:
                trip = route.trip_set.all()[0] # arbitrarily choose first trip
            except IndexError:
                print "Skipping %s because it does not have any trips" % route.route_name()
                continue # why don't some routes have trips?
            bus_stops = [ts.bus_stop for ts in trip.tripstop_set.order_by('-seconds_after_start')]
            bus_stop_data = []
            
            for bus_stop in bus_stops:
                bus_stop_data.append({
                    'location': bus_stop.location,
                    'lat': bus_stop.geometry.y,
                    'lng': bus_stop.geometry.x,
                })
        
            bus_stops_by_route[route.route_name()] = bus_stop_data

        print dumps(bus_stops_by_route)
