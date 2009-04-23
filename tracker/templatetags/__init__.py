from django.template import Library, add_to_builtins

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

add_to_builtins('tracker.templatetags')
