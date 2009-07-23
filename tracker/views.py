from datetime import datetime
from django.contrib.gis.geos import Point
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.utils.datastructures import SortedDict
from tracker.models import *
from mta_data.models import Shape

import django.templatetags #for the side-effects of doing so
import settings
import urllib
import tracker.templatetags #to catch import errors

def index(request):

    routes = Route.objects.all()
    return render_to_response('routes/index.html', {'routes': routes})


def kml(request):
    bus_id = request.REQUEST['bus_id']

    observations = list(BusObservation.objects.filter(bus=bus_id))
    intersection_observations = list(IntersectionObservation.objects.filter(bus=bus_id))
    observations += intersection_observations
    observations.sort(key=lambda obs: obs.time)

    snap_to_roads = False
    if 'snap_to_roads' in request.REQUEST:
        snap_to_roads = True

    error_lines = []
    if 'show_error_lines' in request.REQUEST:
        # TODO: Break this up into a separate function and KML file?
        prev_stop = None
        obs_btw_stops = []
        for obs in observations:
            if hasattr(obs, 'intersection'): # intersection or bus stop
                curr_stop = obs
                if obs_btw_stops:
                    if not prev_stop:
                        # Make a temp/'fake' prev stop to handle the observations
                        # between the start of the route and the first real bus
                        # stop/intersection observation.
                        loc = Point(obs.bus.trip.shape.geometry.coords[0])
                        prev_stop = IntersectionObservation(bus=obs.bus,
                                                            location=loc,
                                                            time=obs_btw_stops[0].time,
                                                            intersection="start of route")

                    dist_btw_stops = curr_stop.distance_along_route() - prev_stop.distance_along_route()
                    time_btw_stops = (curr_stop.time - prev_stop.time).seconds
                    if dist_btw_stops > 0:
                        for bus_obs in obs_btw_stops:
                            if time_btw_stops:
                                dt = float((bus_obs.time - prev_stop.time).seconds) / time_btw_stops
                            else:
                                dt = 0
                            dist_along_route = dt * dist_btw_stops + prev_stop.distance_along_route()
                            loc_on_route = point_on_route_by_distance(dist_along_route, bus_obs.bus.trip.shape)
                            error_lines.append({'start':bus_obs.location, 'end': loc_on_route})
                prev_stop = curr_stop
                obs_btw_stops = []
            else: # bus observation
                obs_btw_stops.append(obs)
    
    if 'show_intersections' not in request.REQUEST:
        observations = list(BusObservation.objects.filter(bus=bus_id))

    return render_to_response('routes/kml.kml', {'observations': observations,
                                                 'snap_to_roads': snap_to_roads,
                                                 'error_lines': error_lines})

def route_kml(request):
    bus_id = request.REQUEST['bus_id']
    bus = Bus.objects.get(id=bus_id)
    trip = bus.trip
    return render_to_response('routes/route_kml.kml', {'trip': trip})

@transaction.commit_on_success
def update(request):
    if not request.method == "POST":
        return HttpResponse("Bad method", status=405)

    bus_id = request.REQUEST['bus_id']    
    route = _route_by_name(request.REQUEST['route'])

    client_time = datetime.strptime(request.REQUEST['date'].strip(), "%Y-%m-%dT%H:%M:%SZ")

    apply_observation(float(request.REQUEST['lat']),
                      float(request.REQUEST['lng']),
                      client_time,
                      bus_id,
                      route,
                      request.REQUEST.get('intersection'),
                      request.REQUEST)

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
    route_parts = route_name.split(" ", 2)
    parts = route_parts
    return parts

def _route_by_name(route_name):
    parts = _parse_route_name(route_name)
    if len(parts) == 2:
        route = Route.objects.get(name = parts[0], direction = parts[1])
    else:
        route = Route.objects.get(name = parts[0], direction = parts[1], headsign=parts[2])
    return route

def _locate(route_name, time, long, lat):
    route = _route_by_name(route_name)
    location = Point(long, lat)
    buses = []
    for bus in Bus.objects.filter(trip__route=route):
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
    buses = Bus.objects.all()
    return render_to_response('routes/map.html', {'buses': buses})

# Displays a map of where all the currently running buses are
def live_map(request):
    return render_to_response('routes/live_map.html')

# Return JSON list of bus location data
def bus_locations(request):
    buses = Bus.objects.all()
    return render_to_response('routes/bus_locations.json', {'buses': buses})

# total hack to test how good our predictions are
def test_accuracy(request):
    from numpy import std

    intervals =[timedelta(0, x) for x in (60, 120, 600, 1200)]

    for bus in Bus.objects.all():
        total_diff = 0

        max_diff = 0
        worst_spot = None

        diffs = []

        observations = list(bus.busobservation_set.all())
        first_observation_time = observations[0].time

        for observation in observations:
            for interval in intervals:
                estimate_time = observation.time - interval
                if estimate_time > first_observation_time:
                    estimated_time = bus.estimated_arrival_time2(observation.location, estimate_time)
                    if estimated_time:
                        #absolute value of difference; can't use
                        #abs because datetime subtraction is broken.
                        if estimated_time > observation.time:
                            diff = (estimated_time - observation.time).seconds
                        else:
                            diff = (observation.time - estimated_time).seconds
                            
                        diffs.append(diff)

                        if diff > max_diff:
                            max_diff = diff
                            worst_spot = observation.location
                        total_diff += diff * diff
        n_samples = len(diffs)
        diffs.sort(reverse=True)
        print "Bus %s" % bus.id
        print "Num diffs: %s" % len(diffs)
        print "Divergence for this data set: %s" % sqrt(total_diff / n_samples)
        print "Standard deviation: %s" % std(diffs)
        print "Worst error: %s, at %s, %s" % (max_diff, worst_spot.x, worst_spot.y)
        print "Worst 20: %s" % diffs[:20]
        diffs = diffs[20:]
        n_samples = len(diffs)
        total_diff = 0
        for diff in diffs:
            total_diff += diff * diff
        print "Num diffs: %s" % n_samples
        print "Divergence ignoring worst 20: %s" % sqrt(total_diff / n_samples)
        print "Standard deviation: %s" % std(diffs)
        print "------------"

