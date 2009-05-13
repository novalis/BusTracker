from datetime import time
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from mta_data_parser import parse_schedule_dir
from mta_data.models import *
from simplejson import dumps

import os

def time_from_centiminutes(centiminutes):
    #the MTA's day starts at some non-midnight time, but that needn't
    #bother us so long as we are sure never to use absolute times any
    #time subtraction might be required
    hours = (centiminutes / 6000) % 24 
    minutes = (centiminutes % 6000) / 100

    seconds = ((centiminutes % 6000) - minutes * 100) * 60 / 100
    return time(hours, minutes, seconds)

class Command(BaseCommand):
    def handle(self, dirname, route_table, **kw):
        for route_rec in parse_schedule_dir(dirname):

            #fixme: need to handle s4898
            name = "%s%s%s" % (route_rec['borough'], route_rec['route_no'], route_rec['route_name_flag'])
            route = Route(name = name, 
                          geometry = None)
            route.save()

            bus_stops = {}
            for stop_rec in route_rec['stops']:
                stop = BusStop(box_no = stop_rec['box_no'], 
                               location = "%s at %s" % (stop_rec['street1'], stop_rec['street2']),
                               geometry = Point(stop_rec['longitude'] / 100000.0,
                                                stop_rec['latitude'] / 100000.0))
                stop.save()
                bus_stops[stop_rec['stop_id']] = stop
            for trip_rec in route_rec['trips']:
                trip = Trip(route = route, 
                            start_time = time_from_centiminutes(trip_rec['start_minutes']),
                            direction = trip_rec['direction'],
                            day_of_week = route_rec['day_of_week'])
                trip.save()
                start_time = trip_rec['start_minutes']
                for trip_stop_rec in trip_rec['stops']:
                    trip_stop = TripStop(trip = trip,
                                         seconds_after_start = (trip_stop_rec['minutes'] - start_time) * 0.6,
                                         bus_stop = bus_stops[trip_stop_rec['stop_id']],
                                         type = trip_stop_rec['type'])


                    trip_stop.save()
                
                        
