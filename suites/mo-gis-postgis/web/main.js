import Map from 'ol/Map.js';
import View from 'ol/View.js';
import GeoJSON from 'ol/format/GeoJSON.js';
import VectorLayer from 'ol/layer/Vector.js';
import VectorSource from 'ol/source/Vector.js';
import {Circle as CircleStyle,Fill,Stroke,Style} from 'ol/style.js';
import 'ol/ol.css';
const source=new VectorSource();
const map=new Map({target:'map',layers:[new VectorLayer({source,style:new Style({image:new CircleStyle({radius:8,fill:new Fill({color:'#137f87'}),stroke:new Stroke({color:'#fff',width:2})})})})],view:new View({center:[0,0],zoom:2})});
window.gisMap=map;window.gisSource=source;window.gisLoaded=false;
async function load(){
 window.gisLoaded=false;
 const engine=document.querySelector('#engine').value;
 const response=await fetch(`/api/${engine}/features`);if(!response.ok)throw Error(`API ${response.status}`);
 const data=await response.json();const features=new GeoJSON().readFeatures(data,{dataProjection:'EPSG:4326',featureProjection:'EPSG:3857'});
 source.clear();source.addFeatures(features);map.getView().fit(source.getExtent(),{padding:[60,60,60,60],maxZoom:14});
 document.querySelector('#status').textContent=`${engine}: ${features.length} features`;window.gisLoaded=true;
}
document.querySelector('#engine').addEventListener('change',()=>load().catch(e=>{document.querySelector('#status').textContent=e.message}));
load().catch(e=>{document.querySelector('#status').textContent=e.message});
