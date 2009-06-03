from datetime import time
from django.contrib.gis.geos import LineString, Point
from django.core.management.base import BaseCommand
from django.db import transaction, connection
from mta_data.models import *

import transitfeed

def process_route(feed, gtfs_route):
    direction = gtfs_route.route_long_name[-1]
    long_name = gtfs_route.route_long_name[:-2] #chop off direction
    name = gtfs_route.route_short_name

    for trip in gtfs_route.trips:
        route = list(Route.objects.filter(gid=gtfs_route.route_id))
        if route:
            route = route[0]
        else:
            shape = feed.GetShape(trip.shape_id)
            geometry = LineString([point[:2] for point in shape.points])
            route = Route(gid = gtfs_route.route_id,
                          name = name, 
                          geometry = geometry,
                          headsign = long_name,
                          direction = direction)
            route.save()

        import pdb;pdb.set_trace()
        trip = Trip(route=route, day_of_week=trip.service_id, start_time=trip.stops[0].stop_time)
        trip.save()
        start = trip.stops[0].stop_time
        for stop in trip.stops:
            print stop
            import pdb;pdb.set_trace()
            #bus_stop = BusStop(box_no = stop.box_id, location=stop.location,
            #                   geometry=x)

            from django.db import connection
            cursor = connection.cursor()
            #fixme: is there any way to just pass the stop's geometry
            #directly?
            location = "SRID=4326;POINT(%s %s)" % (stop.stop_lon,
                                                   stop.stop_lat)
            sql = """SELECT st_line_locate_point(the_geom, %%s) 
        FROM 
        mta_data_route
        WHERE 
        gid = %%s""" % table_name
            cursor.execute(sql, (location, route.gid))
            row = cursor.fetchone()
            distance = row[0]
            TripStop(trip = trip, seconds_after_start = stop.stop_time - start,
                     bus_stop = bus_stop, distance = distance)


class Command(BaseCommand):
    """Import mta schedule and route data from GTFS into DB."""

    @transaction.commit_manually
    def handle(self, gtfs_file, **kw):
        try:
            feed = transitfeed.Loader(gtfs_file, memory_db=True).Load()

            for stop_id, stop in feed.stops.items():
                bus_stop = BusStop(box_no=stop_id, location=stop.stop_name,
                                   geometry=Point(stop.stop_lat, stop.stop_lon))
            transaction.commit()
            for route_id, route in sorted(feed.routes.items()):
                process_route(feed, route)
                transaction.commit()
        except Exception, e:
            import traceback
            traceback.print_exc()
            import pdb;pdb.set_trace()
            raise
