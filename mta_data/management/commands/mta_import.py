from django.core.management.base import BaseCommand
from pprint import pformat
from simplejson import dumps

import os
import re
import sys

#stif.bx0012sb.309113.wkd.closed
#stif.q_0031__.509084.sat
filename_re = re.compile("stif\\.(?P<borough>m|b|bx|q|s)_?(?P<route_no>\d{4})(?P<unknown_flags>x_|c_|o_|sb|__)\\.(?P<unknown_2>\w{6})\\.(?P<day_of_week>sat|sun|wkd\\.open|wkd.\\closed)")

class FieldDef:    
    def __init__(self, name, width, numeric = False, hex = False, stripped = True, strip_underscore=False):
        self.name = name
        self.width = width
        self.stripped = stripped
        self.strip_underscore = strip_underscore
        self.numeric = numeric
        self.hex = hex

    def __repr__(self):
        return "<FieldDef ('%s', %d)>" % (self.name, self.width)

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
                value = dataline[pos:pos + field.width]
                if field.stripped:
                    value = value.strip()
                if field.strip_underscore:
                    value = value.strip("_")
                if field.numeric:
                    if not value:
                        value = -1
                    elif field.hex:
                        int(value, 16) #don't actually convert to an int, but assert that we can do so
                    else:
                        value = int(value)
                values[field.name] = value
            except:
                print >>sys.stderr, "Error parsing line %s\nat field %s, at pos %d" % (dataline, field.name, pos)
                print >>sys.stderr, "Parsed so far: %s" % pformat(values)
                import pdb;pdb.set_trace()
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
    FieldDef('UNKNOWN_1', 2),
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
    FieldDef('UNKNOWN_2', 12, numeric=True),
    FieldDef('borough', 3),
    FieldDef('UNKNOWN_3', 9), #optional, and it appears to correlate to location, as in Bartel PRichard SQ -> BPRSQ 
    FieldDef('stop_type', 4), #N or D for Normal or Depot (?)
    FieldDef('latitude', 10, numeric=True),
    FieldDef('longitude', 10, numeric=True),
    FieldDef('UNKNOWN_4', 6, numeric=True)
)


#after the bus stops, there are sets of one of these (which probably
#represent trips) followed by a few dozen of the next ones (time
#points?)

#0         1         2         3         4         5         6         7         8         9        10        11        12        13        14        15        16        17        18
#012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012

#212e1600034500N 1 ad1 00037500         4BX07_0019     BX07                        R3070 N N                6880 KB    8743044      4   BX07 00039000   15   BX07      4   BX07 00032200
#2154cd00006000W 1 15ec00008900         1S4898_0032   S4898                        R6481 N N                6760 CA    9012496      1  S4898 00014000   51    S48      1  S4898 00004000
#21f9d 00031500W 1447c100034700       201SBS12_0037   SBS12                        S8127 N N                7270 GH    8745788    201  SBS12 00036000   13  SBS12    201  SBS12 00031300

