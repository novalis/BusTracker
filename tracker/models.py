from datetime import datetime, timedelta
from django.contrib.gis.db import models

class Road(models.Model):
    """An entire road -- 8 Ave, for instance"""
    name = models.CharField(max_length=120, primary_key=True)
    geometry = models.GeometryField(null=True)
    #Name is road_name, borough.  Some roads (the BQE, say) will
    #appear in multiple boroughs, and will be treated as multiple
    #roads

class RoadSegment(models.Model):
    """Represents one segment of a road -- 8 Ave between W 28 St and
    W 29 St, for instance"""
    gid = models.IntegerField(primary_key=True)
    geometry = models.GeometryField()
    road = models.ForeignKey(Road)
    path_order = models.IntegerField()

class Route(models.Model):
    name = models.CharField(max_length=200, primary_key=True) #M20 Uptown
    geometry = models.GeometryField(null=True) #denormalized

    def __unicode__(self):
        return "<Route ('%s')>" % self.name
    
class RouteSegment(models.Model):
    roadsegment = models.ForeignKey(RoadSegment)
    route = models.ForeignKey(Route)
    path_order = models.IntegerField()

class Bus(models.Model):
    """A particular physical bus"""
    route = models.ForeignKey(Route) #the route it is traveling on (if any)

    def __unicode__(self):
        return "<Bus (%d) on route %s>" % (self.id, self.route.name)

    @property
    def location(self):
        last = self.busobservation_set.order_by('-time')[0]
        return last.location

    def estimated_arrival_time(self, target_location, time=None):

        #The target location is a point, but needs to be a distance along the route.
        target_location = location_along_route(target_location, self.route)

        #Find out when the bus started moving.  
        #This is when the distance along the route (a) is > 0.01
        observations = self.busobservation_set.all().order_by('time')

        for observation in observations:
            if observation.distance > 0.01:
                start_location, start_time = observation.distance, observation.time
                break
        else:
            #the bus has not yet moved
            return None

        #The bus's last observed location
        last = observations.order_by('-time')[0]
        last_location, last_time = last.distance, last.time

        if last_location <= start_location or last_time <= start_time:
            #the bus has not moved or has moved backwards
            #this means no arrival estimate is possible for this bus.
            return None
        
        rate = (last_location - start_location) / (last_time - start_time).seconds
        if not time:
            now = datetime.utcnow()
        else:
            now = time
        d = target_location - last_location

        return last_time + timedelta(0, d / rate)


def location_along_route(location, route):
    from django.db import connection
    cursor = connection.cursor()
    location = "SRID=4326;POINT(%s %s)" % (location.x, location.y)
    cursor.execute(
"""SELECT st_line_locate_point(tracker_route.geometry, %s) 
FROM 
tracker_route
WHERE 
tracker_route.name = %s""", (location, route.name))
    row = cursor.fetchone()
    return row[0]
        


class BusObservationManager(models.GeoManager):
    def get_query_set(self):
        return super(BusObservationManager, self).get_query_set().extra(select={
            'distance': """
SELECT st_line_locate_point(route.geometry, tracker_busobservation.location) 
FROM 
tracker_bus as bus, 
tracker_route as route
WHERE 
tracker_busobservation.bus_id = bus.id AND
bus.route_id = route.name
"""})




class BusObservation(models.Model):
    """A GPS observation of a bus"""
    objects = BusObservationManager()
    bus = models.ForeignKey(Bus)
    location = models.PointField()
    time = models.DateTimeField()

    class Meta:
        ordering = ["time"]

    def __unicode__(self):
        
        return "<Observation of %s at %s at %s >" % (self.bus, self.location, self.time)


    
