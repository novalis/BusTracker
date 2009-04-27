from datetime import datetime
from django.test import TestCase
from django.test.client import Client
from tracker.views import update
from tracker.models import *


class UpdateTestCase(TestCase):
    fixtures = ['location.json']

    def test_update_location(self):

        c = Client()
        response = c.post('/tracker/update', {'username' : '5',
                                              'report': 'M20 Uptown', 
                                              'lat': '40.737606', 
                                              'lng' : '-74.006393',
                                              'date' : '2009-04-23T05:06:07Z'})
        assert response.status_code == 200

        response = c.get('/tracker/')
        self.assertTrue('M20 Uptown' in response.content)

        bus = Bus.objects.get(id=5)
        observations = bus.busobservation_set.filter(time=datetime.strptime("2009-04-23T05:06:07Z", '%Y-%m-%dT%H:%M:%SZ'))
        self.assertEqual(len(observations), 1)
        observation = observations[0]
        self.assertAlmostEqual(observation.location.x, -74.006393)
        self.assertAlmostEqual(observation.location.y, 40.737606) 

    def test_estimate(self):

        assert BusObservation.objects.all().count() > 3

        c = Client()

        response = c.get('/tracker/locate', 
                         { 'route_name' : 'M20 Uptown',
                           'lat': '40.766735', 
                           'long' : '-73.983093',
                           'time' : '1239644900',
                           }
                          )
        #there's an estimate for the bus on this day
        self.assertEqual(response.status_code, 200)
        self.assertTrue('2009-04-13' in response.content)

        response = c.get('/tracker/locate', 
                         { 'route_name' : 'M20 Uptown',
                           'lat': '40.766735', 
                           'long' : '-73.983093',
                           'time' : '1239645900',
                           }
                          )
        #there's an estimate for the bus on this day, after the first bus has passed 
        self.assertEqual(response.status_code, 200)
        self.assertTrue('2009-04-13' in response.content)


        response = c.get('/tracker/locate', 
                         { 'route_name' : 'M20 Uptown',
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

        c = Client()

        response = c.get('/tracker/locate_by_address', 
                         { 'route_name' : 'M20 Uptown',
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
