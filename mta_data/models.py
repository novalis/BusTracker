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
    objects = models.GeoManager()

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

class TripStop(models.Model):
    trip = models.ForeignKey(Trip)
    seconds_after_start = models.IntegerField()
    bus_stop = models.ForeignKey(BusStop)
    type = models.CharField(max_length=1) #D, T, or A for start, middle, and end stops


