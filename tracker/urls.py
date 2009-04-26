from django.conf.urls.defaults import *

urlpatterns = patterns('',
    (r'^/?$', 'tracker.views.index'),
    (r'^(?P<bus_id>\d+)/update$', 'tracker.views.update'),
    (r'^locate$', 'tracker.views.locate'),
    (r'^locate_by_address$', 'tracker.views.locate_by_address'),
    (r'^show_locate_by_address$', 'tracker.views.show_locate_by_address'),
)
