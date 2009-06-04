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

    for gtfs_trip in gtfs_route.trips:
        route = list(Route.objects.filter(gid=gtfs_route.route_id))
        if route:
            route = route[0]
        else:
            shape = feed.GetShape(gtfs_trip.shape_id)
            geometry = LineString([point[:2] for point in shape.points])
            route = Route(gid = gtfs_route.route_id,
                          name = name, 
                          geometry = geometry,
                          headsign = long_name,
                          direction = direction)
            route.save()

        stop_times = gtfs_trip.GetStopTimes()
        start = stop_times[0].arrival_secs
        hours = start / 3600
        minutes = (start / 60) % 60
        seconds =  (start / 3600) % 60
        day_later = False
        if hours >= 24:
            hours -= 24
            start -= 86400
            day_later = True

        start_time = time(hours, minutes, seconds)
        trip = list(Trip.objects.filter(route=route, day_of_week=gtfs_trip.service_id, start_time=start_time))
        if trip:
            trip = trip[0]
        else:
            trip = Trip(route=route, day_of_week=gtfs_trip.service_id, start_time=start_time)
            trip.save()
        start = start
        for stop_time in stop_times:
            stop = stop_time.stop
            bus_stop = BusStop(box_no = stop_time.stop_id, 
                               location=stop.stop_name,
                               geometry=Point(stop.stop_lon, stop.stop_lat))
            bus_stop.save()
            cursor = connection.cursor()
            #fixme: is there any way to just pass the stop's geometry
            #directly?
            location = "SRID=4326;POINT(%s %s)" % (stop.stop_lon,
                                                   stop.stop_lat)
            sql = """SELECT st_line_locate_point(geometry, %s) 
        FROM 
        mta_data_route
        WHERE 
        gid = %s"""
            cursor.execute(sql, (location, route.gid))
            row = cursor.fetchone()
            distance = row[0]
            arrival_secs = stop_time.arrival_secs
            if day_later:
                arrival_secs -= 86400
            ts = TripStop(trip = trip, 
                          seconds_after_start = arrival_secs - start,
                          bus_stop = bus_stop, distance = distance)
            ts.save()

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
