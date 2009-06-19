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
            f = open(os.path.join(dirname, filename))
            # For a BusObservation queryset of bus_id 7 the filename should look like M6_N_7.json
            # For an IntersectionObservation queryset the filename should look like M6_S_66_intersections.json
            filename = filename[:-5] if filename.endswith('json') else filename
            route_name, direction = filename.split('_')[:2]
            data = f.read()
            f.close()
            observation_group = serializers.deserialize('json', data)
        
            for observation in observation_group:
                self._import_observation(observation.object, route_name, direction)


    def _import_observation(self, observation, route_name, direction):
        # Most of this was mindlessly pulled from update in tracker/views.py
        bus_id = observation.bus_id
        
        route = Route.objects.get(name=route_name, direction=direction)

        #figure out what trip we are on by assuming it is the trip
        #starting closest to here and now.

        client_time = observation.time

        bus_candidates = (Bus.objects.filter(id=bus_id)[:1])

        location = observation.location

        if len(bus_candidates):
            bus = bus_candidates[0]
            trip = bus.trip
        else:
            #fixme: day of week
            location_sql = "SRID=4326;POINT(%s %s)" % (location.x, location.y)
            trip = Trip.objects.filter(route=route).extra(
                tables = ['mta_data_shape'],
                select = SortedDict([
                        ('start_error', 'abs(extract(epoch from start_time - %s))'),
                        ('shape_error', 'st_distance(st_startpoint(mta_data_shape.geometry), %s)')
                        ]),  
                select_params = (client_time.time(), location_sql)
                ).order_by('start_error')[0]
        
            bus = Bus(id=bus_id, trip=trip)
            bus.save()

        if hasattr(observation, 'intersection'):
            obs = IntersectionObservation(bus=bus, location=location, time=client_time, intersection = observation.intersection)
            obs.save()
        else:
            possible_observations = bus.busobservation_set.order_by('-time')[:2]
            if (len(possible_observations) == 2 and 
                possible_observations[0].location == location and 
                possible_observations[1].location == location):
                possible_observations[0].time = client_time
            else:
                obs = BusObservation(bus=bus,
                                     location=location,
                                     time=client_time,
                                     speed=observation.speed,
                                     course=observation.course,
                                     horizontal_accuracy=observation.horizontal_accuracy,
                                     vertical_accuracy=observation.vertical_accuracy,
                                     altitude=observation.altitude)
                                           
                obs.save()
                
                #fixme: this WILL NOT WORK until observation distances are
                #nondescending.

                #figure out dwell information
                route_length = trip.shape.length
                stop_fudge = STOP_FUDGE / route_length

                prev_bus_stop = TripStop.objects.filter(
                    trip=bus.trip, 
                    distance__lte=obs.distance + stop_fudge * route_length
                    ).order_by('distance')[:1]

                if len(prev_bus_stop):
                    prev_bus_stop = prev_bus_stop[0]

                    try:
                        prev_observation = obs.get_previous_by_time(bus=bus)
                        if prev_observation.distance + stop_fudge <= prev_bus_stop.distance:
                            #this is our first post-stop observation

                            #find the observation that was before the stop.
                            before_stop_observation = BusObservation.objects.filter(
                                distance__lte=prev_bus_stop.distance - stop_fudge
                                )[0]
                            bus.total_dwell_time += (client_time - before_stop_observation.time).seconds
                            bus.n_dwells += 1
                    except BusObservation.DoesNotExist:
                        pass
