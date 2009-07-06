#!/usr/bin/python

from django.core.management.base import BaseCommand
from django.core import serializers
from optparse import make_option, OptionParser
from tracker.models import *
from mta_data.models import *

import sys

class Command(BaseCommand):
    help = "Dump bus observation data as JSON files"

    def handle(self, bus_ids=None, **kw):

        if not bus_ids:
            bus_ids = [bus.id for bus in Bus.objects.all()]
        else:
            bus_ids = bus_ids.split(',')

        for id in bus_ids:
            id = int(id)
            obs = BusObservation.objects.filter(bus=id)
            if not len(obs):
                continue
            route_name = obs[0].bus.trip.route.route_name().replace(' ', '_')
            fname = "%s_%s.json" % (route_name, id)
            f = open(fname, "w")
            f.write(serializers.serialize('json', obs))
            f.close()

            intersection_obs = IntersectionObservation.objects.filter(bus=id)
            if intersection_obs:
                fname = "%s_%s_intersections.json" % (route_name, id)
                f = open(fname, "w")
                f.write(serializers.serialize('json', intersection_obs))
                f.close()

