#!/usr/bin/python
# Dump out a list of intersections that a bus route passes through,
# with lat and long

from django.core.management.base import BaseCommand
from optparse import make_option, OptionParser
from simplejson import dumps
from tracker.models import *

import sys

class Command(BaseCommand):
    help = "Creates bus routes from a human-readable format."

    def handle(self, bus_route, **kw):
        route = Route.objects.get(name=bus_route)
        roadsegments = [x.roadsegment for x in route.routesegment_set.all()]

        intersections = []

        for i, on_segment in enumerate(roadsegments):
            if i == len(roadsegments) - 1:
                intersections.append({'intersection' : "[end]", 
                                      'lng' : route.geometry.coords[-1][0],
                                      'lat' : route.geometry.coords[-1][1]})
                break

            next_segment = roadsegments[i + 1]

            center_of_intersection = on_segment.geometry.intersection(next_segment.geometry)

            import pdb;pdb.set_trace()

            if center_of_intersection.empty:
                print "error: no intersection at %s, %s" % (on_segment.road.name, next_segment.road.name)
                sys.exit(1)

            if on_segment.road == next_segment.road:
                intersecting_segs = RoadSegment.objects.filter(geometry__intersects = center_of_intersection)
                for seg in intersecting_segs:                    
                    if seg.road != on_segment.road:
                        intersection = "%s and %s" % (on_segment.road.name, seg.road.name)
                intersection = "uh-oh"
                print center_of_intersection, intersecting_segs
                
            else:
                #turn or road name change

                intersection = '%s at %s' % (on_segment.road.name, next_segment.road.name)


            intersections.append({'intersection' : intersection, 
                                  'lng' : center_of_intersection.coords[0],
                                  'lat' : center_of_intersection.coords[1]})
        #print dumps(intersections)
        print intersections
