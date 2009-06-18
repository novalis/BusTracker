#!/usr/bin/python

from bus_stops import bus_stops
from datetime import datetime
from gps import gps
from os import popen
from thread import start_new_thread

import gobject
import gtk
import urllib
import sqlite3
import time
import dbus

def init_gps():
    global gps_instance
    g = gps()
    gps_instance = g

def send_observation(lat, lng, intersection = None):
    data = {}
    if intersection:
        data['intersection'] = intersection;

    data['lat'] = lat
    data['lng'] = lng

    now = datetime.now()
    data['date'] = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    data['route'] = route_field.get_active_text()
    data['bus_id'] = id_field.get_text()

    location_db.execute("insert into location(latitude, longitude, time, route, bus_id, intersection) values (?, ?, ?, ?, ?, ?)", (float(lat), float(lng), int(now.strftime("%s")), data['route'], int(data['bus_id']), intersection or ''))
    location_db.commit()

    def send_to_server():
        try:
            u = urllib.urlopen(url_field.get_text(), urllib.urlencode(data))
            response = u.read()
            u.close()
            server_indicator.set_text("%s... at %s" % (response[:20], datetime.now()))
        except Exception, e:
            print "Some sort of error sending: %s" % e
            pass #errors sending are no problem
    start_new_thread(send_to_server, ())

def quit_main_loop(*dump):
    gtk.main_quit()

def send_gps_observation():

    gps_instance.query("o\r\n")
    gps_instance.poll
    if gps_instance.valid:
        send_observation(gps_instance.fix.latitude, gps_instance.fix.longitude)
        valid_indicator.set_text("valid at %s" % datetime.now())
    else:
        valid_indicator.set_text("not valid at %s" % datetime.now())
    return 1
    
tracking = False
def start_tracking(*dummy):
    global cur_stop
    global stops
    global gps_sender_signal
    global tracking

    if tracking:
        tracking = False
        gobject.source_remove(gps_sender_signal)
        start_button.set_label('start tracking')
        return


    if not id_field.get_text() or not route_field.get_active_text():
        return

    start_button.set_label('stop tracking')

    route = route_field.get_active_text()
    stops = bus_stops[route]
    cur_stop = 0
    stop_button.set_sensitive(True)
    stop = stops[cur_stop]
    stop_button.set_label(stop['location'])

    gps_sender_signal = gobject.timeout_add(900, send_gps_observation)

    tracking = True

def reenable_stop_button():
    stop_button.set_sensitive(True)
    stop = stops[cur_stop]
    stop_name = stop['location']
    stop_button.set_label(stop_name)

def found_stop(*dummy):
    global cur_stop

    stop = stops[cur_stop]
    lat = stop['lat']
    lng = stop['lng']
    send_observation(lat, lng, stop['location'])
    
    cur_stop += 1
    stop = stops[cur_stop]
    stop_button.set_sensitive(False) 

    source_id = gobject.timeout_add(1000, reenable_stop_button)


def store_network_list(db, networks):
    now = str(int(datetime.now().strftime("%s")))

    for cell in networks:
        db.execute("insert into networks(time, address, quality) values (?, ?, ?);", (now, cell['address'], cell['quality']))
    db.commit()


def parse_iwlist(output):

    cells = []
    for line in output.split("\n"):
        line = line.strip()

        if line.startswith("Cell"):
            address = line[len("Cell 08 - Address: "):]
            cell = dict(address=address)
            cells.append(cell)
        elif line.startswith("ESSID"):
            cell['essid'] = line[6:]
        elif line.startswith("Quality="):
            start = len('Quality=')
            cell['quality'] = int(line[start:].split("/")[0])
    return cells

def track_networks():
    db = sqlite3.connect('network.db')
    init_network_db(db)

    try:
        while 1:
            if not tracking:
                time.sleep(1)
                continue
            
            f = popen("iwlist eth0 scanning", "r")
            output = f.read()
            networks = parse_iwlist(output)
            f.close()
            store_network_list(db, networks)
    finally:
        db.close()

def init_network_db(db):

    db.execute("""CREATE TABLE IF NOT EXISTS networks(
time int, 
address text,
quality int
)""")
    db.commit()

def init_location_db(db):
    db.execute("""CREATE TABLE IF NOT EXISTS location(
time int, 
latitude float,
longitude float,
bus_id int,
route text,
intersection text
)""")

    db.commit()

def getDbusObject (bus, busname , objectpath , interface):
    dbusObject = bus.get_object(busname, objectpath)
    return dbus.Interface(dbusObject, dbus_interface=interface)


#enable wifi
system_bus = dbus.SystemBus()
wifi = getDbusObject (system_bus, "org.freesmartphone.odeviced", "/org/freesmartphone/Device/PowerControl/WiFi", "org.freesmartphone.Device.PowerControl")
wifi.SetPower(True)



init_gps()
location_db = sqlite3.connect('location.db')
init_location_db(location_db)

start_new_thread(track_networks, ())

win = gtk.Window()
win.connect('delete-event', quit_main_loop)
win.set_title("Locator")
win.set_default_size(480,640)

layout = gtk.VBox()

stop_button = gtk.Button("[bus stop]")
stop_button.set_sensitive(False)
layout.add(stop_button)
stop_button.connect('pressed', found_stop)

valid_indicator = gtk.Label("gps not initialized")
layout.add(valid_indicator)

server_indicator = gtk.Label("last server response")
layout.add(server_indicator)

layout.add(gtk.Label("url"))
url_field = gtk.Entry()

url_field.set_text("http://bustracker.demo.topplabs.org/tracker/update")
#url_field.set_text("http://192.168.0.200:8000/tracker/update")
layout.add(url_field)

layout.add(gtk.Label("id"))
id_field = gtk.Entry()
layout.add(id_field)

layout.add(gtk.Label("route"))
route_field = gtk.combo_box_new_text()
for route in sorted(bus_stops.keys()):
    route_field.append_text(route)

layout.add(route_field)
    
start_button = gtk.Button("Start tracking")
layout.add(start_button)
start_button.connect('pressed', start_tracking)

win.add (layout)

win.show_all()
gtk.main()
