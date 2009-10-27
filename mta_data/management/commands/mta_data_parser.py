from pprint import pformat

import os
import re
import sys

#stif.bx0012sb.309113.wkd.closed
#stif.q_0031__.509084.sat
stif_filename_re = re.compile("stif\\.(?P<borough>m|b|bx|q|s)_?(?P<route_no>\d{4})(?P<unknown_flags>x_|c_|o_|sb|__)\\.(?P<unknown_2>\w{6})\\.(?P<day_of_week>sat|sun|wkd\\.open|wkd.\\closed)")

#rtif.gs..1.0015.000.08127
#rtif.c...1.0043.000.07009 
rtif_filename_re = re.compile("rtif\\.(?P<line>[a-z0-9]{0,2})[.]{0,3}(?P<day_of_week>\d)(?P<misc>.*)")

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
    formats = {}
    def __init__(self, name, id, *fields):
        self.name = name
        self.id = id
        self.fields = list(fields)
        self.fields.insert(0, FieldDef('record_type', 2, numeric=True))
        LineFormat.formats[id] = self

    @property
    def width(self):
        return sum(field.width for field in self.fields)

    def parse(self, dataline):
        values = {'_format' : self.name}
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
            except Exception, e:
                print >>sys.stderr, "Error parsing line %s\nat field %s, at pos %d: '%s'" % (dataline, field.name, pos, value)
                print >>sys.stderr, "Parsed so far: %s" % pformat(values)
                print "Exception: %s" % e
                import pdb;pdb.set_trace()
                raise
            pos += field.width
        return values

    @classmethod
    def parse_line(cls, line):
        format_id = int(line[:2])
        format = cls.formats[format_id]
        return format.parse(line)


#there's one of these at the beginning of the file
#0         1         2         3         4         5         6         7         
#012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901
#11MQ  M 0006  1 MICHAEL J. QUILL        BROADWAY - 6 AVENUE     209009   240 S OA  20081001                                        
#11UP  M 0025X 11ULMER PARK              GRAND CENTRAL - WALL STR409057   240 S TA  20081013  

route_format = LineFormat(
    "route", 11,
    FieldDef('depot_short', 4),
    FieldDef('borough', 2),
    FieldDef('route_no', 4, numeric=True),
    FieldDef('route_name_flag', 1),
    FieldDef('UNKNOWN_1', 2),
    FieldDef('depot', 24), 
    FieldDef('street_name', 24), 
    FieldDef('UNKNOWN_2', 7),  #this appears to be the same as unknown_2 in the filename
    FieldDef('UNKNOWN_3', 5), 
    FieldDef('UNKNOWN_4', 2), 
    FieldDef('UNKNOWN_5', 2), 
    FieldDef('UNKNOWN_6', 9), #looks like a date in YYYYMMDD format?
    FieldDef('REMAINDER', 4),
)

#there's a list of these staring at the second line.  It appears that
#they describe bus stops, and are not in order

#0         1         2         3         4         5         6         7         8         9        10   
#01234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123
#15169bBRIGHTON BEACH AV     CONEY ISLAND AV       000000000000B  BBCIA    N    40578014 -73959770 300012

stop_format = LineFormat(
    "stop", 15,
    FieldDef('stop_id', 4, hex=True),
    FieldDef('street1', 22),
    FieldDef('street2', 22),
    FieldDef('UNKNOWN_2', 12, numeric=True),
    FieldDef('borough', 3),
    FieldDef('UNKNOWN_3', 9), #optional, and it appears to correlate to location, as in Bartel PRichard SQ -> BPRSQ 
    FieldDef('stop_type', 4), #N or D for Normal or Depot (?)
    FieldDef('latitude', 10, numeric=True),
    FieldDef('longitude', 10, numeric=True),
    FieldDef('box_no', 6, numeric=True)
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
    "trip", 21,
    FieldDef('stop_id', 4, hex=True),
    FieldDef("UNKNOWN_1", 2), 
    FieldDef("start_minutes", 6, numeric=True),
    FieldDef('direction', 2), #NSEW only, I think.
    FieldDef('trip_type', 1, numeric=True),  #1 = normal; anything else = to/from depot?
    FieldDef('UNKNOWN_3', 1, numeric=True),  #but does it have something to do with local/limited/expressness? because I noticed it on the M5 limited service buses
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
    'tripstop', 31,
    FieldDef("stop_id", 4, hex=True),
    FieldDef("UNKNOWN_2", 2), 
    FieldDef("minutes", 6, numeric=True),
    FieldDef("type", 2), #D = depart, T = timed, A = arrive
    FieldDef("UNKNOWN_3", 5), #ST or SN -- anything else?
    FieldDef("UNKNOWN_4", 1),
)


#012345678901234567890123456789012345678901
#351060    M06       MIDTOWN 59 ST via 6 AV

headsign_format = LineFormat(
    'headsign', 35,
    FieldDef("headsign_id", 5, numeric=True), 
    FieldDef("UNKNOWN_2", 3),
    FieldDef("route_id", 5), 
    FieldDef("UNKNOWN_3", 5), 
    FieldDef("headsign", 100),
)

unknown_format_41 = LineFormat(
    'unknown41', 41,
    FieldDef("unknown", 30)
)

subway_stop_format = LineFormat(
    'subway_stop', 13,
    FieldDef("location_id", 8),
    FieldDef("abbrev_name", 8),
    FieldDef("full_name", 33),
    FieldDef("feet_east", 6, numeric=True),
    FieldDef("feet_north", 6, numeric=True),
    FieldDef("UNKNOWN_1", 20), 
)

