from django.core.management.base import BaseCommand
from mta_data_parser import parse_schedule_dir
from mta_import import find_route_by_stops, time_from_centiminutes
import transitfeed

def google_time_from_centiminutes(centiminutes):
    #the MTA's day is longer than 24 hours, but that needn't bother us
    #so long as we are sure never to use absolute times any time
    #subtraction might be required
    hours = (centiminutes / 6000)
    minutes = (centiminutes % 6000) / 100

    seconds = ((centiminutes % 6000) - minutes * 100) * 60 / 100
    return "%02d:%02d:%02d" % (hours, minutes, seconds)

rename_location = {
'BROADWAY at 207 ST' : 'BROADWAY at W 207 ST',
'NARROWS ROAD S at FINGERBOARD ROAD' : 'NARROWS RD S at FINGERBOARD RD',
'NARROWS RD S at FINGERBOARD ROAD' : 'NARROWS RD S at FINGERBOARD RD',
'NARROWS ROAD S at FINGERBOARD RD' : 'NARROWS RD S at FINGERBOARD RD',
}

def route_for_trip(feed, name, trip_rec, headsign):
    route_id = trip_rec['headsign_id']

    if route_id in feed.routes:
        return feed.routes[route_id]

    #create the route
    long_name = headsign + ' ' + trip_rec['direction']
    route = transitfeed.Route(route_id=route_id,
                             short_name=name, 
                             long_name=long_name,
                             route_type="Bus")
    feed.AddRouteObject(route)
    return route

class Command(BaseCommand):
    """Import mta schedule and route data into DB.  Assume route data is 
    truth for matters of directionality"""

    def handle(self, dirname, **kw):

        feed = transitfeed.Loader("mta_data/gtfs.zip", memory_db=False).Load() #base data

        try:
            #capture multiple stops with different box ids
            stop_name_to_id = {}

            for route_rec in parse_schedule_dir(dirname):

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
                    if location in stop_name_to_id:
                        box_no = stop_name_to_id[location]
                    else:
                        stop_name_to_id[location] = box_no

                    #now, try to find a nearby stop

                    lat = stop_rec['latitude'] / 1000000.0
                    lng = stop_rec['longitude'] / 1000000.0

                    #not in NYC area
                    if not (-72 > lng > -75) or not (41 > lat > 39):
                        print "bad lat, lng", lat, lng
                        import pdb;pdb.set_trace()
                        

                    nearest = feed.GetNearestStops(lat, lng, 1)
                    if len(nearest) and not ' LANE ' in nearest[0].stop_name:
                        #sometimes bus stops really are like 1 m away because 
                        #they are two lanes in a multilane terminal area
                        nearest = nearest[0]
                    else:
                        nearest = None

                    if nearest and abs(nearest.stop_lat - lat) + abs(nearest.stop_lon - lng) < 0.00001:
                        stop_hexid_to_stop[stop_rec['stop_id']] = nearest
                    else:
                        stop = transitfeed.Stop(
                                lng=lng,
                                lat=lat,
                                stop_id=box_no,
                                name=location
                                )
                        feed.AddStopObject(stop)
                        stop_hexid_to_stop[stop_rec['stop_id']] = stop
            
                #figure out headsigns

                headsigns = dict((sign['headsign_id'], sign['headsign']) for sign in route_rec['headsigns'])

                #now trips
                for trip_rec in route_rec['trips']:
                    if trip_rec['UNKNOWN_1'].startswith('-'):
                        #these trips are bogus -- their stops are out-of-order.
                        continue
                    hid = trip_rec['headsign_id']
                    headsign = headsigns.get(hid, long_name)

                    route = route_for_trip(feed, name, trip_rec, headsign)

                    trip = route.AddTrip(feed, 
                                         headsign, 
                                         service_period=period)
                    for tripstop_rec in trip_rec['stops']:
                        stop_id = tripstop_rec['stop_id']
                        stop_time = google_time_from_centiminutes(tripstop_rec['minutes'])
                        trip.AddStopTime(stop_hexid_to_stop[stop_id], 
                                         stop_time=stop_time)

            feed.Validate()
            feed.WriteGoogleTransitFeed('mta_data/out.zip')
        except Exception, e:
            import traceback
            traceback.print_exc()
            import pdb;pdb.set_trace()
            raise
