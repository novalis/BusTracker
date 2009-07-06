#!/usr/bin/python

import sys
import sqlite3
from datetime import datetime


conn = sqlite3.connect('location.db')
curs = conn.cursor()

if len(sys.argv) < 2:
    curs.execute("""select bus_id, count(*), min(time) as m from location group by bus_id order by m""")
    for run, count, start_time in curs.fetchall():
        timestr = str(datetime.fromtimestamp(start_time))
        print "%s (%s points) at %s" % (run, count, timestr)
    sys.exit(0)

bus_id = sys.argv[1]

curs.execute("""select latitude, longitude, time, intersection from location where bus_id=?""", (bus_id,))

print "delete from tracker_intersectionobservation where bus_id = %s;" % bus_id
print "delete from tracker_busobervation where bus_id = %s;" % bus_id
for latitude, longitude, time, intersection in curs.fetchall():
    location = "SRID=4326;POINT(%s %s)" % (longitude, latitude)
    time = datetime.fromtimestamp(time)
    if intersection:
        print "insert into tracker_intersectionobservation(bus_id, location, time, intersection) values (%s, '%s', '%s', '%s');" % (bus_id, location, time, intersection)
    else:
        print "insert into tracker_busobservation(bus_id, location, time) values (%s, '%s', '%s');" % (bus_id, location, time)

