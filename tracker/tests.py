from datetime import datetime, timedelta
from django.test import TestCase
from django.test.client import Client
from math import sqrt
from tracker.views import update
from tracker.models import *


class UpdateTestCase(TestCase):
    fixtures = ['location.json', 'm6.json', 'schedule.json']

    def test_update_location(self):
        response = self.client.post('/tracker/update', {'bus_id' : '5',
                                              'route': 'M20 N', 
                                              'lat': '40.737606', 
                                              'lng' : '-74.006393',
                                              'date' : '2009-04-23T05:06:07Z'})
        assert response.status_code == 200

        response = self.client.get('/tracker/')
        self.assertTrue('M20' in response.content)

        bus = Bus.objects.get(id=5)
        observations = bus.busobservation_set.filter(time=datetime.strptime("2009-04-23T05:06:07Z", '%Y-%m-%dT%H:%M:%SZ'))
        self.assertEqual(len(observations), 1)
        observation = observations[0]
        self.assertAlmostEqual(observation.location.x, -74.006393)
        self.assertAlmostEqual(observation.location.y, 40.737606) 

    def test_estimate(self):

        assert BusObservation.objects.all().count() > 3

        response = self.client.get('/tracker/locate', 
                         { 'route_name' : 'M20 N',
                           'lat': '40.766735', 
                           'long' : '-73.983093',
                           'time' : '1239644900',
                           }
                          )
        #there's an estimate for the bus on this day
        self.assertEqual(response.status_code, 200)
        self.assertTrue('2009-04-13' in response.content)

        response = self.client.get('/tracker/locate', 
                         { 'route_name' : 'M20 N',
                           'lat': '40.766735', 
                           'long' : '-73.983093',
                           'time' : '1239645900',
                           }
                          )
        #there's an estimate for the bus on this day, after the first bus has passed 
        self.assertEqual(response.status_code, 200)
        self.assertTrue('2009-04-13' in response.content)


        response = self.client.get('/tracker/locate', 
                         { 'route_name' : 'M20 N',
                           'lat': '40.766735', 
                           'long' : '-73.983093',
                           'time' : '1239650000',
                           }
                          )

        #and there's not an estimate for the bus if we ask too late
        self.assertEqual(response.status_code, 200)
        self.assertFalse('2009-04-13' in response.content)

    def test_estimate_geocode(self):

        assert BusObservation.objects.all().count() > 3

        response = self.client.get('/tracker/locate_by_address', 
                         { 'route_name' : 'M20 N',
                           'lat': '40.766735', 
                           'long' : '-73.983093',
                           'time' : '1239644900',
                           'address' : "8 Ave and W 56 St",
                           })

        self.assertEqual(response.status_code, 200)
        self.assertTrue('2009-04-13' in response.content)

        #this location is the bus's last seen location; 
        #the time parameter, above, does not eliminate observations
        #of the bus after that time.
        self.assertTrue('W 57 St' in response.content)
        self.assertTrue('8 Ave' in response.content)

    def test_kml(self):
        
        response = self.client.get('/tracker/kml', 
                         { 'bus_id' : 7 })


        self.assertEqual(response.status_code, 200)
        self.assertTrue('-74.01255, 40.702404' in response.content)

    def test_estimate_accuracy(self):
        """Test the accuracy of the estimation algorithm.  It uses
        the M6 dataset, a record of two bus trips on the M6 bus.

        Estimates are taken one minute, two minutes, ten minutes, and
        twenty minutes before arrival at each observation.
        """

        intervals =[timedelta(0, x) for x in (60, 120, 600, 1200)]

        route = Route.objects.get(name="M06", direction="S")

        total_diff = 0
        n_samples = 0

        max_diff = 0
        worst_spot = None

        for bus in Bus.objects.filter(trip__route = route):
            observations = list(bus.busobservation_set.all())
            first_observation_time = observations[0].time
            tripstops = list(bus.trip.tripstop_set.all())

            nearest_observation_by_stop = {}
            i = 0

            for stop in tripstops:
                #find nearest following observation
                while i < len(observations) - 1 and observations[i].distance <= stop.distance:
                    i += 1
                nearest_observation_by_stop[stop] = observations[i]

            for stop in tripstops:
                observation = nearest_observation_by_stop[stop]
                for interval in intervals:
                    estimate_time = observation.time - interval
                    if estimate_time > first_observation_time:
                        estimated_time = bus.estimated_arrival_time2(stop.bus_stop, estimate_time)
                        if estimated_time:
                            #absolute value of difference; can't use
                            #abs because datetime subtraction is broken.
                            if estimated_time > observation.time:
                                diff = (estimated_time - observation.time).seconds
                            else:
                                diff = (observation.time - estimated_time).seconds

                            if diff > max_diff:
                                max_diff = diff
                                worst_spot = observation.location
                            total_diff += diff * diff
                            n_samples += 1
        assert n_samples, "There must be at least one bus observation in the fixtures."
        print "Divergence for this data set: %s" % sqrt(total_diff / n_samples)
        print "Worst error: %s, at %s, %s" % (max_diff, worst_spot.x, worst_spot.y)


    def test_intersection_observation(self):
                
        response = self.client.post('/tracker/update', {'bus_id' : '8',
                                              'route': 'M20 N', 
                                              'intersection' : '6 Ave and 37 St',
                                              'lat': '40.742899', 
                                              'lng' : '-73.992799',
                                              'date' : '2009-04-24T00:00:00Z'})

        for io in IntersectionObservation.objects.all():
            self.assertTrue(0 < io.distance < 1)
