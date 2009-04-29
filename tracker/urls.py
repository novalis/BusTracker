from django.conf.urls.defaults import *
from django.conf import settings

urlpatterns = patterns('',
    (r'^/?$', 'tracker.views.index'),
    (r'^update$', 'tracker.views.update'),
    (r'^locate$', 'tracker.views.locate'),
    (r'^kml$', 'tracker.views.kml'),
    (r'^locate_by_address$', 'tracker.views.locate_by_address'),
    (r'^show_locate_by_address$', 'tracker.views.show_locate_by_address'),
    (r'^map$', 'tracker.views.map'),
)

# Hack to serve static files for development
# http://oebfare.com/blog/2007/dec/31/django-and-static-files/
if settings.LOCAL_DEVELOPMENT:
    urlpatterns += patterns('django.views',
    url(r"static/(?P<path>.*)/$", "static.serve", {
            "document_root": settings.MEDIA_ROOT,
        })
    )
