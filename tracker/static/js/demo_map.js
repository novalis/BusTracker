function createMap(map_id) {
    var bounds = new OpenLayers.Bounds(-2.003750834E7,-2.003750834E7,2.003750834E7,2.003750834E7);
    var options = {
        projection: 'EPSG:900913',
        maxExtent: bounds,
        maxResolution: 156543.03390625,
        numZoomLevels: 20
    };
    map = new OpenLayers.Map('map', options);
    var baseMap = new OpenLayers.Layer.WMS(
        'OpenStreetMap',
        'http://maps.opengeo.org/geowebcache/service/wms',
        {
            layers: 'openstreetmap',
            format: 'image/png'
        },
        {
            transitionEffect: 'resize'
        }
    );

    map.addLayers([baseMap]);
    var center = new OpenLayers.LonLat(-73.99, 40.76); // Center of the universe
    center.transform(new OpenLayers.Projection('EPSG:4326'), map.getProjectionObject());
    map.setCenter(center, 14);

    return map;
}

function updateBusLocations() {
    $.getJSON('bus_locations',
        function(data, textStatus) {
            /* Data should be a list of bus observations
               [{bus_id: 1, lat: 74, lon: 42, time: __, route: 'M6 S'},
                ...]

                These need to be turned into vector features.
            */
            if (data.length == 0) {
                // no buses to display
                alert("There are currently no buses to display");
                return;
            }
            var features = [];
            for (var i=0; i<data.length; i++) {
                var busObs = data[i];
                var feature = featureFromLatLon(busObs['lat'], busObs['lon']);
                feature.attributes = {label: busObs['route']};
                features.push(feature);
            }
            var busLayer = map.getLayersByClass('OpenLayers.Layer.Vector')[0];
            if (!busLayer) {
                var style = new OpenLayers.Style({
                    externalGraphic: '/tracker/static/img/bus.png',
                    graphicWidth: 20,
                    graphicHeight: 25,
                    graphicXOffset: -22,
                    label: '${label}',
                    labelAlign: 'lm', // horizontal: left, vertical: middle
                    fontSize: '0.9em',
                    fontWeight: 'bold',
                    fontColor: '#0057a9'
                });
                busLayer = new OpenLayers.Layer.Vector('Buses', {
                    styleMap: new OpenLayers.StyleMap(style)
                });
                map.addLayer(busLayer);
            }
            busLayer.removeFeatures(busLayer.features);
            busLayer.addFeatures(features);
        });
}

// Takes a lat and a lon and returns an OpenLayers.Feature.Vector object.  If
// projection is not specified (either as a string or OpenLayers.Projection
// object), then the resulting point is reprojected as EPSG:900913.
function featureFromLatLon(lat, lon, projection) {
    if (typeof(projection) == 'undefined') {
        projection = new OpenLayers.Projection('EPSG:900913');
    } else if (typeof(projection) == 'string') {
        projection = new OpenLayers.Projection(projection);
    }
    var lonlat = new OpenLayers.LonLat(lon, lat);
    lonlat.transform(new OpenLayers.Projection('EPSG:4326'), projection);

    return new OpenLayers.Feature.Vector(new OpenLayers.Geometry.Point(lonlat.lon, lonlat.lat));
}

function loadKml(url, name) {
    var layerOptions = {
        format: OpenLayers.Format.KML,
        projection: new OpenLayers.Projection('EPSG:4326')
    };
    var layer = new OpenLayers.Layer.GML(name, url, layerOptions);
    map.addLayers([layer]);

    return layer;
}



function loadBusKml(url, name) {
    var styleMap = new OpenLayers.StyleMap({
            fillOpacity: 0.2,
            pointRadius: 5
        });
           
    var lookup = {
        '#tracker_busobservation': {fillColor: "green"},
        '#tracker_intersectionobservation': {fillColor: "red",
                                             fillOpacity: 1.0,
                                             pointRadius: 10}
    }
 
            
    var context = function(feature) {
        return feature.attributes;
    }
    
    styleMap.addUniqueValueRules("default", "styleUrl", lookup, context);

    var layerOptions = {
        format: OpenLayers.Format.KML,
        projection: new OpenLayers.Projection('EPSG:4326'),
        extractAttributes: true,
        styleMap: styleMap
    };
    var layer = new OpenLayers.Layer.GML(name, url, layerOptions);
    map.addLayers([layer]);

    return layer;
}


function loadBusData(url, name) {
    var layer = loadBusKml(url, name); 
    layer.events.register('loadend', layer, function() {
        this.map.zoomToExtent(this.getDataExtent()); 
        //TODO Move all this stuff that doesn't belong in loadBusData
        var busData = []
        // Store references to the features so we have them after they're
        // removed from the map
        for (var i=0; i<layer.features.length; i++) {
            busData[i] = layer.features[i];
        }
        layer.removeFeatures(layer.features);
        
        function refreshBusData() {
            var val = $(this).slider('value');
            // TODO: Add optional arg for adding/removing appropriate features
            // when the slider is dragged (may make sense to bucket features
            // and have a mapping to e.g., secs)
            layer.addFeatures(busData[val]);
        }
        $('#time-slider').slider({
            max: busData.length-1,
            range: 'min',
            value: 0,
            slide: refreshBusData,
            change: refreshBusData
        });
        $('#pause-play-btn').show().click(function() {
            // TODO: Fix ugly hack of using global timer
            if (this.innerHTML == 'Play') {
                this.innerHTML = 'Pause';
                var startVal = $('#time-slider').slider('value');
                timer = animateBusData(startVal);
            } else {
                if (this.innerHTML == 'Reset') {
                    $('#time-slider').slider('value', 0);
                    layer.removeFeatures(layer.features);
                }
                this.innerHTML = 'Play';
                clearInterval(timer);
            }
        });
    })

    return layer;
}

function animateBusData(startVal) {
    var slider = $('#time-slider');
    slider.slider('value', startVal);
    var timer = setInterval(function() {
        if (slider.slider('value') < slider.slider('option', 'max')) {
            slider.slider('value', slider.slider('value') + 1);
        } else {
            clearInterval(timer);
            $('#pause-play-btn').get(0).innerHTML = 'Reset';
        }
    }, 2);
    return timer;
}
