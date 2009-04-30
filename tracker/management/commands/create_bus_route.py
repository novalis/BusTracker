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
                #Start a new route
                name = segment['route']
                route = Route(name = name)
                route.save()
                route.routesegment_set.all().delete()
                if name.startswith("M"):
                    borough = ", Manhattan"
                path_order = 0
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
                try:
                    segment = road.roadsegment_set.get(gid=int(segment['gid']))
                except RoadSegment.DoesNotExist:
                    print >>sys.stdout, "No such gid %s" % (segment['gid'])
                    sys.exit(1)

                RouteSegment(roadsegment = segment, route=route, path_order = path_order).save()
                path_order += 1
            else:
                from_road = find_road(segment['from'] + borough)
                to_road = find_road(segment['to'] + borough)

                #There are 2 road segments of on_segment which 
                #intersect from_road: the one before and 
                #the one after.  Likewise for to_road.
                #We ultimately want the inner segments:
                #consider "8 Ave between 57 St and 55 St"

                #         |
                #         |
                #         |
                # 57 st   |8
                #---------+--------
                #        *|A
                #        *|v
                # 56 st  *|e
                #---------+--------
                #        *|
                #        *|
                # 55 st  *|
                #---------+--------
                #         |
                #         |
                #         |
                #
                # all four segments of 8 ave shown here intersect one of 55 or
                # 57 st, but we only want the two marked with *
                                
                from_segments = []
                to_segments = []

                #fixme: this could be done in sql more efficiently
                for segment in road.roadsegment_set.all():
                    if segment.geometry.intersects(from_road.geometry):
                        from_segments.append(segment)
                    if segment.geometry.intersects(to_road.geometry):
                        to_segments.append(segment)

                if len(from_segments) > 2:
                    print "Warning: there is a fork in %s at %s (and all forks share the same name). You probably want to specify a better endpoint" % (road.name, from_road.name)

                if len(to_segments) > 2:
                    print "Warning: there is a fork in %s at %s (and all forks share the same name).. You probably want to specify a better endpoint" % (road.name, to_road.name)

                if not len(from_segments):
                    print >>sys.stderr, "%s does not intersect %s" % (road.name, from_road.name)
                    sys.exit(0)
                if not len(to_segments):
                    print >>sys.stderr, "%s does not intersect %s" % (road.name, to_road.name)
                    sys.exit(0)

                if from_segments[0].path_order == to_segments[0].path_order:
                    #there's only one segment, so direction doesn't matter
                    route_segment = RouteSegment(route=route, roadsegment=from_segments[0], path_order = path_order)
                    route_segment.save()
                    path_order += 1
                    
                elif from_segments[0].path_order < to_segments[0].path_order:
                    #we're going up in road segment path_order
                    from_path_order = from_segments[0].path_order
                    if len(from_segments) > 1:
                        if from_segments[1].path_order > from_segments[0].path_order:
                            from_path_order = from_segments[1].path_order

                    to_path_order = to_segments[0].path_order
                    if len(to_segments) > 1:
                        if to_segments[1].path_order < to_segments[0].path_order:
                            to_path_order = to_segments[1].path_order


                
                    for segment in road.roadsegment_set.filter(path_order__gte=from_path_order, path_order__lte=to_path_order).order_by("path_order"):
                        route_segment = RouteSegment(route=route, roadsegment=segment, path_order = path_order)
                        route_segment.save()
                        path_order += 1
                else:
                    #we're going down in road segment path_order
                    from_path_order = from_segments[0].path_order
                    if len(from_segments) > 1:
                        if from_segments[1].path_order < from_segments[0].path_order:
                            from_path_order = from_segments[1].path_order

                    to_path_order = to_segments[0].path_order
                    if len(to_segments) > 1:
                        if to_segments[1].path_order > to_segments[0].path_order:
                            to_path_order = to_segments[1].path_order


                
                    for segment in road.roadsegment_set.filter(path_order__lte=from_path_order, path_order__gte=to_path_order).order_by("-path_order"):
                        route_segment = RouteSegment(route=route, roadsegment=segment, path_order = path_order)
                        route_segment.save()
                        path_order += 1

        from django.db import connection, transaction
        cursor = connection.cursor()
        cursor.execute(
"""UPDATE tracker_route SET geometry=(select st_linemerge(st_union(tracker_roadsegment.geometry))
FROM 
tracker_roadsegment, tracker_routesegment
WHERE 
tracker_routesegment.route_id = tracker_route.name AND
tracker_routesegment.roadsegment_id = tracker_roadsegment.gid
)""")
        transaction.commit_unless_managed()
