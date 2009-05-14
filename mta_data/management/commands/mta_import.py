from datetime import time
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.db import transaction
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


class MTARoute(models.Model):
    id = models.IntegerField(primary_key=True)
    rt_dir = models.CharField(max_length=1)
    route = models.CharField(max_length=16)
    the_geom = models.GeometryField()


fix_direction = {
    'Bx14' : {'W' : 'S', 'E' : 'N'},
    'S54' : {'E' : 'S'},

}

def process_route(route_rec, mta_routes, name):
    print "importing", name
    routes_by_direction = {}
    for mta_route in mta_routes:
        direction = mta_route.rt_dir
        geometry = mta_route.the_geom
        route = Route(name = name, 
                      geometry = geometry,
                      direction = direction)
        route.save()
        routes_by_direction[direction] = route

    bus_stops = {}
    for stop_rec in route_rec['stops']:
        geometry = Point(stop_rec['longitude'] / 100000.0,
                         stop_rec['latitude'] / 100000.0)
        location = "%s at %s" % (stop_rec['street1'], stop_rec['street2'])
        stop = BusStop(box_no = stop_rec['box_no'], 
                       location = location,
                       geometry = geometry)
        stop.save()
        bus_stops[stop_rec['stop_id']] = stop
    for trip_rec in route_rec['trips']:
        if trip_rec['route_name'] != name:
            continue
        #fix up bogus direction information
        direction = trip_rec['direction']
        if name in fix_direction:
            fix = fix_direction[name]
            if direction in fix:
                direction = fix[direction]

        try:
            route = routes_by_direction[direction]
        except KeyError:
            print "Could not find a route for direction %s on line %s (directions are %s)" % (
                direction, name, 
                routes_by_direction.keys())
            import pdb;pdb.set_trace()
            continue

        trip = Trip(route = route, 
                    start_time = time_from_centiminutes(trip_rec['start_minutes']),
                    day_of_week = route_rec['day_of_week'])
        trip.save()
        start_time = trip_rec['start_minutes']
        for trip_stop_rec in trip_rec['stops']:
            trip_stop = TripStop(trip = trip,
                                 seconds_after_start = (trip_stop_rec['minutes'] - start_time) * 0.6,
                                 bus_stop = bus_stops[trip_stop_rec['stop_id']],
                                 type = trip_stop_rec['type'])


            trip_stop.save()


class Command(BaseCommand):
    """Import mta schedule and route data into DB.  Assume route data is 
    truth for matters of directionality"""

    @transaction.commit_manually
    def handle(self, dirname, route_table_name, **kw):

        MTARoute._meta.db_table = route_table_name
        try:
            for route_rec in parse_schedule_dir(dirname):
                #fixme: need to handle s4898                 
                #fixme: need to worry about weird bus names with ABCD
                #on the end

                if route_rec['route_name_flag'] == 'X':
                    #express buses
                    borough = 'X'
                else:
                    borough = route_rec['borough'].title()
                name = "%s%s" % (borough, 
                                   route_rec['route_no'])

                mta_routes = list(MTARoute.objects.filter(route = name))
                if len(mta_routes) > 2:
                    print "route %s is too complicated -- no way to match path names to trips yet" % name
                    continue #too complicated
                elif len(mta_routes) == 0:
                    #it's probably a multiroute file.  
                    trips = route_rec['trips']
                    names = set(trip['route_name'] for trip in trips if trip['route_name'])
                    if len(names) == 0:
                        print "route %s has no entry in shapes." % name
                        import pdb;pdb.set_trace()
                        continue
                    for name in names:

                        if name == 'S98':
                            #there's no route for the westbound S98, so we use
                            #the S48 routes, which are the same but for stops
                            search_name = 'S48'
                        else:
                            search_name = name

                        mta_routes = list(MTARoute.objects.filter(route = search_name))
                        process_route(route_rec, mta_routes, name)

                else:
                    process_route(route_rec, mta_routes, name)
                transaction.commit()
        except Exception, e:
            #import pdb;pdb.set_trace()        
            raise
