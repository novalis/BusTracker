from datetime import datetime, timedelta
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point
from django.utils.datastructures import SortedDict
from math import sqrt
from mta_data.models import *

class Bus(models.Model):
    """A particular physical bus"""
    id = models.IntegerField(primary_key=True)
    trip = models.ForeignKey(Trip)
    next_stop = models.ForeignKey(TripStop)
    distance = models.FloatField() #nondescending

    def __unicode__(self):
        return "<Bus (%d) on route %s %s>" % (self.id, self.trip.route.name, self.trip.route.direction)

    @property
    def location(self):
        last = self.busobservation_set.order_by('-time')[0]
        return last.location_on_route()

    def location_on_route(self):
        from django.db import connection
        from django.contrib.gis.geos import fromstr
        cursor = connection.cursor()
        location = "SRID=4326;POINT(%s %s)" % (location.x, location.y)
        cursor.execute(
            """SELECT st_line_interpolate_point(mta_data_shape.geometry,%s)
FROM 
mta_data_shape
WHERE 
mta_data_shape.gid = %s""", (self.distance, self.trip.shape.gid))
        row = cursor.fetchone()
        point = fromstr(row[0])
        return point

    def estimated_arrival_time2(self, target_bus_stop, time=None):
        #compute estimated arrival time based on schedule

        if not time:
            now = datetime.utcnow()
        else:
            now = time

        start_datetime = self.trip.start_datetime_relative_to(now)
        seconds_traveled = (now - start_datetime).seconds

        tripstop = self.trip.tripstop_set.get(busstop_id=target_bus_stop.id)
        target_distance = tripstop.distance

        for busstop in self.trip.tripstop_set.order_by('-distance'):
            if busstop.distance <= target_distance:
                break # last stop we passed

        scheduled_time = busstop.seconds_after_start
        delay = bus.previousstop_set.filter(arrival_time__lte=now).order_by('id').lateness
        return start_date_time + timedelta(0, scheduled_time + lateness)

    def estimated_arrival_time(self, target_location, time=None):
        """target_location is a Point"""
        #estimated arrival time is a function of average speed in
        #decimal degrees per second, remaining distance, average speed
        #in number of intersections per second, and remaining
        #intersections.

        if not time:
            now = datetime.utcnow()
        else:
            now = time

        #The target location is a point, but needs to be a distance along the route.
        target_distance = distance_along_route(target_location, self.trip.shape)

        #Find out when the bus started moving.
        #This is when the distance along the route (a) is > 0.01
        observations = self.busobservation_set.filter(time__lte = now).order_by('time')

        start_distance = None
        for observation in observations:
            if not start_distance:
                start_distance = observation.distance
                continue
            if observation.distance - start_distance > 0.01:
                start_location, start_distance, start_time = observation.location, observation.distance, observation.time
                break
        else:
            #the bus has not yet moved
            return None

        #The bus's last observed distance
        last = observations.order_by('-time')[0]
        last_distance, last_time = last.distance, last.time

        if last_distance - start_distance < 0.02 or last_time <= start_time:
            #the bus has not moved enough or has moved backwards
            #this means no arrival estimate is possible for this bus.
            return None

        journey_time = (last_time - start_time).seconds
        rate = (last_distance - start_distance) / journey_time
        d = target_distance - last_distance

        estimate_from_distance = d / rate

        seconds = estimate_from_distance
        return last_time + timedelta(0, seconds)

class PreviousStop(models.Model):
    tripstop = models.ForeignKey(TripStop)
    arrival_time = models.DateTimeField()
    lateness = models.IntegerField() # seconds after scheduled arrival time
    bus = models.ForeignKey(Bus)

def distance_along_route(location, shape):
    from django.db import connection
    cursor = connection.cursor()
    location = "SRID=4326;POINT(%s %s)" % (location.x, location.y)
    cursor.execute(
"""SELECT st_line_locate_point(mta_data_shape.geometry, %s) 
FROM 
mta_data_shape
WHERE 
mta_data_shape.gid = %s""", (location, shape.gid))
    row = cursor.fetchone()
    return row[0]

# Return the point along shape that is closest to location
def location_on_route(location, shape):
    from django.db import connection
    from django.contrib.gis.geos import fromstr
    cursor = connection.cursor()
    location = "SRID=4326;POINT(%s %s)" % (location.x, location.y)
    cursor.execute(
"""SELECT st_line_interpolate_point(mta_data_shape.geometry,
st_line_locate_point(mta_data_shape.geometry, %s))
FROM 
mta_data_shape
WHERE 
mta_data_shape.gid = %s""", (location, shape.gid))
    row = cursor.fetchone()
    point = fromstr(row[0])
    return point

# TODO: Figure out where this belongs.
def point_on_route_by_distance(distance, shape):
    from django.db import connection
    from django.contrib.gis.geos import fromstr
    cursor = connection.cursor()
    cursor.execute(
"""SELECT st_line_interpolate_point(mta_data_shape.geometry, %s)
FROM
mta_data_shape
WHERE
mta_data_shape.gid = %s""", (distance, shape.gid))
    row = cursor.fetchone()
    point = fromstr(row[0])
    return point

def next_stop_by_distance(distance, trip):
    next = trip.tripstop_set.filter(distance__gt=distance).order_by('distance')[:1]
    if not next:
        return None
    return next[0]

