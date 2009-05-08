from django.template import Library, add_to_builtins
from simplejson import loads

import settings
import sys
import urllib

register = Library()

@register.filter
def localdatetime(dt):
    """Converts a datetime (assumed to be in UTC) to the local time
    zone as defined by your settings.  Ideally, you should do all your
    date computations in UTC (whether naive or not), and format only
    for output."""
    import pytz
    from django.conf import settings
    local_time_zone = pytz.timezone(str(settings.TIME_ZONE))
    localized_dt = pytz.utc.localize(dt)
    return localized_dt.astimezone(local_time_zone)

@register.filter
def reverse_geocode_intersection(point):
    long, lat = point.x, point.y
    url = "http://ws.geonames.org/findNearestIntersectionJSON?lat=%f&lng=%f" % (lat, long)
    data = urllib.urlopen(url).read()
    try:
        intersection = loads(data)
        intersection = intersection['intersection']
    except:
        print >>sys.stderr, "Couldn't geocode %s : %s" % (point, intersection)
        return '(%f, %f) [geocoding failed]' % (lat, long)

    return "%s and %s" % (intersection['street1'], intersection['street2'])
    

add_to_builtins('tracker.templatetags')


@register.filter
def style_for_observation(observation):
    return observation._meta.db_table
