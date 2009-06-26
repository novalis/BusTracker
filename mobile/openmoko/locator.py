#!/usr/bin/python

from bus_stops import bus_stops
from datetime import datetime
from gps import gps
from os import popen
from random import randint
from threading import Thread
import dbus, e_dbus
import gobject
import gtk
import httplib2
import signal
import sqlite3
import sys
import time
import urllib

gprs_apn = 'internet2.voicestream.com'
gprs_login = 'internet'
gprs_password = ''

class Pinger(Thread):
    def __init__(self, url):
        Thread.__init__(self)
        self.url = url
        self.queue = []
        self.to_send_now = None
        self.errors = 0
        self.http = httplib2.Http()
        self.quitting = False

    def run(self):
        while not self.quitting:
            data = None
            while not data:
                if self.quitting:
                    break
                time.sleep(0.25)
                data = self.to_send_now
                if not data:
                    if self.queue:
                        data = self.queue.pop(0)
                
            try:
                print "sending"
                start = time.time()
                encoded = urllib.urlencode(data)
                response, content = self.http.request(self.url, method="POST", body=encoded)
                server_indicator.set_text("%s... at %s" % (content[:20], datetime.now()))
                self.errors = 0
                print "sent in %s seconds" % (time.time() - start)
            except KeyboardInterrupt, SystemExit:
                sys.exit(0)
            except Exception, e:
                print "Some sort of error sending %s: %s" % (encoded, e)
                self.errors += 1
            

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

    if intersection:
        #don't block time-sensitive tracking messages
        pinger.queue.append(data)
    else:
        pinger.to_send = data

quitting = False
def quit_main_loop(*dump):
    global quitting
    quitting = True
    if pinger:
        pinger.quitting = True
    sys.exit(0)

def send_gps_observation():
    gps_instance.query("o\r\n")
    gps_instance.poll #do not actually call it, for some reason
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
    global pinger

    if tracking:
        tracking = False
        pinger.quitting = True
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

    gps_sender_signal = gobject.timeout_add(1000, send_gps_observation)

    pinger = Pinger(url_field.get_text())
    pinger.start()

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

    source_id = gobject.timeout_add(5000, reenable_stop_button)


def store_network_list(db, networks):
    now = str(int(datetime.now().strftime("%s")))

    for cell in networks:
        db.execute("insert into networks(time, address, quality) values (?, ?, ?);", (now, cell['address'], cell.get('quality')))
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
        while not quitting:
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

def get_dbus_object (bus, busname , objectpath , interface):
    dbus_object = bus.get_object(busname, objectpath)
    return dbus.Interface(dbus_object, dbus_interface=interface)

class GPRSController:
    def __init__(self):
        self.gsm_bus = system_bus.get_object ('org.freesmartphone.ogsmd', '/org/freesmartphone/GSM/Device')
        self.gprs = dbus.Interface (self.gsm_bus, dbus_interface = 'org.freesmartphone.GSM.PDP')

    def restart_connection(self):
        print "bringing down GPRS"
        self.gprs.DeactivateContext()
        time.sleep(5)

        print "starting GPRS"
        self.gprs.ActivateContext(gprs_apn, gprs_login, gprs_password)
        time.sleep(5)

pinger = None
def keep_online():
    while not quitting:
        time.sleep(1)
        if pinger and pinger.errors >= 2:
            gprs.restart_connection()
            pinger.errors = 0

system_bus = dbus.SystemBus()

print "Init wifi"
wifi = get_dbus_object (system_bus, "org.freesmartphone.odeviced", "/org/freesmartphone/Device/PowerControl/WiFi", "org.freesmartphone.Device.PowerControl")
wifi.SetPower(True)

print "Turn off suspend"
power = get_dbus_object (system_bus, "org.shr.ophonekitd.Usage", "/org/shr/ophonekitd/Usage", "org.shr.ophonekitd.Usage")

power.RequestResource('CPU')
power.RequestResource('Display')

print "Init gps"
init_gps()
location_db = sqlite3.connect('location.db')
init_location_db(location_db)

print "Init gprs"
gprs = GPRSController()
gprs.restart_connection()

print "Start tracking networks and keepalive"
for target in (track_networks, keep_online):
    thread = Thread(target=target)
    thread.setDaemon(True)
    thread.start()


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

layout.add(url_field)

layout.add(gtk.Label("id"))
id_field = gtk.Entry()
id_field.set_text(str(randint(100,1000000)))
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

while 1:
    time.sleep(0.005)
    gtk.main_iteration(block=False)

quit_main_loop()
