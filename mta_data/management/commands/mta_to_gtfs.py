from django.contrib.gis.geos import LineString, Point
from django.core.management.base import BaseCommand
from mta_data_parser import parse_schedule_dir
from mta_data.models import *
from mta_data.utils import st_line_locate_point
from zipfile import ZipFile

import os
import re
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

class MTABusRoute(models.Model):
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


class MTASubwayRoute(models.Model):
    gid = models.IntegerField(primary_key=True)
    id = models.FloatField()
    line = models.CharField(max_length=20)
    routes = models.CharField(max_length=9)
    the_geom = models.GeometryField()

class MTASubwayStop(models.Model):
    gid = models.IntegerField(primary_key=True)
    routes = models.CharField(max_length=13)
    line = models.CharField(max_length=16)
    facility = models.CharField(max_length=40)
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
    'S48' : 'S98',
    'S98' : 'S48',
    'X17' : 'X17J', #but what about all the other X17 routes?
    'S61' : 'S91',
    'S91' : 'S61',
    'X68' : ['X68A', 'X68B', 'X68C'],
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
loop_routes = set(['B74'])

rename_routes = {
    'S7484' : 'S84',
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

    #routes are sorted by length, because we want to use the shortest
    #route that matches the points.
    for route in sorted(candidate_routes, key=lambda route:route.the_geom.length):
        total_dist = 0
        for stop in stops:
            total_dist += route.the_geom.distance(Point(stop.stop_lon, stop.stop_lat))
        if total_dist < best_dist:
            best_dist = total_dist
            best_route = route

    if candidate_routes[0].route == 'S55':
        print "The MTA's route shape for S55 is from 2007.  So we're skipping it."
        return None

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
        print "Backwards route %s, Skipping." % route.gid
        return None

    if end_location - start_location < 0.98 and best_route.route not in loop_routes:
        if end_location - start_location < 0.05:
            print """"This is a very short route segment. Is it a 
miscategorized loop?  Route: %s, first and last: %s, %s""" % (
                best_route.route, stops[0].location, stops[-1].location)
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

        distance = 0
        for point in best_route.the_geom.coords:
            last_distance = distance
            distance = st_line_locate_point(best_route.the_geom, point)
            if start_location <= distance - 0.001:
                if distance <= end_location + 0.001:
                    shape.AddPoint(point[1], point[0])
                else:
                    line_distance_span = distance - last_distance;
                    end_distance_span = end_location - last_distance;
                    interp_ratio = end_distance_span / line_distance_span
                    interp_x = last_point[1] * interp_ratio + point[1] * (1 - interp_ratio)
                    interp_y = last_point[0] * interp_ratio + point[0] * (1 - interp_ratio)
                    shape.AddPoint(interp_x, interp_y)
                    
            last_point = point

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

def save_base_gtfs(base_gtfs_dir):
    for conveyance in ('bus', 'subway'):
        gtfs_file = os.path.join(base_gtfs_dir, "%s-gtfs.zip" % conveyance)
        zip = ZipFile(gtfs_file, "w")
        gtfs_dir =  os.path.join(base_gtfs_dir, "%s-gtfs" % conveyance)
        for filename in os.listdir(gtfs_dir):
            if filename.endswith(".txt"):
                zip.write(os.path.join(gtfs_dir, filename), os.path.basename(filename))
        zip.close()

def init_q48():
    """the shape for the Q48 is one long loop, instead of three separate
    routes: one for west, one for east from midnight - 6 am, and one
    for east during the day.  This corrects it."""

    q48 = list(MTABusRoute.objects.filter(route='Q48'))
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

    MTABusRoute(gid=10705, rt_dir='W', route='Q48', path='WW',
             the_geom = LineString(coords[:502])).save()
    MTABusRoute(gid=10706, rt_dir='E', route='Q48', path='ED',
             the_geom = LineString(coords[502:])).save()
    MTABusRoute(gid=10707, rt_dir='E', route='Q48', path='EN',
             the_geom = LineString(coords[502:524] + coords[458:410:-1] + on_94_st + coords[565:])).save()

subway_headsign = {
    '1' : {'S' : 'South Ferry',
           'N' : '242nd Street'},
    '2' : {'S' : 'Flatbush Avenue',
           'N' : '241st Street'},
    '3' : {'S' : 'New Lots Avenue',
           'N' : '148th Street'},
    '4' : {'S' : 'Utica Ave',
           'N' : 'Woodlawn'},
    '5' : {'S' : 'Dyre Ave',
           'N' : 'Flatbush Avenue'},
    '6' : {'S' : 'Brooklyn Bridge',
           'N' : 'Pelham Bay Park'},
    '7' : {'S' : 'Times Square',
           'N' : 'Flushing - Main Street'},

    'a' : {'N' : 'Lefferts Boulevard, Far Rockaway',
           'S' : 'Inwood - 207th Street'},
    'b' : {'N' : 'Bedford Park Boulevard',
           'S' : 'Brighton Beach'},
    'c' : {'N' : 'Euclid Avenue',
           'S' : '168th Street'},
    'd' : {'N' : 'Norwood - 205th Street',
           'S' : 'Coney Island'},
    'e' : {'N' : 'Jamaica Center',
           'S' : 'World Trade Center'},
    'f' : {'N' : '179th Street',
           'S' : 'Coney Island'},
    'g' : {'N' : '71st Avenue',
           'S' : 'Church Ave'},

    'h' : {'N' : 'Broad Channel', #?
           'S' : 'Rockaway Park'}, #?

    'j' : {'N' : 'Jamaica Center',
           'S' : 'Broad Street'},
    'l' : {'N' : '8th Avenue',
           'S' : 'Canarsie'},

    'm' : {'N' : 'Middle Village',
           'S' : 'Bay Parkway'},
    'n' : {'N' : 'Ditmars Boulevard',
           'S' : 'Coney Island'},
    'q' : {'N' : '57th Street',
           'S' : 'Coney Island'},
    'r' : {'N' : '71st Avenue',
           'S' : 'Bay Ridge - 95th Street'},

    'fs' : {'N' : 'Franklin Avenue',
            'S' : 'Prospect Park'}, 
    'gs' : {'N' : 'Grand Central',
            'S' : 'Times Square'}, 

    't' : {'S' : 'Hanover Square',
           'N' : '125th Street'},
    'v' : {'S' : 'Second Avenue',
           'N' : '71st Street'},
    'w' : {'S' : 'Whitehall Street',
           'N' : 'Ditmars Boulevard'},
    'z' : {'N' : 'Jamaica Center',
           'S' : 'Broad Street'},
}

rename_subway_stops = {
    '110TH STREET-BWAY' : 'CATHEDRAL PKY',
    '42ND ST.-TIMES SQ.' : 'TIMES SQ',
    'PELHAM BAY PKWY.' : 'PELHAM PKY',
    'EAST 238TH STREET' : 'NEREID AVE',
    'ST. LAWRENCE AVENUE' : 'ST LAWRENCE AVE',
    'SOUNDVIEW AVENUE' : 'MORRISON AVE',
    '138TH ST. THIRD AVENUE' : '3RD AVE',
    'HUNTERS POINT AVENUE' : 'HUNTERSPOINT AVE',
    'TIMES SQUARE QUEENS' : 'TIMES SQ',
    'HOYT STREET-SCH' : 'HOYT-SCHERMERHORN STS',
    'BROADWAY JUNCTION-ENY' : 'BROADWAY-EAST NEW YORK',
    'BROADWAY-NASSAU' : 'BROADWAY-NASSAU ST',
    'WEST 4 ST-UPPER LEVEL' : 'W 4TH ST',
    'WEST 4 ST-LOWER LEVEL' : 'W 4TH ST',
    'MOTT AVENUE  FAR ROCKAWAY' : 'FAR ROCKAWAY',
    '9TH STREET' : '9TH ST',
    '25TH STREET' : '25TH ST',
    '25 AVENUE' : '25TH AVE',
    'NINTH AVENUE' : '9TH AVE',
    'NINTH AVE (WEST END)' : '9TH AVE',
    'BAY 50 STREET' : 'BAY 50TH ST',
    'STILLWELL AVE.  C.I.' : 'CONEY ISLAND',
    'FORT HAMILTON PKWAY' : 'FT HAMILTON PKY',
    'FORT HAMILTON PKWY.' : 'FORT HAMILTON PKY',
    'VAN WYCK-JAMAICA' : 'JAMAICA-VAN WYCK',
    'UNION TURNPIKE' : 'UNION TPKE',
    'PARSONS-ARCHER' : 'JAMAICA CENTER/ PARSONS ARCHER',
    'SECOND AVENUE' : '2ND AVE',
    'DELANCY STREET' : 'DELANCEY ST', #thanks, MTA
    'EAST BROADWAY' : 'EAST BROADWAY', 
    '4TH AVENUE' : '4TH AVE',
    '22 AVENUE-BAY PARKWAY' : 'BAY PKY',
    'VAN SICKLEN AVENUE (CULVER)' : 'NEPTUNE AVE',
    'BOTANIC GARDENS-E PKWY' : 'BOTANIC GARDEN',
    'ELDERTS LANE' : '75TH ST-ELDERT LN',
    'BROADWAY JUNCTION-EPY' : 'EASTERN PKY',
    'GATES AVENUE' : 'GATES ST',
    'BROADWAY-MYRTLE' : 'MYRTLE AVE',
    'BROADWAY JUNCTION' : 'BROADWAY JCT',
    'BUSHWICK AVENUE' : 'BUSHWICK-ABERDEEN',
    'BEVERLEY ROAD' : 'BEVERLY RD',
    
}

abbreviations = {
    "STATION" : "",
    "SQUARE" : "SQ",
    "STREET" : "ST",
    " ROAD" : " RD",
    "AVENUE" : "AVE",
    "PLAZA" : "PLZ",
    "WEST " : "W ",
    "EAST " : "E ",
    "PARKWAY" : "PKY",
    "PLACE" : "PL",
    "BOULEVARD" : "BLVD",
    "BURHE" : "BUHRE", #it's misspelled somewhere
    "HIGHWAY" : "HWY",

}

addl_lines = {
    "4" : "6",
    "A" : "C",
    "D" : "R",
    "N" : "R",
    "E" : "FV",


}


stop_id_to_gid = {
    '201' : 64,
    '503' : 67,
    '208' : 59,
    '504' : 56,
    '211' : 66,
    '415' : 126,
    'D14' : 255,
    'D25' : 383,
    'R36' : 406,
    'B14' : 416,
    'B17' : 419,
    'B20' : 422,
    'G06' : 464,
    'F09' : 258,
    'F11' : 257,
    'F12' : 256,
    'B08' : 466,
    'D18' : 294,
    'D19' : 293,
    'S01' : 224,
    'M21' : 305,
    'N10' : 434,
    'N06' : 430,
    'N04' : 428,
    'N03' : 427,
    'N02' : 426,
    'R23' : 373,
    'Q01' : 380,
    'R21' : 371,
    'R06' : 357,
    'R05' : 358,


}

def handle_subway(dirname):

    feed = transitfeed.Loader("mta_data/subway-gtfs.zip", memory_db=False).Load() #base data

    dow_num_to_service_period = {'1' : 'WD',
                                 '2' : 'SAT',
                                 '3' : 'SUN'}

    for route_rec in parse_schedule_dir(os.path.join(dirname, 'rail-subway'), 'rtif'):
        route_rec['day_of_week'] = dow_num_to_service_period[route_rec['day_of_week']]

        period = feed.GetServicePeriod(route_rec['day_of_week'])
        route_id = route_rec['line']
        try:
            route = feed.GetRoute(route_id)
        except KeyError:
            route = transitfeed.Route(route_id=route_id,
                                      short_name=route_id,
                                      route_type="Subway")
            feed.AddRouteObject(route)
            feed.AddFareRuleObject(transitfeed.FareRule("regular", route_id))


        stops_by_id = {}
        for stop in route_rec['stops']:
            stop_id = stop['location_id']
            stops_by_id[stop_id] = stop

        for trip in route_rec['subway_trips']:
            line_name = trip['line_name'][-1:] #GS -> S

            if not line_name:
                continue # a bogus trip

            if line_name == '2':
                if 'NOSTRAND AVE.' in [stops_by_id[stop['stop_id']]['full_name'] for stop in trip['stops']]:

                    #the 2 train, as far as I can tell, does not
                    #actually run on the 3/4 track in Brooklyn.
                    continue

            direction = trip['direction']
            headsign = subway_headsign[route_id][direction] #fixme: depends on actual destination of train
            gtfs_trip = route.AddTrip(feed, headsign, service_period=period)
            for tripstop in trip['stops']:

                if tripstop['is_real_stop'] != 'S':
                    continue

                if tripstop['stop_id'] == '138':
                    #Cortland St
                    continue

                stop_id = tripstop['stop_id']
                if stop_id in feed.stops:
                    gtfs_stop = feed.GetStop(stop_id)
                else:
                    stop = stops_by_id[stop_id]

                    #first, the table
                    translated_full_name = stop['full_name']
                    #remove anything following a dot or a dash or an open paren                    
                    for endchar in ['.','-','(','  ']:
                        if endchar in translated_full_name:
                            translated_full_name = translated_full_name[:translated_full_name.index(endchar)]

                    #abbreviations
                    for long, abbreviated in abbreviations.items():
                        translated_full_name = translated_full_name.replace(long, abbreviated)


                    translated_full_name = translated_full_name.strip()
                    translated_full_name = translated_full_name.replace("  ", " ")


                    number_st_re = re.compile('^(\d+)')
                    number_st = number_st_re.match(translated_full_name)
                    is_num = False
                    if number_st:
                        translated_full_name = number_st.group(1)
                        is_num = True

                    translated_full_name = rename_subway_stops.get(stop['full_name'], translated_full_name
)
                    possible_stops = MTASubwayStop.objects.filter(routes__contains=line_name, facility__contains=translated_full_name)


                    #the A makes C stops late at night
                    if line_name in addl_lines:
                        possible_stops = list(possible_stops)

                        for addl_line in addl_lines[line_name]:
                            addl_possible_stops = MTASubwayStop.objects.filter(routes__contains=addl_line, facility__contains=translated_full_name)
                            for addl_stop in addl_possible_stops:
                                if not addl_stop in possible_stops:
                                    possible_stops.append(addl_stop)

                    #hard coded stop id
                    if stop_id in stop_id_to_gid:
                        possible_stops = MTASubwayStop.objects.filter(gid = stop_id_to_gid[stop_id])

                    if is_num:
                        #we need to make sure our search for 23rd st doesn't
                        #bring up 232nd st.
                        new_possible_stops = []
                        num_re = re.compile("(^|\D)" + translated_full_name + "($|\D)")
                        for possible_stop in possible_stops:
                            if num_re.search(possible_stop.facility):
                                new_possible_stops.append(possible_stop)
                        possible_stops = new_possible_stops


                    if len(possible_stops) == 0:
                        print "no stops for %s on the %s (translated to %s)" % (stop['full_name'], line_name, translated_full_name)
                        print "possible stops are %s" % sorted([s.facility for s in MTASubwayStop.objects.filter(routes__contains=line_name)])
                        import pdb;pdb.set_trace()
                        continue
                    elif len(possible_stops) > 1:
                        print "too many stops for %s on the %s (translated to %s): %s" % (stop['full_name'], line_name, translated_full_name, [(s.facility, s.gid, s.routes) for s in possible_stops])
                        import pdb;pdb.set_trace()
                        continue
                    else:
                        dbstop = possible_stops[0]

                    gtfs_stop = transitfeed.Stop(
                        lng=dbstop.the_geom.x,
                        lat=dbstop.the_geom.y,
                        stop_id=stop_id,
                        name=dbstop.facility
                        )
                    feed.AddStopObject(gtfs_stop)            

                stop_time = google_time_from_centiminutes(tripstop['stop_time'])
                gtfs_trip.AddStopTime(gtfs_stop, stop_time=stop_time)

    feed.WriteGoogleTransitFeed('mta_data/subway.zip')

def handle_buses(dirname):

    feed = transitfeed.Loader("mta_data/bus-gtfs.zip", memory_db=False).Load() #base data
    current_borough = None

    #capture multiple stops with different box ids
    stop_name_to_stop = {}

    last_route = None
    for route_rec in parse_schedule_dir(os.path.join(dirname, 'surface-bus'), 'stif'):
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

            if nearest and abs(nearest.stop_lat - lat) + abs(nearest.stop_lon - lng) < 0.000001:
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
            extra = extra_names[name]
            if isinstance(extra, str):
                names.add(extra)
            else:
                names.update(extra)

        for trip_rec in route_rec['trips']:
            route_name = trip_rec['route_name']
            names.add(route_name)

        nameq = models.Q(route = name)
        for rname in names:
            rname = fix_leading_zeros.get(rname, rname)
            nameq |= models.Q(route__iexact = rname)

            if rname in extra_names:
                extra = extra_names[rname] 
                if isinstance(extra, str):
                    if extra not in names:
                        nameq |= models.Q(route__iexact = extra_names[rname])
                else:
                    for rname in extra:
                        if rname not in names:
                            nameq |= models.Q(route__iexact = extra_names[rname])
        shapes = list(MTABusRoute.objects.filter(nameq))

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
            trip_route_name = rename_routes.get(trip_rec['route_name'], trip_rec['route_name'])
            direction = trip_rec['direction']
            if trip_route_name in fix_direction:
                direction = fix_direction[trip_route_name].get(direction, direction)
            shapes = shapes_by_direction.get(direction)

            shape = find_shape_by_stops(feed, shapes, stops, 'bus_route_table')
            if shape:
                trip.shape_id = shape.shape_id

    feed.Validate()
    feed.WriteGoogleTransitFeed('mta_data/bus-%s.zip' % current_borough)

class Command(BaseCommand):
    """Transform mta schedule and route data to GTFS.  Assume route data is 
    truth for matters of directionality"""

    def handle(self, dirname, bus_route_table_name, subway_route_table_name = None, subway_stop_table_name = None, **kw):

        MTABusRoute._meta.db_table = bus_route_table_name
        if subway_route_table_name:
            MTASubwayRoute._meta.db_table = subway_route_table_name
            MTASubwayStop._meta.db_table = subway_stop_table_name

        init_q48()

        save_base_gtfs("./mta_data")

        try:
            if subway_route_table_name:
                handle_subway(dirname)
            #handle_buses(dirname)

        except Exception, e:
            import traceback
            traceback.print_exc()
            import pdb;pdb.set_trace()
            raise
