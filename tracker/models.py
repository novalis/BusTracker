from datetime import datetime, timedelta
from django.contrib.gis.db import models
from math import sqrt
from mta_data.models import *

class Bus(models.Model):
    """A particular physical bus"""
    id = models.IntegerField(primary_key=True)
    route = models.ForeignKey(Route) #the route it is traveling on (if any)
    trip = models.ForeignKey(Trip)
    total_dwell_time = models.IntegerField(default=0)
    n_dwells = models.IntegerField(default=0)

    def average_dwell_time(self):
        if self.n_dwells:
            return self.total_dwell_time / self.n_dwells
        else:
            return -1

    def __unicode__(self):
        return "<Bus (%d) on route %s %s>" % (self.id, self.route.name, self.route.direction)

    @property
    def location(self):
        last = self.busobservation_set.order_by('-time')[0]
        return last.location

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
        target_distance = distance_along_route(target_location, self.route)

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

        if last_distance - start_distance < 0.1 or last_time <= start_time:
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


def distance_along_route(location, route):
    from django.db import connection
    cursor = connection.cursor()
    location = "SRID=4326;POINT(%s %s)" % (location.x, location.y)
    cursor.execute(
"""SELECT st_line_locate_point(mta_data_route.geometry, %s) 
FROM 
mta_data_route
WHERE 
mta_data_route.gid = %s""", (location, route.gid))
    row = cursor.fetchone()
    return row[0]
        


class BusObservationManager(models.GeoManager):
    def get_query_set(self):
        return super(BusObservationManager, self).get_query_set().extra(select={
            'distance': """
SELECT st_line_locate_point(route.geometry, %s.location) 
FROM 
tracker_bus as bus, 
mta_data_route as route
WHERE 
%s.bus_id = bus.id AND
bus.route_id = route.gid
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
        return distance_along_route(self.location, self.bus.route)



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
        return distance_along_route(self.location, self.bus.route)
