from datetime import datetime, timedelta
from django.contrib.gis.db import models

class Route(models.Model):
    """A route (in one direction)"""
    gid = models.IntegerField(primary_key=True) #gid from shapefile
    name = models.CharField(max_length=5) #borough, number
    geometry = models.GeometryField() 
    direction = models.CharField(max_length = 1) #NSEW
    path = models.CharField(max_length = 2, null=True)
    headsign = models.CharField(max_length = 64, null=True)
    length = models.FloatField(null=True)
    objects = models.GeoManager()

    def save(self):
        if not self.length:
            self.length = self.geometry.length
        super(Route, self).save()

    def route_name(self):
        if self.path:
            return "%s %s %s" % (self.name, self.direction, self.path)
        else:
            return "%s %s" % (self.name, self.direction)

    def __unicode__(self):
        return "'%s'" % self.name

class BusStop(models.Model):
    box_no = models.IntegerField(primary_key=True)
    location = models.CharField(max_length=48) 
    geometry = models.PointField()
    objects = models.GeoManager()

class Trip(models.Model):
    route = models.ForeignKey(Route)
    #day_of_week values are sat, sun, wko, wkc, xme, xmd, nye, nyd:
    #weekday when school is open, weekday when school is closed,
    #christmas eve, day, new year's eve, day
    day_of_week = models.CharField(max_length=3)
    start_time = models.TimeField()
    
    class Meta:
        unique_together = ('route', 'start_time', 'day_of_week')

    def __unicode__(self):
        return "%s for %s starting at %s" % (unicode(self.route), self.day_of_week, self.start_time)

def distance_along_route(location, route):
    from django.db import connection
    cursor = connection.cursor()
    location = "SRID=4326;POINT(%s %s)" % (location.x, location.y)
    cursor.execute(
"""SELECT st_line_locate_point(mta_data_route.geometry, %s) 
FROM 
mta_data_route
WHERE 
mta_data_route.name = %s""", (location, route.name))
    row = cursor.fetchone()
    return row[0]

class TripStop(models.Model):
    trip = models.ForeignKey(Trip)
    seconds_after_start = models.IntegerField()
    bus_stop = models.ForeignKey(BusStop)
    type = models.CharField(max_length=1) #D, T, or A for start, middle, and end stops
    distance = models.FloatField(null=True)

    def save(self):
        if not self.distance:
            self.distance = self.distance_along_route()
        super(TripStop, self).save()


    def __unicode__(self):        
        return "%s on %s at %s" % (self.bus_stop.geometry, unicode(self.trip), self.seconds_after_stop)

    def distance_along_route(self):
        return distance_along_route(self.bus_stop.geometry, self.trip.route)