class BusObservationManager(models.GeoManager):
    def get_query_set(self):
        return super(BusObservationManager, self).get_query_set().extra(select={
            'distance': """
SELECT st_line_locate_point(shape.geometry, %s.location) 
FROM 
tracker_bus as bus, 
mta_data_trip as trip, 
mta_data_shape as shape
WHERE 
%s.bus_id = bus.id AND
bus.trip_id = trip.id AND
trip.shape_id = shape.gid
""" % (self.model._meta.db_table,
       self.model._meta.db_table)})




class BusObservation(models.Model):
    """A GPS observation of a bus"""
    objects = BusObservationManager()
    bus = models.ForeignKey(Bus)
    location = models.PointField()
    distance = models.FloatField(null=True, db_index=True)
    time = models.DateTimeField()

    #extra GPS fields
    course = models.FloatField(null=True)
    speed = models.FloatField(null=True)
    altitude = models.FloatField(null=True)
    horizontal_accuracy = models.FloatField(null=True)
    vertical_accuracy = models.FloatField(null=True)

    class Meta:
        unique_together = ('bus', 'time')
        ordering = ["time"]

    def save(self):
        if not self.distance:
            self.distance = self.distance_along_route()
        super(BusObservation, self).save()


    def __unicode__(self):
        return "%s at %s at %s" % (self.bus, self.location, self.time)

    def distance_along_route(self):
        return distance_along_route(self.location, self.bus.trip.shape)

    def location_on_route(self):
        return location_on_route(self.location, self.bus.trip.shape)



class IntersectionObservation(models.Model):
    """A human observation of a bus"""
    objects = BusObservationManager()
    bus = models.ForeignKey(Bus)
    location = models.PointField()
    time = models.DateTimeField()
    intersection = models.CharField(max_length=120)
    distance = models.FloatField(null=True)

    class Meta:
        ordering = ["time"]

    def __unicode__(self):

        return "%s at %s at %s" % (self.bus, self.location, self.time)

    def save(self):
        if not self.distance:
            self.distance = self.distance_along_route()
        super(IntersectionObservation, self).save()

    def distance_along_route(self):
        return distance_along_route(self.location, self.bus.trip.shape)

    def location_on_route(self):
        return self.location

def apply_observation(lat, lon, time, bus_id, route, intersection=None, request={}):
    #figure out what trip we are on by assuming it is the trip
    #starting closest to here and now.

    bus_candidates = (Bus.objects.filter(id=bus_id)[:1])

    location = Point(lon, lat)

    if len(bus_candidates):
        bus = bus_candidates[0]
        trip = bus.trip
        distance = distance_along_route(location, trip.shape)
        if distance > bus.distance:
            bus.distance = distance
    else:
        location_sql = "SRID=4326;POINT(%s %s)" % (lon, lat)

        day_of_week = ScheduleDay.objects.get(day=time.date()).day_of_week
        trip = Trip.objects.filter(route=route, day_of_week=day_of_week).extra(
            tables=['mta_data_shape'],
            select = SortedDict([
                    ('start_error', 'abs(extract(epoch from start_time - %s))'),
                    ('shape_error', 'st_distance(st_startpoint(mta_data_shape.geometry), %s)')
                    ]),
            select_params = (time.time(), location_sql)
            ).order_by('start_error')[0] # fixme (should order by both shape and start error)

        start_datetime = trip.start_datetime_relative_to(time)
        lateness = (time - start_datetime).seconds

        distance = distance_along_route(location, trip.shape)
        next_stop = trip.tripstop_set.all()[0]
        bus = Bus(id=bus_id, trip=trip, next_stop=next_stop, distance=distance)
        bus.save()

    if intersection:
        obs = IntersectionObservation(bus=bus, location=location, time=time, intersection=intersection)
        obs.save()
    else:
        if BusObservation.objects.filter(bus=bus,time=time).count():
            #time is unique -- more than one observation per second is no good.
            return

        start_datetime = trip.start_datetime_relative_to(time)

        while distance > bus.next_stop.distance:            

            expected_time = start_datetime + timedelta(0, bus.next_stop.seconds_after_start)
            lateness = time - expected_time
            PreviousStop(tripstop=bus.next_stop,
                         arrival_time=time,
                         lateness=lateness,
                         bus=bus)

            next_stop = TripStop.objects.filter(trip=trip, seconds_after_start__gt = bus.next_stop.seconds_after_start)[:1]

            if next_stop:
                bus.next_stop = next_stop[0]
            else:
                import pdb;pdb.set_trace()
                

        if bus.previousstop_set.count() == 0:
            #check if we have passed the initial stop
            if distance > 0.01: # a huge hack!
                arrival_time = time - timedelta(0, 30)
                seconds_traveled = (arrival_time - trip.start_datetime_relative_to(time)).seconds
                PreviousStop(tripstop=trip.tripstop_set.get(distance=0),
                             arrival_time=arrival_time,
                             lateness=seconds_traveled,
                             bus=bus)

        extra_field_names = ['speed', 'course', 'horizontal_accuracy', 'vertical_accuracy', 'altitude']
        extra_fields = {}
        for x in extra_field_names:
            value = request.get(x)
            if not value:
                continue
            try:
                value = float(value)
                extra_fields[x] = value
            except ValueError:
                continue

        obs = BusObservation(bus=bus, location=location, time=time, **extra_fields)

        obs.save()