#20H15       004150N 1 H19       005450H         304   H..N21R     H   R44                                           1   00630010                                
subway_trip_format = LineFormat(
    'subway_trip', 20,
    FieldDef("start_location_id", 8),
    FieldDef("start_minutes", 8, numeric=True),
    FieldDef("direction", 2), #N or S only
    FieldDef("trip_type", 2, numeric=True), #1 = normal
    FieldDef("end_location_id", 8),
    FieldDef("end_minutes", 8, numeric=True),
    FieldDef("UNKNOWN_1", 28),
    FieldDef("line_name", 4),
    FieldDef("car_type", 4),
    FieldDef("UNKNOWN_2", 95),
)

#30M21     J1  009800D SY                

subway_tripstop_format = LineFormat(
    'subway_tripstop', 30,
    FieldDef('stop_id', 8),
    FieldDef('chaining_line', 4),
    FieldDef('stop_time', 6, numeric=True),
    FieldDef("type", 2), #D = depart, T = timed, A = arrive
    FieldDef("is_real_stop", 1),
    FieldDef("UNKNOWN_1", 1),
    FieldDef("UNKNOWN_2", 16),
)

#17***ALL**                                                                      
subway_unknown_format_1 = LineFormat(
    'subway_unknown_1', 17,
    FieldDef('all', 8),
    FieldDef('UNKNOWN_1', 72),
)

#90   69    1  224  21612346                                     
subway_unknown_format_2 = LineFormat(
    'subway_unknown_2', 90,
    FieldDef('UNKNOWN_1', 62),
)

def parse_stif_file(path, route):

    #open and closed refer to public schools
    if route['day_of_week'] == 'wkd.open':
        route['day_of_week'] = 'wko'
    if route['day_of_week'] == 'wkd.closed':
        route['day_of_week'] = 'wkc'

    route['original_filename'] = path

    f = open(path)
    line = f.readline().strip('\r\n')
    route.update(route_format.parse(line))

    route['stops'] = []
    route['trips'] = []
    route['headsigns'] = []

    trip = None

    line_no = 0
    for line in f.readlines():
        line_no += 1
        line = line.strip('\r\n')
        parsed = LineFormat.parse_line(line)
        parsed['_line_no'] = line_no
        format = parsed['_format']
        if format == 'stop':
            route['stops'].append(parsed)
        elif format == 'trip':
            parsed['stops'] = []
            trip = parsed
            route['trips'].append(trip)
        elif format == 'tripstop':
            trip['stops'].append(parsed ) 
        elif format == 'headsign':
            route['headsigns'].append(parsed)
        else:
            route['more_unknown_crap'] = line

    return route

def parse_rtif_file(path, route):
    route['original_filename'] = path

    f = open(path)
    line = f.readline().strip('\r\n')
    route.update(route_format.parse(line))

    route['stops'] = []
    route['trips'] = []

    trip = None

    line_no = 0
    for line in f.readlines():
        line_no += 1
        line = line.strip('\r\n')
        parsed = LineFormat.parse_line(line)
        parsed['_line_no'] = line_no
        format = parsed['_format']
        if format == 'subway_stop':
            route['stops'].append(parsed)
        elif format == 'subway_trip':
            trip = parsed
            trip['stops'] = []            
            if not 'subway_trips' in route:
                route['subway_trips'] = []
            route['subway_trips'].append(trip)
        elif format == 'subway_tripstop':
            trip['stops'].append(parsed ) 
        else:
            route['more_unknown_crap'] = line

    return route


def parse_schedule_file(path):
    """Returns a dict with general data about the route, as well as stops and trips, and stops for each trip"""
    filename = os.path.basename(path)
    stif_match = stif_filename_re.match(filename)

    if stif_match:
        route = stif_match.groupdict()
        return parse_stif_file(path, route)

    rtif_match = rtif_filename_re.match(filename)

    if rtif_match:
        route = rtif_match.groupdict()
        return parse_rtif_file(path, route)

    print >>sys.stdout, "could not parse filename %s" % filename

holidays = {'Christmas' : 'xmd', 'Christmas Eve' : 'xme',
            'New Year\'s Day' : 'nyd', 'New Year\'s Eve' : 'nye'}

def parse_schedule_dir(dirname, format):
    files = os.listdir(dirname)
    use_files = []

    for filename in files:
        if filename.startswith(format):
            use_files.append((filename, dirname, None))
        else:
            subdirname = os.path.join(dirname, filename)
            if filename in holidays:
                holiday_abbrev = holidays[filename]
                files = os.listdir(subdirname)
                for filename in files:
                    #schools are necessarily closed on holidays, so I have
                    #no idea why there are open data sets.
                    if filename.startswith(format) and filename.endswith('.closed'):
                        use_files.append((filename, subdirname, holiday_abbrev))
            elif os.path.isdir(subdirname):
                for result in parse_schedule_dir(subdirname, format):
                    yield result
            else:
                print subdirname
            
    use_files.sort()
    for filename, dirname, day_of_week in use_files:
        if 'b_0666' in filename or 'b_0333' in filename:
            continue #there is no B666 or B333 bus -- these are
                     #shuttle buses that don't make stops.  There is
                     #no route data for them, so we won't include
                     #them.
                     

        route = parse_schedule_file(os.path.join(dirname, filename))
        if not route:
            continue
        if day_of_week:
            route['day_of_week'] = day_of_week
        yield route
