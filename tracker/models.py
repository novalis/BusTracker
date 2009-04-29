from datetime import datetime, timedelta
from django.contrib.gis.db import models

class Road(models.Model):
    """An entire road -- 8 Ave, for instance"""
    name = models.CharField(max_length=120, primary_key=True)
    geometry = models.GeometryField(null=True)
    #Name is road_name, borough.  Some roads (the BQE, say) will
    #appear in multiple boroughs, and will be treated as multiple
    #roads
    objects = models.GeoManager()

class RoadSegment(models.Model):
    """Represents one segment of a road -- 8 Ave between W 28 St and
    W 29 St, for instance"""

    class Meta:
        ordering = ["path_order"]

    gid = models.IntegerField(primary_key=True)
    geometry = models.GeometryField()
    road = models.ForeignKey(Road)
    path_order = models.IntegerField()
    objects = models.GeoManager()

class Route(models.Model):
    name = models.CharField(max_length=200, primary_key=True) #M20 Uptown
    geometry = models.GeometryField(null=True) #denormalized
    objects = models.GeoManager()    

    def __unicode__(self):
        return "<Route ('%s')>" % self.name

class RouteSegment(models.Model):

    class Meta:
        ordering = ["path_order"]

    roadsegment = models.ForeignKey(RoadSegment)
    route = models.ForeignKey(Route)
    path_order = models.IntegerField()
    objects = models.GeoManager()

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

        for observation in observations:
            if observation.distance > 0.01:
                start_location, start_distance, start_time = observation.location, observation.distance, observation.time
                break
        else:
            #the bus has not yet moved
            return None

        #The bus's last observed distance
        last = observations.order_by('-time')[0]
        last_distance, last_time = last.distance, last.time

        if last_distance <= start_distance or last_time <= start_time:
            #the bus has not moved or has moved backwards
            #this means no arrival estimate is possible for this bus.
            return None
        
        journey_time = (last_time - start_time).seconds
        rate = (last_distance - start_distance) / journey_time
        d = target_distance - last_distance

        estimate_from_distance = d / rate

        def find_nearest_route_segment(route, location):
            """Find which segment of a route a location is nearest to."""
            radius = 0.002
            nearby_segments = []
            #we use dwithin and exponential backoff because dwithin can use
            #the spatial index
            while radius < 0.064 and not nearby_segments:
                nearby_segments = list(route.routesegment_set.filter(roadsegment__geometry__dwithin=(location, radius)))
                radius *= 2
                
            assert nearby_segments, "no segment on %s near %d, %d" % (route.name, location.x, location.y)

            nearest_segment=None
            best_dist = 100000000000
            for segment in nearby_segments:
                dist = segment.roadsegment.geometry.distance(location)
                if dist < best_dist:
                    best_dist = dist
                    nearest_segment = segment

            return nearest_segment

        start_segment = find_nearest_route_segment(self.route, start_location)
        last_segment = find_nearest_route_segment(self.route, last.location)
        target_segment = find_nearest_route_segment(self.route, target_location)

        total_segments = last_segment.path_order - start_segment.path_order
        if total_segments > 0:

            segments_per_second = float(total_segments) / journey_time
            
            remaining_segments = target_segment.path_order - last_segment.path_order

            estimate_from_intersections = remaining_segments / segments_per_second

            seconds = (estimate_from_distance + estimate_from_intersections) / 2
        else:
            seconds = estimate_from_distance

        return last_time + timedelta(0, seconds)


def distance_along_route(location, route):
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


    def distance_along_route(self):
        return distance_along_route(self.location, self.bus.route)
