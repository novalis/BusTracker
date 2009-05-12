from django.core.management.base import BaseCommand
from pprint import pformat
from simplejson import dumps

import os
import re
import sys

#stif.bx0012sb.309113.wkd.closed
filename_re = re.compile("stif.(?P<borough>m|b|bx|q|s)_?(?P<route_no>\d+)(?P<unknown_flags>x_|c_|o_|sb|__).(?P<unknown_2>\w{6}).(?P<day_of_week>sat|sun|wkd)")

class FieldDef:    
    def __init__(self, name, width, numeric = False, hex = False, stripped = True, strip_underscore=False):
        self.name = name
        self.width = width
        self.stripped = stripped
        self.strip_underscore = strip_underscore
        self.numeric = numeric or hex
        self.hex = hex

class LineFormat:
    def __init__(self, *fields):
        self.fields = fields

    @property
    def width(self):
        return sum(field.width for field in self.fields)

    def parse(self, dataline):
        values = {}
        pos = 0
        for field in self.fields:
            try:
                values[field.name] = dataline[pos:pos + field.width]
                if field.stripped:
                    values[field.name] = values[field.name].strip()
                if field.strip_underscore:
                    values[field.name] = values[field.name].strip("_")
                if field.numeric:
                    if field.hex:
                        values[field.name] = int(values[field.name], 16)
                    else:
                        values[field.name] = int(values[field.name])
            except:
                print >>sys.stderr, "Error parsing line %s\nat field %s, at pos %d" % (dataline, field.name, pos)
                print >>sys.stderr, "Parsed so far: %s" % pformat(values)
                raise
            pos += field.width
        return values

#there's one of these at the beginning of the file
#0         1         2         3         4         5         6         7         
#012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901
#11MQ  M 0006  1 MICHAEL J. QUILL        BROADWAY - 6 AVENUE     209009   240 S OA  20081001                                        
#11UP  M 0025X 11ULMER PARK              GRAND CENTRAL - WALL STR409057   240 S TA  20081013  

route_format = LineFormat(
    FieldDef('route_id', 6),
    FieldDef('borough', 2),
    FieldDef('route_no', 5),
    FieldDef('UNKNOWN_1', 2, numeric=True),
    FieldDef('depot', 24), 
    FieldDef('street_name', 24), 
    FieldDef('UNKNOWN_2', 7),  #this appears to be the same as unknown_2 in the filename
    FieldDef('UNKNOWN_3', 5), 
    FieldDef('UNKNOWN_4', 2), 
    FieldDef('UNKNOWN_5', 2), 
    FieldDef('UNKNOWN_6', 9), #looks like a date in YYYYMMDD format?
    FieldDef('REMAINDER', 4)
)

#there's a list of these staring at the second line.  It appears that
#they describe bus stops, and are not in order

#0         1         2         3         4         5         6         7         8         9        10   
#01234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123
#15169bBRIGHTON BEACH AV     CONEY ISLAND AV       000000000000B  BBCIA    N    40578014 -73959770 300012

stop_format = LineFormat(
    FieldDef('UNKNOWN_1', 2, hex=True),
    FieldDef('stop_id', 4, hex=True),
    FieldDef('street1', 22),
    FieldDef('street2', 22),
    FieldDef('UNKNOWN_2', 11, numeric=True),
    FieldDef('borough', 2),
    FieldDef('UNKNOWN_3', 10), #optional, and it appears to correlate to location, as in Bartel PRichard SQ -> BPRSQ 
    FieldDef('stop_type', 4), #N or D for Normal or Depot (?)
    FieldDef('latitude', 9, numeric=True),
    FieldDef('longitude', 9, numeric=True),
    FieldDef('UNKNOWN_4', 6, numeric=True)
)


#after the bus stops, there are sets of one of these (which probably
#represent trips) followed by a few dozen of the next ones (time
#points?)

#0         1         2         3         4         5         6         7         8         9        10        11        12        13        14        15        16        17        18
#012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012

#212e1600034500N 1 ad1 00037500         4BX07_0019     BX07                        R3070 N N                6880 KB    8743044      4   BX07 00039000   15   BX07      4   BX07 00032200