trip_format = LineFormat(
    FieldDef('UNKNOWN_0', 2, hex=True),
    FieldDef('stop_id', 4, hex=True),
    FieldDef("UNKNOWN_1", 2), 
    FieldDef("start_minutes", 6, numeric=True),
    FieldDef('direction', 2), #NSEW only, I think.
    FieldDef('UNKNOWN_2', 2, numeric=True), 
    FieldDef('start_stop', 4, hex=True), 
    FieldDef('UNKNOWN_4', 2, hex=True),  
    FieldDef('end_minutes', 6, numeric=True),  
    FieldDef('UNKNOWN_5', 9),  #I only hypothesize that this field is not part of the prev or next
    FieldDef('UNKNOWN_6', 1, numeric = True),
    FieldDef('route_name_again_1', 5, strip_underscore=True),
    FieldDef('UNKNOWN_7', 5, numeric = True, strip_underscore=True), 
    FieldDef('UNKNOWN_8', 3), #another hypothetical-dark-matter-type field
    FieldDef('route_name_again_2', 5),
    FieldDef('UNKNOWN_9', 24), 
    FieldDef('UNKNOWN_10', 1),
    FieldDef('headsign_id', 5, numeric = True),
    FieldDef('UNKNOWN_12', 2),
    FieldDef('UNKNOWN_13', 2),
    FieldDef('UNKNOWN_14', 14),
    FieldDef('UNKNOWN_15', 5, numeric = True),
    FieldDef('UNKNOWN_16', 7),
    FieldDef('UNKNOWN_17', 7, numeric = True),
    FieldDef('UNKNOWN_18', 5),
    FieldDef('UNKNOWN_19', 2, numeric = True),
    FieldDef('UNKNOWN_20', 3), #dark matter
    FieldDef('route_name_again_3', 5),
    FieldDef('UNKNOWN_21', 9, numeric = True),
    FieldDef('UNKNOWN_22', 6, numeric = True),
    FieldDef('route_name', 5), #this is the actual route name for this trip -- see s4898 for an example
    FieldDef('UNKNOWN_23', 6),
    FieldDef('UNKNOWN_24', 3, numeric = True),
    FieldDef('route_name_again_4', 5),
    FieldDef('UNKNOWN_25', 9, numeric = True),
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

headsign_format = LineFormat(
    FieldDef("UNKNOWN_1", 2, numeric=True), 
    FieldDef("headsign_id", 5, numeric=True), 
    FieldDef("UNKNOWN_2", 3),
    FieldDef("route_id", 5), 
    FieldDef("UNKNOWN_3", 5), 
    FieldDef("headsign", 100),
)

def parse_schedule_file(path):
    """Returns a dict with general data about the route, as well as stops and trips, and stops for each trip"""
    filename = os.path.basename(path)
    match = filename_re.match(filename)

    if not match:
        print >>sys.stdout, "could not parse filename %s" % filename

    route = match.groupdict()

    if route['day_of_week'] == 'wkd.open':
        route['day_of_week'] = 'wko'
    if route['day_of_week'] == 'wkd.closed':
        route['day_of_week'] = 'wkc'

    route['original_filename'] = filename

    f = open(path)
    line = f.readline().strip('\r\n')
    route.update(route_format.parse(line))

    route['stops'] = []
    route['trips'] = []
    route['headsigns'] = []

    trip = None

    for line in f.readlines():
        line = line.strip('\r\n')
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
        elif len(line) == len("41000026000078000849000066000002"):
            route['more_unknown_crap'] = line
        else:
            print "unknown line %s" % line

    return route

holidays = {'Christmas' : 'xmd', 'Christmas Eve' : 'xme',
            'New Year\'s Day' : 'nyd', 'New Year\'s Eve' : 'nye'}

class Command(BaseCommand):
    def handle(self, dirname, outdir, **kw):
        files = os.listdir(dirname)

        def store(route):
            filename = "%s%s.%s.json" % (route['borough'], route['route_no'], route['day_of_week'])
            path = os.path.join(outdir, filename)
            if os.path.exists(path):
                import pdb;pdb.set_trace()
            out = open(path, "w")
            print >>out, dumps(route)
            out.close()

        for filename in files:
            if filename.startswith('stif'):
                route = parse_schedule_file(os.path.join(dirname, filename))
                store(route)
            elif filename in holidays:
                holiday_abbrev = holidays[filename]
                subdirname = os.path.join(dirname, filename)
                files = os.listdir(subdirname)
                for filename in files:
                    #schools are necessarily closed on holidays, so I have no idea why there are open data sets.
                    if filename.startswith('stif') and filename.endswith('.closed'):
                        route = parse_schedule_file(os.path.join(subdirname, filename))
                        route['day_of_week'] = holiday_abbrev
                        store(route)
