from django.core.management.base import BaseCommand
from mta_data_parser import parse_schedule_dir
from mta_import import find_route_by_stops
import transitfeed


class Command(BaseCommand):
    """Import mta schedule and route data into DB.  Assume route data is 
    truth for matters of directionality"""

    def handle(self, dirname, **kw):

        feed = transitfeed.Loader("mta_data/gtfs.zip").Load() #base data

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

                if name == 'Q48':
                    print "Don't know how to handle loop routes yet"
                    continue


                #add the route itself
                route = feed.AddRoute(short_name=name, 
                                      long_name=route_rec["street_name"],
                                      route_type="Bus")


                #figure out the schedule
                #FIXME:WRONG
                schedule = route.GetSchedule(route_rec['day_of_week'])

                stop_hexid_to_stop = {}
                #add all stops
                for stop_rec in route_rec['stops']:
                    location = "%s at %s" % (stop_rec['street1'], stop_rec['street2'])
                    #check for duplicate box ids
                    box_no = stop_rec['box_no']
                    if location in stop_name_to_id:
                        box_no = stop_name_to_id[location]
                    else:
                        stop_name_to_id[location] = box_no

                    #now, try to find a nearby stop

                    lat = stop_rec['latitude'] / 1000000.0
                    lng = stop_rec['longitude'] / 1000000.0

                    nearest = feed.GetNearestStops(lat, lng, 1)
                    if len(nearest):
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
                    headsign = headsigns[trip_rec['headsign_id']]
                    trip = route.AddTrip(schedule, 
                                         headsign=headsign)
                    for tripstop_rec in trip_rec['stops']:
                        stop_id = tripstop_rec['stop_id']
                        stop_time = time_from_centiminutes(tripstop_rec['minutes'])
                        trip.AddStopTime(stop_hexid_to_stop[stop_id], 
                                         stop_time=stop_time)

            schedule.Validate()
            schedule.WriteGoogleTransitFeed('mta_data/out.zip')
        except Exception, e:
            import traceback
            traceback.print_exc()
            import pdb;pdb.set_trace()
            raise
