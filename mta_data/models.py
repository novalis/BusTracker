from datetime import datetime, timedelta
from django.contrib.gis.db import models

class Route(models.Model):
    """A route (in one direction)"""
    name = models.CharField(max_length=7, primary_key=True) #borough, number, x?, space, direction
    geometry = models.GeometryField(null=True) #from MTA's shapefile
    objects = models.GeoManager()

    def __unicode__(self):
        return "'%s'" % self.name

class BusStop(models.Model):
    box_no = models.IntegerField(primary_key=True)
    location = models.CharField(max_length=44) 
    geometry = models.PointField()
    objects = models.GeoManager()

class Trip(models.Model):
    route = models.ForeignKey(Route)
    day_of_week = models.CharField(max_length=3) #sat, sun, wkd, xme, xmd, nye, nyd  (christmas eve, day, new year's eve, day)
    start_time = models.TimeField()

class TripStop(models.Model):
    trip = models.ForeignKey(Trip)
    time = models.TimeField()
    bus_stop = models.ForeignKey(BusStop)
    type = models.CharField(max_length=1) #D, T, or A for start, middle, and end stops


