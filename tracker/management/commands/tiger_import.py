#!/usr/bin/python
# Imports tiger data from the table provided on the command-line into the tracker tables.

from django.core.management.base import BaseCommand
from optparse import make_option, OptionParser
from tracker.models import *

import re

class Tiger(models.Model):
    """Tiger import burning bright, in the forests of the night..."""
    gid = models.IntegerField(primary_key=True)
    statefp = models.CharField(max_length=2)
    countyfp = models.CharField(max_length=3)
    fullname = models.CharField(max_length=100)
    roadflg = models.CharField(max_length=1)
    the_geom = models.GeometryField()

countyfp_to_borough = {'061' : 'Manhattan'}

number_st_re = re.compile("((?:[NSEW] )?\d+)(?:st|nd|rd|th)? (Ave|St)(.*)")
def normalize_street_name(fullname):
    """Tiger data has inconsistencies -- 25th St vs 26 St, or 
    7 Ave vs 7th Ave.  We can't fix them all, but at least we 
    can fix the numbered streets and avenues."""

    match = number_st_re.match(fullname)
    if match:
        return "%s %s%s" % (match.group(1), match.group(2), match.group(3))
    else:
        return fullname



class Command(BaseCommand):
    help = "Imports tiger data from the table provided into the tracker tables."

    def handle(self, tiger_table_name, **kw):

        Tiger._meta.db_table = tiger_table_name

        tiger_segs = Tiger.objects.filter(roadflg='Y')

        print "Importing from tiger data.  %d road segments to import" % len(tiger_segs)
        for i, tiger_seg in enumerate(tiger_segs):
            borough = countyfp_to_borough[tiger_seg.countyfp]
            if i and i % 500 == 0:
                print "finished %d" % i
            if not tiger_seg.fullname:
                continue #riding through the city on a road with no name...

            fullname = normalize_street_name(tiger_seg.fullname)
            
            road = Road(name = fullname + ", " + borough)
            road.save()

            seg = RoadSegment(gid=tiger_seg.gid, geometry=tiger_seg.the_geom, road=road, path_order=-1)
            seg.save() 
            
        #now, set path order for each road

        for road in Road.objects.all():
            road_geometry = None
            segments = list(road.roadsegment_set.all())
            for segment in segments:
                if road_geometry:
                    road_geometry = road_geometry.union(segment.geometry)
                else: 
                    road_geometry = segment.geometry

            assert road_geometry, "road %s has no geometry" % road.name
            extent = road_geometry.extent
            x_extent = abs(road_geometry.extent[0] - road_geometry.extent[2])
            y_extent = abs(road_geometry.extent[1] - road_geometry.extent[3])
            
            if x_extent > y_extent:
                segments.sort(key=lambda segment:segment.geometry.extent[0])
            else:
                segments.sort(key=lambda segment:segment.geometry.extent[1])

            #and god help you if your road loops back on itself

            for i, segment in enumerate(segments):
                segment.path_order = i
                segment.save()

        print "Denormalizing road geometry"
        from django.db import connection
        cursor = connection.cursor()
        cursor.execute(
"""UPDATE tracker_road SET geometry=(select st_linemerge(st_union(tracker_roadsegment.geometry))
FROM 
tracker_roadsegment
WHERE 
tracker_roadsegment.road_id = tracker_road.name)""")

