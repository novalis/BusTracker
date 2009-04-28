function createMap(map_id) {
    var bounds = new OpenLayers.Bounds(-2.003750834E7,-2.003750834E7,2.003750834E7,2.003750834E7);
    var options = {
        projection: 'EPSG:900913',
        maxExtent: bounds,
        maxResolution: 156543.03390625,
        numZoomLevels: 20,
    };
    var map = new OpenLayers.Map('map', options);
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
}

