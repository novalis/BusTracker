#!/usr/bin/python
# Imports tiger data from the table provided on the command-line into the tracker tables.

from django.core.management.base import BaseCommand
from optparse import make_option, OptionParser
from tracker.models import *

import sys

class Command(BaseCommand):
    help = "Creates bus routes from a human-readable format."

    def handle(self, bus_route_file, **kw):
        f = open(bus_route_file)

        for line_no, line in enumerate(f.readlines()):
            if "#" in line:
                line = line[:line.index("#")]

            line = line.strip()
            if not line:
                continue

            items = line.split(", ")
            segment = {}
            for item in items:
                key, value = item.split(": ")
                segment[key.lower()] = value

            if 'route' in segment:
                name = segment['route']
                route = Route(name = name)
                if name.startswith("M"):
                    borough = ", Manhattan"

                continue

            def find_road(road_name):
                try:
                    road = Road.objects.get(name=road_name)
                except Road.DoesNotExist:
                    print >>sys.stdout, "No such road %s on line %d" % (road_name, line_no)
                    sys.exit(1)
                return road
                

            road = find_road(segment['on'] + borough)
            if 'gid' in segment:
                #some roadsegments must be chosen by GID because the
                #roadsegment ordering system does not work for circles
                segment = road.roadsegment_set.get(gid=int(segment['gid']))
                RouteSegment(roadsegment = segment, route=route).save()
            else:
                from_road = find_road(segment['from'] + borough)
                to_road = Road.objects.get(name=segment['to'] + borough)

                for segment in road.roadsegment_set.all():
                    if segment.geometry.intersects(from_road.geometry):
                        from_order = segment.path_order
                    if segment.geometry.intersects(to_road.geometry):
                        to_order = segment.path_order
                if from_order > to_order:
                    from_order, to_order = to_order, from_order
                
                for segment in road.roadsegment_set.filter(path_order__gte=from_order, path_order__lt=to_order):
                    route_segment = RouteSegment(route=route, roadsegment=segment)
                    route_segment.save()

#todo: update route geometry
