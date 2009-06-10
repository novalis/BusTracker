from django.contrib.gis.geos import LineString, Point
from django.core.management.base import BaseCommand
from math import sqrt
from mta_data_parser import parse_schedule_dir
from mta_data.models import *
from zipfile import ZipFile

import os
import transitfeed

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

    def dump_kml(self):
        f = open("/tmp/%s.kml" % self.gid, "w")
        coords = self.the_geom.coords

        print >>f, """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://earth.google.com/kml/2.2">
<Document>
"""
        for i, (x, y) in enumerate(coords):
            print>>f,  """
             <Placemark>
                <name>
			%d
                </name>
                <Point>
			<coordinates>%f, %f</coordinates>
		</Point>
              </Placemark>
""" % (i, x, y)

        print >>f, """</Document>
</kml>
"""
        f.close()
        print "dumped %s" % self.gid

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
    'S48' : 'S98',
    'S98' : 'S48',
    'X17' : 'X17J', #but what about all the other X17 routes?
    'S61' : 'S91',
    'S91' : 'S61',
}


fix_direction = {
    'BX14' : {'W' : 'S', 'E' : 'N'},
    'S74' : {'E' : 'S', 'W' : 'N'}, #fixme: check this
    'S54' : {'E' : 'S'}, #one bogus entry
    'M31' : {'W' : 'S', 'E' :'N'},
    'BX05' : {'E' : 'N', 'W' : 'S'},
    'S74' : {'E' : 'N', 'W' : 'S'},
    'S84' : {'E' : 'N', 'W' : 'S'},
}

fix_leading_zeros = {
    'Q01' : 'Q1',
    'Q02' : 'Q2',
    'Q03' : 'Q3',
    'Q04' : 'Q4',
    'Q05' : 'Q5',
    'M01' : 'M1',
    'M02' : 'M2',
    'M03' : 'M3',
    'M04' : 'M4',
    'M05' : 'M5',
    'M06' : 'M6',
    'M07' : 'M7',
    'M08' : 'M8',
    'M09' : 'M9',
    'BX03' : 'BX3',
    'BX04' : 'BX4',
    'BX05' : 'BX5',
    'BX06' : 'BX6',
    'BX07' : 'BX7',
    'BX08' : 'BX8',
    'BX09' : 'BX9',
}

def dist_line_point(A, B, p):
    #CGAlgorithms::distancePointLine comp.graphics.algorthim FAQ via GEOS

    s=(((A[1]-p[1])*(B[0]-A[0])-(A[0]-p[0])*(B[1]-A[1])) /
       ((B[0]-A[0])*(B[0]-A[0])+(B[1]-A[1])*(B[1]-A[1])))
    return abs(s)*sqrt(((B[0]-A[0])*(B[0]-A[0])+(B[1]-A[1])*(B[1]-A[1])))


#This approximates the postgresql function of the same name.  For some
#reason, it gives slightly different results.  Since I haven't looked
#at the postgresql function, I don't know why.  It's also slower than
#going through postgresql, but using postgresql appears to cause
#segfaults after some internal resource is exhausted.
def st_line_locate_point(linestring, p):

    coords = linestring.coords
    before_length = after_length = seg_length = 0
    best_dist = 1000000000

    found = None
    for i in range(len(coords) - 1):
        p0, p1 = coords[i:i+2]
        this_length = sqrt((p0[0] - p1[0]) ** 2 + (p0[1] - p1[1]) **2)
        # next four lines from comp.graphics.algorithms Frequently
        # Asked Questions  via GEOS

        dx=p1[0]-p0[0]
        dy=p1[1]-p0[1]
        len2=dx*dx+dy*dy
        r=((p[0]-p0[0])*dx+(p[1]-p0[1])*dy)/len2

        if r < 0:
            r = 0
            dist = (p0[0] - p[0]) ** 2 + (p0[1] - p[1]) ** 2
        elif r > 1:
            r = 1
            dist = (p1[0] - p[0]) ** 2 + (p1[1] - p[1]) ** 2

        else:
            dist = dist_line_point(p0, p1, p)
            
        if dist < best_dist:
            best_dist = dist

            found = r
            before_length += after_length + seg_length
            after_length = 0
            seg_length = this_length
        else:
            if found is None:
                before_length += this_length
            else:
                after_length += this_length

    total_length = before_length + seg_length + after_length
    before_r = before_length / total_length
    seg_r = seg_length / total_length

    return before_r + found * seg_r


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

    #routes are sorted by length, because we want to use the shortest
    #route that matches the points.
    for route in sorted(candidate_routes, key=lambda route:route.the_geom.length):
        total_dist = 0
        for stop in stops:
            total_dist += route.the_geom.distance(Point(stop.stop_lon, stop.stop_lat))
        if total_dist < best_dist:
            best_dist = total_dist
            best_route = route

    if candidate_routes[0].route == 'Q48':
        #this is a total hack; the Q48 is in general a total hack
        if len(stops) == 22:
            for route in candidate_routes:
                if route.gid == 10707:
                    best_route = route


    #figure out if the set of stops is shorter than the best route
    #(the bus stops or ends in the middle of the route) and if so,
    #cut the route down.

    start_location = st_line_locate_point(best_route.the_geom, (stops[0].stop_lon, stops[0].stop_lat))

    end_location = st_line_locate_point(best_route.the_geom, (stops[-1].stop_lon, stops[-1].stop_lat))

    if start_location > end_location:
        print "Backwards route %s" % route.gid
        import pdb;pdb.set_trace()

    if end_location - start_location < 0.98:
        #create a new shape for the short route
        i = 0
        while 1:
            new_gid = str(best_route.gid * 100 + 20000 + i)
            i += 1
            try:
                feed.GetShape(new_gid)
            except KeyError:
                break

        shape = transitfeed.Shape(new_gid)

        #while a binary search for start and end would probably be
        #faster, it assumes that the shapes are correctly plotted in
        #ascending order, which they appear not to be.

        #also, this doesn't split the line segments that span the
        #start and end of the route, which is basically OK because
        #routes are very overdetermined in the MTA data, so the
        #resulting path is very close.
        for point in best_route.the_geom.coords:

            distance = st_line_locate_point(best_route.the_geom, point)

            if start_location <= distance:
                if distance <= end_location:
                    shape.AddPoint(point[1], point[0])
                else:
                    #break
                    pass

        feed.AddShapeObject(shape)
    else: #not a too-short route
        try:
            shape = feed.GetShape(str(best_route.gid))
        except KeyError:
            shape = transitfeed.Shape(str(best_route.gid))
            for point in best_route.the_geom.coords:
                shape.AddPoint(point[1], point[0])

            feed.AddShapeObject(shape)

    _shape_by_stops_cache[key] = shape
    return shape

