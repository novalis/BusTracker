from django.core.management.base import BaseCommand
from mta_data_parser import parse_schedule_dir
from mta_data.models import *
import os
import transitfeed
from zipfile import ZipFile

rename_location = {
'BROADWAY at 207 ST' : 'BROADWAY at W 207 ST',
'NARROWS ROAD S at FINGERBOARD ROAD' : 'NARROWS RD S at FINGERBOARD RD',
'NARROWS RD S at FINGERBOARD ROAD' : 'NARROWS RD S at FINGERBOARD RD',
'NARROWS ROAD S at FINGERBOARD RD' : 'NARROWS RD S at FINGERBOARD RD',
'AVE U at GERRITSEN AV' : 'AV U at GERRITSEN AV',
}

def google_time_from_centiminutes(centiminutes):
    #the MTA's day is longer than 24 hours, but that needn't bother us
    #so long as we are sure never to use absolute times any time
    #subtraction might be required
    hours = (centiminutes / 6000)
    minutes = (centiminutes % 6000) / 100

    seconds = ((centiminutes % 6000) - minutes * 100) * 60 / 100
    return "%02d:%02d:%02d" % (hours, minutes, seconds)

class MTARoute(models.Model):
    gid = models.IntegerField(primary_key=True)
    rt_dir = models.CharField(max_length=1)
    route = models.CharField(max_length=16)
    path = models.CharField(max_length=2)
    the_geom = models.GeometryField()


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

extra_names = {
    'S89' : 'S59',
    'S90' : 'S40',
    'S92' : 'S62',
    'S94' : 'S44',
    'S96' : 'S46',
    'S98' : 'S48',
    'S98' : 'S48',
    'S98' : 'S48',
    'X17' : 'X17J', #but what about all the other X17 routes?
    'S61' : 'S91',
    'S91' : 'S61'
}


fix_direction = {
    'Bx14' : {'W' : 'S', 'E' : 'N'},
    'S74' : {'E' : 'S', 'W' : 'N'}, #fixme: check this
    'S54' : {'E' : 'S'}, #one bogus entry
    'M31' : {'W' : 'S', 'E' :'N'},
    'Bx5' : {'E' : 'N', 'W' : 'S'},
}


_shape_by_stops_cache = {}
def find_shape_by_stops(feed, candidate_routes, stops, table_name):
    """This is brutal -- it matches a set of route paths against a
    known set of bus stops to choose the route path which falls
    nearest to the trip."""

    key = freeze([candidate_routes, stops, table_name])
    if key in _shape_by_stops_cache:
        return _shape_by_stops_cache[key]

    best_route = None
    best_dist = 100000000000000
    sql = """SELECT st_distance(the_geom, %%s) 
FROM 
%s
WHERE 
gid = %%s""" % table_name

    from django.db import connection
    for route in candidate_routes:
        total_dist = 0
        for stop in stops:
            cursor = connection.cursor()
            #fixme: is there any way to just pass the stop's geometry
            #directly?
            location = "SRID=4326;POINT(%s %s)" % (stop.stop_lat,
                                                   stop.stop_lon)
            cursor.execute(sql, (location, route.gid))
            row = cursor.fetchone()
            total_dist += row[0]
        if total_dist < best_dist:
            best_dist = total_dist
            best_route = route

    _shape_by_stops_cache[key] = best_route
    try:
        shape = feed.GetShape(best_route.gid)
    except KeyError:
        shape = transitfeed.Shape(best_route.gid)
        for point in best_route.the_geom.coords:
            shape.AddPoint(point[0], point[1])

        feed.AddShapeObject(shape)
    return shape

def route_for_trip(feed, trip_rec, headsign):
    route_id = trip_rec['headsign_id']

    if route_id in feed.routes:
        return feed.routes[route_id]

    #create the route
    long_name = headsign + ' ' + trip_rec['direction']
    short_name = trip_rec['route_name']
    route = transitfeed.Route(route_id=route_id,
                             short_name=short_name, 
                             long_name=long_name,
                             route_type="Bus")
    feed.AddRouteObject(route)

    if short_name.startswith("X"):
        fare_id = 'express'
    elif short_name.startswith('SBS'):
        fare_id = 'sbs'
    else:
        fare_id = 'regular'

    feed.AddFareRuleObject(transitfeed.FareRule(fare_id, route_id))
    return route

def save_base_gtfs(gtfs_dir):

    gtfs_file = os.path.dirname(gtfs_dir) + "/gtfs.zip"
    zip = ZipFile(gtfs_file, "w")
    for filename in os.listdir(gtfs_dir):
        if filename.endswith(".txt"):
            zip.write(os.path.join(gtfs_dir, filename), os.path.basename(filename))
    zip.close()

