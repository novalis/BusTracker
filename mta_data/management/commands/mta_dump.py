from django.core.management.base import BaseCommand
from mta_data_parser import parse_schedule_dir
from simplejson import dumps

import os

class Command(BaseCommand):
    def handle(self, dirname, outdir, **kw):

        def store(route):
            filename = "%s%s.%s.json" % (route['borough'], route['route_no'], route['day_of_week'])
            path = os.path.join(outdir, filename)
            if os.path.exists(path):
                import pdb;pdb.set_trace()
            out = open(path, "w")
            print >>out, dumps(route)
            out.close()

        for route in parse_schedule_dir(dirname):
            store(route)