def route_for_trip(feed, trip_rec, headsign):
    route_id = str(trip_rec['headsign_id'])

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

def init_q48():
    """the shape for the Q48 is one long loop, instead of three separate
    routes: one for west, one for east from midnight - 6 am, and one
    for east during the day.  This corrects it."""

    q48 = list(MTARoute.objects.filter(route='Q48'))
    if len(q48) > 1:
        return #assume that if there's more than one shape, we have
               #already run this function

    shape = q48[0]
    coords = list(shape.the_geom.coords)
    if len(coords) != 725:
        raise ValueError("Failed to import q48: wrong size")

    on_94_st = [
        (-73.87637, 40.77293), (-73.87643, 40.77261),
        (-73.87607, 40.77114), (-73.87608, 40.77011),
        (-73.87601, 40.77005), (-73.87603, 40.76976),
        (-73.87639, 40.76901), (-73.87624, 40.76807),
        ]

    MTARoute(gid=10705, rt_dir='W', route='Q48', path='WW',
             the_geom = LineString(coords[:502])).save()
    MTARoute(gid=10706, rt_dir='E', route='Q48', path='ED',
             the_geom = LineString(coords[502:])).save()
    MTARoute(gid=10707, rt_dir='E', route='Q48', path='EN',
             the_geom = LineString(coords[502:524] + coords[458:410:-1] + on_94_st + coords[565:])).save()

class Command(BaseCommand):
    """Transform mta schedule and route data to GTFS.  Assume route data is 
    truth for matters of directionality"""

    def handle(self, dirname, route_table_name, **kw):

        MTARoute._meta.db_table = route_table_name

        init_q48()

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
                        feed.WriteGoogleTransitFeed('mta_data/bus-%s.zip' % current_borough)
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

                if last_route != name:
                    _shape_by_stops_cache.clear()
                    last_route = name

                long_name = route_rec["street_name"]
                if long_name.startswith(name):
                    long_name = long_name[len(name):].strip()


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

                #get possible shapes
                names = set()
                if name in extra_names:
                    names.add(extra_names[name])

                for trip_rec in route_rec['trips']:
                    route_name = trip_rec['route_name']
                    names.add(route_name)

                nameq = models.Q(route = name)
                for rname in names:
                    rname = fix_leading_zeros.get(rname, rname)
                    nameq |= models.Q(route__iexact = rname)

                    if rname in extra_names and extra_names[rname] not in names:
                        nameq |= models.Q(route__iexact = extra_names[rname])


                shapes = list(MTARoute.objects.filter(nameq))

                shapes_by_direction = {}
                for shape in shapes:
                    if not shape.rt_dir in shapes_by_direction:
                        shapes_by_direction[shape.rt_dir] = []
                    shapes_by_direction[shape.rt_dir].append(shape)
                del shapes

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
                    trip_route_name = trip_rec['route_name']
                    direction = trip_rec['direction']
                    if trip_route_name in fix_direction:
                        direction = fix_direction[trip_route_name].get(direction, direction)
                    shapes = shapes_by_direction.get(direction)

                    trip.shape_id = find_shape_by_stops(feed, shapes, stops, route_table_name).shape_id


            feed.Validate()
            feed.WriteGoogleTransitFeed('mta_data/bus-%s.zip' % current_borough)
        except Exception, e:
            import traceback
            traceback.print_exc()
            import pdb;pdb.set_trace()
            raise
