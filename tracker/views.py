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

#75 m / 1 decimal degree
STOP_FUDGE = 0.0000676

def index(request):

    routes = Route.objects.all()
    return render_to_response('routes/index.html', {'routes': routes})


def kml(request):
    bus_id = request.REQUEST['bus_id']
    observations = list(BusObservation.objects.filter(bus=bus_id))

    if 'show_intersections' in request.REQUEST:
        intersection_observations = list(IntersectionObservation.objects.filter(bus=bus_id))
        observations += intersection_observations
        observations.sort(key=lambda obs: obs.time)

    error_lines = []
    snap_to_roads = False
    if 'snap_to_roads' in request.REQUEST:
        snap_to_roads = True
    elif 'show_intersections' in request.REQUEST:
        # TODO: Break this up into a separate function and KML file?
        # TODO: make this work even when show_intersections is off? 
        # this will not draw lines for any observations before the first
        # intersection
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
                            dt = float((bus_obs.time - prev_stop.time).seconds) / time_btw_stops
                            dist_along_route = dt * dist_btw_stops + prev_stop.distance_along_route()
                            loc_on_route = point_on_route_by_distance(dist_along_route, bus_obs.bus.trip.shape)
                            error_lines.append({'start':bus_obs.location, 'end': loc_on_route})
                prev_stop = curr_stop
                obs_btw_stops = []
            else: # bus observation
                obs_btw_stops.append(obs)
    
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

    #figure out what trip we are on by assuming it is the trip
    #starting closest to here and now.

    client_time = datetime.strptime(request.REQUEST['date'].strip(), "%Y-%m-%dT%H:%M:%SZ")

    bus_candidates = (Bus.objects.filter(id=bus_id)[:1])

    location = Point(float(request.REQUEST['lng']), float(request.REQUEST['lat']))

    if len(bus_candidates):
        bus = bus_candidates[0]
        trip = bus.trip
    else:
        #fixme: day of week
        location_sql = "SRID=4326;POINT(%s %s)" % (request.REQUEST['lng'], request.REQUEST['lat'])
        trip = Trip.objects.filter(route = route).extra(
            tables=['mta_data_shape'],
            select = SortedDict([
                    ('start_error', 'abs(extract(epoch from start_time - %s))'),
                    ('shape_error', 'st_distance(st_startpoint(mta_data_shape.geometry), %s)')
                    ]),  
            select_params = (client_time.time(), location_sql)
            ).order_by('start_error')[0]
    
        bus = Bus(id=bus_id, trip=trip)
        bus.save()


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
            route_length = trip.shape.length
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

