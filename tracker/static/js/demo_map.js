function createMap(map_id) {
    var bounds = new OpenLayers.Bounds(-2.003750834E7,-2.003750834E7,2.003750834E7,2.003750834E7);
    var options = {
        projection: 'EPSG:900913',
        maxExtent: bounds,
        maxResolution: 156543.03390625,
        numZoomLevels: 20,
    };
    map = new OpenLayers.Map('map', options);
    var baseMap = new OpenLayers.Layer.WMS(
        'OpenStreetMap',
        'http://demo.opengeo.org/geoserver_openstreetmap/gwc/service/wms',
        {
            layers: 'openstreetmap',
            format: 'image/png',
        }
    );

    map.addLayers([baseMap]);
    var center = new OpenLayers.LonLat(-73.99, 40.76); // Center of the universe
    center.transform(new OpenLayers.Projection('EPSG:4326'), map.getProjectionObject());
    map.setCenter(center, 14);

    $('#load-btn').click(function() {
        var bus_id = $('#bus-id').get(0).value;
        var kmlUrl = 'kml?bus_id=' + bus_id;
        loadBusKml(kmlUrl, 'bus ' + bus_id);
    });
}

function loadBusKml(kmlUrl, name) {
    var layerOptions = {
        format: OpenLayers.Format.KML,
        projection: new OpenLayers.Projection('EPSG:4326'),
    };
    var layer = new OpenLayers.Layer.GML(name, kmlUrl, layerOptions);
    layer.events.register('loadend', layer, function() {
        this.map.zoomToExtent(this.getDataExtent()); 
        var busData = []
        // Store references to the features so we have them if they're removed
        // from the map
        for (var i=0; i<layer.features.length; i++) {
            busData[i] = layer.features[i];
        }
        function refreshBusData() {
            var val = $(this).slider('value');
            // TODO: Make less dumb (not sure if this necessary removes all the
            // features it should. May also make more sense to toggle styles
            // instead?)
            layer.removeFeatures(busData.slice(val));
            layer.addFeatures(busData.slice(0,val));
        }
        $('#time-slider').slider({
            max: busData.length,
            range: 'min',
            value: 0,
            slide: refreshBusData,
            change: refreshBusData
        });
    })
    map.addLayer(layer);

    return layer;
}
