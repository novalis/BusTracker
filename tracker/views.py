from datetime import datetime
from django.contrib.gis.geos import Point
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.utils.datastructures import SortedDict
from tracker.models import *

import django.templatetags #for the side-effects of doing so
import settings
import urllib
import tracker.templatetags #to catch import errors

#75 m / 1 decimal degree
STOP_FUDGE = 0.0000676

def index(request):

    routes = Route.objects.all()
    return render_to_response('routes/index.html', {'routes': routes})


def kml(request):
    bus_id = request.REQUEST['bus_id']
    observations = list(BusObservation.objects.filter(bus=bus_id))
    intersection_observations = list(IntersectionObservation.objects.filter(bus=bus_id))

    observations += intersection_observations
    observations.sort(key=lambda obs: obs.time)
    
    return render_to_response('routes/kml.kml', {'observations': observations})

def route_kml(request):
    route = _route_by_name(request.REQUEST['route'])
    return render_to_response('routes/route_kml.kml', {'route': route})

@transaction.commit_on_success
def update(request):
    if not request.method == "POST":
        return HttpResponse("Bad method", status=405)

    bus_id = request.REQUEST['bus_id']    
    
    route = _route_by_name(request.REQUEST['route'])

    #figure out what trip we are on by assuming it is the trip
    #starting closest to now.

    client_time = datetime.strptime(request.REQUEST['date'].strip(), "%Y-%m-%dT%H:%M:%SZ")

    bus_candidates = (Bus.objects.filter(id=bus_id)[:1])
    if len(bus_candidates):
        bus = bus_candidates[0]
    else:
        #fixme: day of week
        trip = Trip.objects.extra(
            select = SortedDict([
                    ('start_error', 'abs(extract(epoch from start_time - %s))')
                    ]),  
            select_params = (client_time.time(),)
            ).order_by('start_error')[0]
    
        bus = Bus(id=bus_id, route=route, trip=trip)
        bus.save()

    location = Point(float(request.REQUEST['lng']), float(request.REQUEST['lat']))

    if 'intersection' in request.REQUEST:
        obs = IntersectionObservation(bus=bus, location=location, time=client_time, intersection = request.REQUEST['intersection'])
        obs.save()
    else:

        possible_observations = bus.busobservation_set.order_by('-time')[:2]
        if (len(possible_observations) == 2 and 
            possible_observations[0].location == location and 
            possible_observations[1].location == location):
            possible_observations[0].time = client_time
        else:
            extra_field_names = ['speed', 'course', 'horizontal_accuracy', 'vertical_accuracy', 'altitude']
            extra_fields = {}
            for x in extra_field_names:
                value = request.REQUEST.get(x)
                if not value:
                    continue
                try:
                    value = float(value)
                    extra_fields[x] = value
                except ValueError:
                    continue

            obs = BusObservation(bus=bus, location=location, time=client_time, **extra_fields)
                                       
            obs.save()
            
            #fixme: this WILL NOT WORK until observation distances are
            #nondescending.

            #figure out dwell information
            route_length = route.length
            stop_fudge = STOP_FUDGE / route_length

            prev_bus_stop = TripStop.objects.filter(
                trip=bus.trip, 
                distance__lte=obs.distance + stop_fudge * route_length
                ).order_by('distance')[:1]

            if len(prev_bus_stop):
                prev_bus_stop = prev_bus_stop[0]

                try:
                    prev_observation = obs.get_previous_by_time(bus=bus)
                    if prev_observation.distance + stop_fudge <= prev_bus_stop.distance:
                        #this is our first post-stop observation

                        #find the observation that was before the stop.
                        before_stop_observation = BusObservation.objects.filter(
                            distance__lte=prev_bus_stop - stop_fudge
                            )[0]
                        bus.total_dwell_time += (client_time - before_stop_observation.time).seconds
                        bus.n_dwells += 1
                except BusObservation.DoesNotExist:
                    pass
    return HttpResponse("ok")

# from http://www.djangosnippets.org/snippets/293/
def geocode(location):
    key = settings.GOOGLE_API_KEY
    output = "csv"
    location = urllib.quote_plus(location)
    request = "http://maps.google.com/maps/geo?q=%s&output=%s&key=%s" % (location, output, key)
    data = urllib.urlopen(request).read()
    dlist = data.split(',')
    if dlist[0] == '200':
        return (float(dlist[2]), float(dlist[3]))
    else:
        return None

def _parse_route_name(route_name):
    route_parts = route_name.split(" ")
    name, direction = route_parts[:2]
    if len(route_parts) == 3:
        path = route_parts[2]
    else:
        path = None
    return name, direction, path

def _route_by_name(route_name):
    name, direction, path = _parse_route_name(route_name)
    if path:
        route = Route.objects.get(name = name, direction = direction, path=path)
    else:
        route = Route.objects.get(name = name, direction = direction)        
    return route

def _locate(route_name, time, long, lat):
    route = _route_by_name(route_name)
    
    location = Point(long, lat)
    buses = []
    for bus in route.bus_set.all():
        bus.est = bus.estimated_arrival_time(location, time=time)

        if bus.est and bus.est > time:
            #bus is still to come (probably)
            buses.append(bus)
            
    return render_to_response('routes/estimates.html', {'buses': buses})

def show_locate_by_address(request):

    routes = Route.objects.all()
    return render_to_response('routes/show_locate_by_address.html', {'routes': routes})

def locate_by_address(request):
    route_name = request.REQUEST['route_name']
    if 'time' in request.REQUEST:
        time = datetime.utcfromtimestamp(float(request.REQUEST['time']))
    else:
        time = datetime.utcnow()

    lat, long = geocode(request.REQUEST['address'])
    return _locate(route_name, time, long, lat)


def locate(request):
    route_name = request.REQUEST['route_name']
    #find the nearest bus to you that has (probably) not reached you.

    if 'time' in request.REQUEST:
        time = datetime.utcfromtimestamp(float(request.REQUEST['time']))
    else:
        time = datetime.utcnow()

    return _locate(route_name, time, float(request.REQUEST['long']), float(request.REQUEST['lat']))

def map(request):
    routes = [route.route_name() for route in Route.objects.all()]
    return render_to_response('routes/map.html', {'routes': routes})
