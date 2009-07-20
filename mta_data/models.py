from datetime import datetime, timedelta
from django.contrib.gis.db import models

class Route(models.Model):
    """A route (in one direction)"""
    gid = models.CharField(primary_key=True, max_length=64) #the GTFS id for this route
    name = models.CharField(max_length=5) #borough, number
    direction = models.CharField(max_length = 1) #NSEW
    headsign = models.CharField(max_length = 64, null=True)

    class Meta:
        ordering = ["name", "direction", "headsign"]

    def route_name(self):
        return "%s %s" % (self.name, self.direction)

    def route_full_name(self):
        return "%s %s %s" % (self.name, self.direction, self.headsign)

    def __unicode__(self):
        return "'%s'" % self.name

class Shape(models.Model):
    gid = models.CharField(primary_key=True, max_length=64) #the GTFS id for this shape
    geometry = models.GeometryField() 
    length = models.FloatField(null=True)
    objects = models.GeoManager()

    def save(self):
        if not self.length:
            self.length = self.geometry.length
        super(Shape, self).save()

class BusStop(models.Model):
    box_no = models.IntegerField(primary_key=True)
    location = models.CharField(max_length=48) 
    geometry = models.PointField()
    objects = models.GeoManager()

class Trip(models.Model):
    route = models.ForeignKey(Route)
    shape = models.ForeignKey(Shape)
    #day_of_week values are sat, sun, wko, wkc, xme, xmd, nye, nyd:
    #weekday when school is open, weekday when school is closed,
    #christmas eve, day, new year's eve, day
    day_of_week = models.CharField(max_length=3)
    start_time = models.TimeField()
    
    class Meta:
        unique_together = ('route', 'shape', 'start_time', 'day_of_week')

    def __unicode__(self):
        return "%s for %s starting at %s" % (unicode(self.route), self.day_of_week, self.start_time)

    def start_datetime_relative_to(self, dt):
        start_time = self.start_time
        start_datetime = datetime(dt.year, dt.month, dt.day,
                                  start_time.hour, start_time.minute, start_time.second)


        if start_datetime > dt:
            difference = (start_datetime - dt).seconds
            if difference > 12 * 60 * 60:
                start_datetime -= timedelta(1)
        else:
            difference = (dt - start_datetime).seconds
            if difference < -12 * 60 * 60:
                start_datetime += timedelta(1)
        return start_datetime


def distance_along_shape(location, shape):
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

class TripStop(models.Model):
    class Meta:
        ordering = ["seconds_after_start"]

    trip = models.ForeignKey(Trip)
    seconds_after_start = models.IntegerField()
    bus_stop = models.ForeignKey(BusStop)
    type = models.CharField(max_length=1) #D, T, or A for start, middle, and end stops
    distance = models.FloatField(null=True)

    def save(self):
        if not self.distance:
            self.distance = self.distance_along_shape()
        super(TripStop, self).save()


    def __unicode__(self):        
        return "%s on %s at %s" % (self.bus_stop.geometry, unicode(self.trip), self.seconds_after_start)

    def distance_along_shape(self):
        return distance_along_shape(self.bus_stop.geometry, self.trip.shape)

    def datetime_relative_to(self, dt):
        start_datetime = self.trip.start_datetime_relative_to(dt)
        
        return start_datetime + timedelta(0, self.seconds_after_start)
        

class ScheduleDay(models.Model):
    day = models.DateField(primary_key=True)
    day_of_week = models.CharField(max_length=3)