trip_format = LineFormat(
    FieldDef('UNKNOWN_0', 2, hex=True),
    FieldDef('stop_id', 4, hex=True),
    FieldDef("UNKNOWN_1", 2), 
    FieldDef("start_minutes", 6, numeric=True),
    FieldDef('direction', 2), #NSEW only, I think.
    FieldDef('UNKNOWN_2', 2, numeric=True), 
    FieldDef('UNKNOWN_3', 3, hex=True), 
    FieldDef('UNKNOWN_4', 9, numeric=True),  
    FieldDef('UNKNOWN_5', 9),  #I only hypothesize that this field is not part of the prev or next
    FieldDef('UNKNOWN_6', 1, numeric = True),
    FieldDef('route_name', 5, strip_underscore=True),
    FieldDef('UNKNOWN_7', 4, numeric = True), 
    FieldDef('UNKNOWN_8', 4), #another hypothetical-dark-matter-type field
    FieldDef('route_name_again_1', 5),
    FieldDef('UNKNOWN_9', 24), 
    FieldDef('UNKNOWN_10', 1),
    FieldDef('headsign_id', 5, numeric = True),
    FieldDef('UNKNOWN_12', 2),
    FieldDef('UNKNOWN_13', 2),
    FieldDef('UNKNOWN_14', 14),
    FieldDef('UNKNOWN_15', 5, numeric = True),
    FieldDef('UNKNOWN_16', 7),
    FieldDef('UNKNOWN_17', 7, numeric = True),
    FieldDef('UNKNOWN_18', 7, numeric = True),
    FieldDef('UNKNOWN_19', 3), #dark matter
    FieldDef('route_name_again_2', 5),
    FieldDef('UNKNOWN_20', 9, numeric = True),
    FieldDef('UNKNOWN_21', 7, numeric = True),
    FieldDef('route_name_again_3', 5),
    FieldDef('UNKNOWN_22', 8, numeric = True),
    FieldDef('route_name_again_4', 5),
    FieldDef('UNKNOWN_23', 8, numeric = True),
)


#I hypothesize that the order of these matters -- that is, that they
#contain no internal clues about what stop they correspond to,

#0123456789012345678901
#314c6700052700D ST   E
tripstop_format = LineFormat(
    FieldDef("stop_id", 6, hex=True), #but keyed into what?
    FieldDef("UNKNOWN_1", 2), 
    FieldDef("minutes", 6, numeric=True),
    FieldDef("type", 2), #D = depart?, T = timed?, A = arrive?
    FieldDef("UNKNOWN_2", 5), #ST or SN -- anything else?
    FieldDef("UNKNOWN_3", 1),
)


#012345678901234567890123456789012345678901
#351060    M06       MIDTOWN 59 ST via 6 AV
routename_format = LineFormat(
    FieldDef("UNKNOWN_1", 2, numeric=True), 
    FieldDef("headsign_id", 6, numeric=True), 
    FieldDef("route_id", 4), 
    FieldDef("headsign", 100),
)

def parse_schedule_file(filename):
    """Returns a dict with general data about the route, as well as stops and trips, and stops for each trip"""
    match = filename_re.match(filename)
    route = match.groupdict()
    f = open(filename)
    route.update(route_format.parse(f.readline()))

    route['stops'] = []
    route['trips'] = []
    route['headsigns'] = []

    trip = None

    for line in f.readlines():
        if len(line) == stop_format.width:
            stop = stop_format.parse(line)
            route['stops'].append(stop) #stops are out-of-order, and we don't yet know how to order them
        elif len(line) == trip_format.width:
            trip = trip_format.parse(line)
            trip['stops'] = []
            route['trips'].append(trip)
        elif len(line) == tripstop_format.width:
            stop = tripstop_format.parse(line)
            #fixme: associate stop id with box id or some other location id
            trip['stops'].append(stop) 
        elif len(line) == headsign_format.width:
            route['headsigns'].append(headsign_format.parse(line))
        else:
            print "unknown line %s" % line

    return route

holidays = {'Christmas' : 'xmd', 'Christmas Eve' : 'xme',
            'New Year\'s Day' : 'nyd', 'New Year\'s Eve' : 'nye'}

class Command(BaseCommand):
    def handle(self, dirname, **kw):
        routes = {}
        files = os.listdir(dirname)
        for filename in files:
            if filename.startswith('stif'):
                route = parse_schedule_file(os.path.join(dirname, filename))
            if filename in holidays:
                holiday_abbrev = holidays[filename]
                subdirname = os.path.join(dirname, filename)
                files = os.listdir(subdirname)
                for filename in files:
                    route = parse_schedule_file(os.path.join(subdirname, filename))
                    route['day_of_week'] = holiday_abbrev
        routes.append(route)
        print dumps(routes)
