#!/usr/bin/python
# Import bus/intersection observations from before we refactored the models to use the MTA data
# Reads a directory of JSON files of the serialized objects.

from django.core.management.base import BaseCommand
from django.core import serializers
from django.utils.datastructures import SortedDict
from optparse import make_option, OptionParser
from simplejson import dumps
from tracker.models import *
from mta_data.models import *

import sys
import os

#75 m / 1 decimal degree
STOP_FUDGE = 0.0000676

class Command(BaseCommand):
    help = "Imports bus and intersection observations from the old model format"

    def handle(self, dirname, **kw):
        files = os.listdir(dirname)
        for filename in files:
            print "importing %s" % filename
            f = open(os.path.join(dirname, filename))
            # For a BusObservation queryset of bus_id 7 the filename should look like M6_N_7.json
            # For an IntersectionObservation queryset the filename should look like M6_S_66_intersections.json
            filename = filename[:-5] if filename.endswith('json') else filename
            route_name, direction = filename.split('_')[:2]
            data = f.read()
            f.close()
            observation_group = serializers.deserialize('json', data)
        
            for observation in observation_group:
                ob = observation.object
                route = Route.objects.get(name=route_name, direction=direction) # will only work sometimes
                if hasattr(ob, 'intersection'):
                    intersection = ob.intersection
                else:
                    intersection = None
                apply_observation(ob.location.y, ob.location.x, ob.time, ob.bus_id, route, intersection=intersection)
