from datetime import datetime
from django.contrib.gis.geos import Point
from django.http import HttpResponse
from django.shortcuts import render_to_response
from tracker.models import *

import django.templatetags #for the side-effects of doing so
import settings
import urllib

def index(request):

    routes = Route.objects.all()
    return render_to_response('routes/index.html', {'routes': routes})


def update(request, bus_id):

    if not request.method == "POST":
        return HttpResponse("Bad method", status=405)
    
    route = Route.objects.get(name=request.REQUEST['route'])
    bus = Bus(id=bus_id, route=route)
    bus.save()


    client_time = datetime.utcfromtimestamp(int(request.REQUEST['time']))
    location = Point(float(request.REQUEST['long']), float(request.REQUEST['lat']))
    obs = BusObservation(bus=bus, location=location, time=client_time)
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

def locate_by_address(request, route_name):
    if 'time' in request.REQUEST:
        time = datetime.utcfromtimestamp(float(request.REQUEST['time']))
    else:
        time = datetime.utcnow()

    long, lat = geocode(request.REQUEST['address'])
    return _locate(route_name, time, long, lat)


def locate(request, route_name):
    #find the nearest bus to you that has (probably) not reached you.

    if 'time' in request.REQUEST:
        time = datetime.utcfromtimestamp(float(request.REQUEST['time']))
    else:
        time = datetime.utcnow()

    return _locate(route_name, time, float(request.REQUEST['long']), float(request.REQUEST['lat']))
