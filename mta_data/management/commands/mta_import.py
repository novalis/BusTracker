from datetime import time
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.db import transaction, connection
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
    gid = models.IntegerField(primary_key=True)
    rt_dir = models.CharField(max_length=1)
    route = models.CharField(max_length=16)
    path = models.CharField(max_length=2)
    the_geom = models.GeometryField()


fix_direction = {
    'Bx14' : {'W' : 'S', 'E' : 'N'},
    'S74' : {'E' : 'S', 'W' : 'N'},
    'S54' : {'E' : 'S'}, #one bogus entry

}

use_alternate_route_geom = {
    'S98' : 'S48',
    'S90' : 'S40',
    'S96' : 'S46',
    'S98' : 'S48',
    'S92' : 'S62',

}

extra_names = {
    'S61' : 'S91',
    'S91' : 'S61'
}

#from Bob Ippolito at 
#http://bob.pythonmac.org/archives/2005/03/04/frozendict/
class frozendict(dict):
    __slots__ = ('_hash',)
    def __hash__(self):
        rval = getattr(self, '_hash', None)
        if rval is None:
            rval = self._hash = hash(frozenset(self.iteritems()))
        return rval

def freeze(obj):
    if isinstance(obj, dict):
        for k in obj:
            obj[k] = freeze(obj[k])
        return frozendict(obj)
    elif isinstance(obj, list):
        for i in range(len(obj)):
            obj[i] = freeze(obj[i])
        return tuple(obj)
    else:
        return obj


_route_by_stops_cache = {}
def find_route_by_stops(candidate_routes, stops, table_name):
    """This is brutal -- it matches a set of route paths against a
    known set of bus stops to choose the route path which falls
    nearest to the trip."""

    key = freeze([candidate_routes, stops, table_name])
    if key in _route_by_stops_cache:
        return _route_by_stops_cache[key]

    best_route = None
    best_dist = 100000000000000
    sql = """SELECT st_distance(the_geom, %%s) 
FROM 
%s
WHERE 
gid = %%s""" % table_name

    for route in candidate_routes:
        total_dist = 0
        for stop in stops:
            from django.db import connection
            cursor = connection.cursor()
            #fixme: is there any way to just pass the stop's geometry
            #directly?
            location = "SRID=4326;POINT(%s %s)" % (stop.geometry.x,
                                                   stop.geometry.y)
            cursor.execute(sql, (location, route.gid))
            row = cursor.fetchone()
            total_dist += row[0]
        if total_dist < best_dist:
            best_dist = total_dist
            best_route = route

    _route_by_stops_cache[key] = best_route
    return best_route

def process_route(route_rec, mta_routes, name, table_name):
    print "importing", name

    _route_by_stops_cache.clear() #multiple routes will rarely have
                                  #the same stops.

    #store routes
    routes_by_direction = {}
    for mta_route in mta_routes:
        direction = mta_route.rt_dir
        geometry = mta_route.the_geom
        route = Route(gid = mta_route.gid,
                      name = name, 
                      geometry = geometry,
                      direction = direction,
                      path = mta_route.path)
        route.save()
        if direction not in routes_by_direction:
            routes_by_direction[direction] = []
        routes_by_direction[direction].append(route)

    #store bus stops
    bus_stops = {}
    for stop_rec in route_rec['stops']:
        geometry = Point(stop_rec['longitude'] / 1000000.0,
                         stop_rec['latitude'] / 1000000.0)
        location = "%s at %s" % (stop_rec['street1'], stop_rec['street2'])
        stop = BusStop(box_no = stop_rec['box_no'], 
                       location = location,
                       geometry = geometry)
        stop.save()
        bus_stops[stop_rec['stop_id']] = stop

    #store trips
    for trip_rec in route_rec['trips']:
        if trip_rec['route_name'] != name:
            continue
        #fix up bogus direction information
        direction = trip_rec['direction']
        if not direction:
            print "no direction for %s" % name
            import pdb;pdb.set_trace()
        if name in fix_direction:
            fix = fix_direction[name]
            if direction in fix:
                direction = fix[direction]

        try:
            routes = routes_by_direction[direction]
        except KeyError:
            print "Could not find a route for direction %s on line %s (directions are %s)" % (
                direction, name, 
                routes_by_direction.keys())
            continue

        if len(routes) == 1:
            route = routes[0]
        else:
            stops = [bus_stops[tripstop['stop_id']] for tripstop in trip_rec['stops']]
            route = find_route_by_stops(routes, stops, table_name)

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
    #fixme: set headsigns based on path mapping

class Command(BaseCommand):
    """Import mta schedule and route data into DB.  Assume route data is 
    truth for matters of directionality"""

    @transaction.commit_manually
    def handle(self, dirname, route_table_name, **kw):

        MTARoute._meta.db_table = route_table_name
        try:
            for route_rec in parse_schedule_dir(dirname):
                #fixme: need to worry about weird bus names with ABCD
                #on the end

                connection.queries[:] = [] #clear out cruft stored by
                                           #debug mode
                
                if route_rec['route_name_flag'] == 'X':
                    #express buses
                    borough = 'X'
                else:
                    borough = route_rec['borough'].title()
                name = "%s%s" % (borough, 
                                   route_rec['route_no'])

                if name == 'Q48':
                    print "Don't know how to handle loop routes yet"
                    continue

                mta_routes = list(MTARoute.objects.filter(route = name))
                if len(mta_routes) == 0:
                    #it's probably a multiroute file.  
                    trips = route_rec['trips']
                    names = set(trip['route_name'] for trip in trips if trip['route_name'])
                    if len(names) == 0:
                        print "route %s has no entry in shapes." % name
                        import pdb;pdb.set_trace()
                        continue

                    for name in names:
                        if name in use_alternate_route_geom:
                            search_name = use_alternate_route_geom[name]
                        else:
                            search_name = name
                            
                        if name in extra_names:
                            extra_name = extra_names[name]
                            mta_routes = list(MTARoute.objects.get(Q(route = search_name) | Q(route = extra_name)))
                        else:
                            mta_routes = list(MTARoute.objects.filter(route = search_name))
                        process_route(route_rec, mta_routes, name, route_table_name)

                else:
                    process_route(route_rec, mta_routes, name, route_table_name)

            transaction.commit()
        except Exception, e:
            import pdb;pdb.set_trace()        
            raise