class Command(BaseCommand):
    """Import mta schedule and route data into DB.  Assume route data is 
    truth for matters of directionality"""

    def handle(self, dirname, route_table_name, **kw):

        MTARoute._meta.db_table = route_table_name

        save_base_gtfs("mta_data/gtfs")

        feed = transitfeed.Loader("mta_data/gtfs.zip", memory_db=False).Load() #base data

        current_borough = None

        try:
            #capture multiple stops with different box ids
            stop_name_to_stop = {}

            last_route = None
            for route_rec in parse_schedule_dir(dirname):
                #gtfs files are organized by borough (not bus prefix)
                if current_borough != route_rec['borough']:
                    if current_borough:
                        feed.Validate()
                        feed.WriteGoogleTransitFeed('mta_data/bus-%s.zip' % borough)
                        feed = transitfeed.Loader("mta_data/gtfs.zip", memory_db=False).Load()                        
                        stop_name_to_stop = {}
                    current_borough = route_rec['borough']

                if route_rec['route_name_flag'] == 'X':
                    #express buses
                    borough = 'X'
                else:
                    borough = route_rec['borough'].title()
                name = "%s%s" % (borough, 
                                   route_rec['route_no'])

                print name
                if name == 'Q48':
                    print "Don't know how to handle loop routes yet"
                    continue

                if last_route != name:
                    _shape_by_stops_cache.clear()
                    last_route = name

                long_name = route_rec["street_name"]
                if long_name.startswith(name):
                    long_name = long_name[len(name):].strip()


                #fixme: split multiroutes
                    
                period = feed.GetServicePeriod(route_rec['day_of_week'].upper())

                stop_hexid_to_stop = {}
                #add all stops
                for stop_rec in route_rec['stops']:
                    location = "%s at %s" % (stop_rec['street1'], stop_rec['street2'])

                    location = rename_location.get(location, location)

                    #check for duplicate box ids
                    box_no = str(stop_rec['box_no'])
                    stop_id = stop_rec['stop_id']
                    if location in stop_name_to_stop:
                        stop_hexid_to_stop[stop_id] = stop_name_to_stop[location]
                        continue

                    lat = stop_rec['latitude'] / 1000000.0
                    lng = stop_rec['longitude'] / 1000000.0

                    #special case for QVDEP:
                    if location == 'Queens Village Depot':
                        lat, lng = 40.726711, -73.734779

                    #not in NYC area
                    if not (-72 > lng > -75) or not (41 > lat > 39):
                        print "bad lat, lng", lat, lng
                        import pdb;pdb.set_trace()
                        
                    #now, try to find a nearby stop
                    nearest = feed.GetNearestStops(lat, lng, 1)
                    if len(nearest) and not ' LANE ' in nearest[0].stop_name:
                        #sometimes bus stops really are like 1 m away because 
                        #they are two lanes in a multilane terminal area
                        nearest = nearest[0]
                    else:
                        nearest = None

                    if nearest and abs(nearest.stop_lat - lat) + abs(nearest.stop_lon - lng) < 0.00001:
                        stop_hexid_to_stop[stop_id] = nearest
                        stop_name_to_stop[location] = nearest
                    else:
                        stop = transitfeed.Stop(
                                lng=lng,
                                lat=lat,
                                stop_id=box_no,
                                name=location
                                )
                        stop_hexid_to_stop[stop_id] = stop
                        stop_name_to_stop[location] = stop                                    
                #figure out headsigns

                headsigns = dict((sign['headsign_id'], sign['headsign']) for sign in route_rec['headsigns'])

                #now trips
                for trip_rec in route_rec['trips']:
                    if trip_rec['trip_type'] > 1:
                        #these are trips to/from the depot
                        continue
                    if trip_rec['UNKNOWN_1'].startswith('-'):
                        #these trips are bogus -- their stops are out-of-order.
                        continue
                    hid = trip_rec['headsign_id']
                    headsign = headsigns.get(hid, long_name)

                    route = route_for_trip(feed, trip_rec, headsign)

                    trip = route.AddTrip(feed, headsign, service_period=period)
                    stops = []
                    for tripstop_rec in trip_rec['stops']:
                        stop_id = tripstop_rec['stop_id']
                        stop_time = google_time_from_centiminutes(tripstop_rec['minutes'])
                        stop = stop_hexid_to_stop[stop_id]
                        if not stop.stop_id in feed.stops:
                            feed.AddStopObject(stop)
                        trip.AddStopTime(stop,
                                         stop_time=stop_time)
                        stops.append(stop)

                    #find the appropriate shape from the shapefiles
                    extra_name = extra_names.get(name)
                    direction = fix_direction.get(trip_rec['direction'], trip_rec['direction'])
                    shapes = list(MTARoute.objects.filter(
                            models.Q(rt_dir = direction) & (
                                models.Q(route = name) | 
                                models.Q(route = extra_name))))
                    trip.shape_id = find_shape_by_stops(feed, shapes, stops, route_table_name)


            feed.Validate()
            feed.WriteGoogleTransitFeed('mta_data/bus-%s.zip' % borough)
        except Exception, e:
            import traceback
            traceback.print_exc()
            import pdb;pdb.set_trace()
            raise
