from datetime import datetime
from django.contrib.gis.geos import Point
from django.http import HttpResponse
from django.shortcuts import render_to_response
from tracker.models import *

import django.templatetags #for the side-effects of doing so
import settings
import urllib
import tracker.templatetags #to catch import errors

def index(request):

    routes = Route.objects.all()
    return render_to_response('routes/index.html', {'routes': routes})


def kml(request):
    bus_id = request.REQUEST['bus_id']
    observations = BusObservation.objects.filter(bus=bus_id)
    return render_to_response('routes/kml.kml', {'observations': observations})

def route_kml(request):
    route_id = request.REQUEST['route_id']
    route = Route.objects.filter(name=route_id).all()[0]
    return render_to_response('routes/route_kml.kml', {'route': route})

def update(request):
    if not request.method == "POST":
        return HttpResponse("Bad method", status=405)


    #note: keys 'username' and 'report' are artifacts of the general nature
    #of the test app.  They will be replaced by sensible keys later.

    bus_id = request.REQUEST['username']    
    route = Route.objects.get(name=request.REQUEST['report'])

    bus = Bus(id=bus_id, route=route)
    bus.save()

    client_time = datetime.strptime(request.REQUEST['date'].strip(), "%Y-%m-%dT%H:%M:%SZ")

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

def _locate(route_name, time, long, lat):
    route = Route.objects.get(name = route_name)
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
    routes = [route.name for route in Route.objects.all()]
    return render_to_response('routes/map.html', {'routes': routes})
