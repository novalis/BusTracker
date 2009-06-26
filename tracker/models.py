from datetime import datetime, timedelta
from django.contrib.gis.db import models
from math import sqrt
from mta_data.models import *

class Bus(models.Model):
    """A particular physical bus"""
    id = models.IntegerField(primary_key=True)
    trip = models.ForeignKey(Trip)
    total_dwell_time = models.IntegerField(default=0)
    n_dwells = models.IntegerField(default=0)

    def average_dwell_time(self):
        if self.n_dwells:
            return self.total_dwell_time / self.n_dwells
        else:
            return -1

    def __unicode__(self):
        return "<Bus (%d) on route %s %s>" % (self.id, self.trip.route.name, self.trip.route.direction)

    @property
    def location(self):
        last = self.busobservation_set.order_by('-time')[0]
        return last.location

    def location_on_route(self):
        last = self.busobservation_set.order_by('-time')[0]
        return last.location_on_route()

    def estimated_arrival_time(self, target_location, time=None):
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

        #todo: create an estimate from dwell time

        #I guess that's average dwell time * n of remaining stops, plus
        #some fudge factor for travel time

        seconds = estimate_from_distance
        return last_time + timedelta(0, seconds)


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

    class Meta:
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

