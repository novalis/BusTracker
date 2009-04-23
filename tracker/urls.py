from django.conf.urls.defaults import *

urlpatterns = patterns('',
    (r'^/?$', 'tracker.views.index'),
    (r'^(?P<bus_id>\d+)/update$', 'tracker.views.update'),
    (r'^(?P<route_name>[\w ]+)/locate$', 'tracker.views.locate'),
)
