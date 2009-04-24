from django.conf.urls.defaults import *

urlpatterns = patterns('',
    (r'^/?$', 'tracker.views.index'),
    (r'^(?P<bus_id>\d+)/update$', 'tracker.views.update'),
    (r'^(?P<route_name>[\w ]+)/locate$', 'tracker.views.locate'),
    (r'^(?P<route_name>[\w ]+)/locate_by_address$', 'tracker.views.locate_by_address'),
)
