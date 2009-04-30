#!/usr/bin/python

"""This is a simple hack to get manage.py dumpdata-formatted data into
something usable for estimation tests"""
import simplejson

f = open("m6.json")
olddata = simplejson.loads(f.read())
f.close()

data = []
roadsegs = set()
for x in olddata:
    if x["model"].lower() == "tracker.bus":
        if x["fields"]["route"] == "M6 Downtown":
            data.append(x)
    elif x["model"].lower() == "tracker.busobservation":
        if x["fields"]["bus"] == 7:
            data.append(x)
    elif x["model"].lower() == "tracker.route":
        if x["pk"] == "M6 Downtown":
            data.append(x)
    elif x["model"].lower() == "tracker.routesegment":
        if x["fields"]["route"] == "M6 Downtown":
            data.append(x)
            roadsegs.add(x["fields"]["roadsegment"])


roads = set()
for x in olddata:
    if x["model"].lower() == "tracker.roadsegment":
        if x["pk"] in roadsegs:
            data.insert(0, x)
            roads.add(x["fields"]["road"])
                   
for x in olddata:
    if x["model"].lower() == "tracker.road":
        if x["pk"] in roads:
            data.insert(0, x)

f = open("m6b.json", "w")
f.write(simplejson.dumps(data))
f.close()
