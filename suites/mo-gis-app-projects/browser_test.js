const {chromium}=require('/workspace/mo-gis-postgis/web/node_modules/playwright-core');
const fs=require('fs');const assert=require('assert');const P='/workspace/mo-gis-app-projects';
const records=[];
function record(r){records.push(r);fs.writeFileSync(P+'/browser-results.json',JSON.stringify(records,null,2));fs.appendFileSync(P+'/workflow-results.jsonl',JSON.stringify(r)+'\n');console.log(r.project,r.engine,r.workflow,r.status);}
(async()=>{
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
for(const engine of ['pg','mo']){
 const start=Date.now();const r={project:'Maputnik',engine,phase:'OGC_API_real_application',workflow:'browser_render_UI_style_edit_export_reimport'};
 const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
 await context.addInitScript(()=>Object.defineProperty(window,'showSaveFilePicker',{value:undefined,configurable:true}));
 await context.route('**/*',async route=>{
  const url=route.request().url();
  if(url==='https://unpkg.com/@mapbox/mapbox-gl-rtl-text@0.2.3/mapbox-gl-rtl-text.min.js')return route.fulfill({path:P+'/maputnik-styles/rtl-text-plugin.js',contentType:'application/javascript'});
  if(url.startsWith('http')&&!url.startsWith('http://127.0.0.1:'))return route.abort();
  return route.continue();
 });
 const errors=[],responses=[];const page=await context.newPage();page.on('dialog',d=>d.accept());page.on('pageerror',e=>errors.push(String(e)));
 page.on('response',async resp=>{if(resp.url().includes('/collections/')){const j=await resp.json();responses.push({url:resp.url(),status:resp.status(),features:j.features?.length});}});
 try{
  await page.goto('http://127.0.0.1:18885/?style='+encodeURIComponent('http://127.0.0.1:18885/styles/'+engine+'-style.json'),{waitUntil:'domcontentloaded'});
  await page.locator('[data-wd-key="nav:export"]').waitFor();
  const limit=Date.now()+15000;while(Date.now()<limit&&!['points','routes','zones'].every(k=>responses.some(v=>v.url.includes(engine+'-'+k+'/')&&v.features===({points:259,routes:16,zones:4})[k])))await page.waitForTimeout(100);
  assert(['points','routes','zones'].every(k=>responses.some(v=>v.url.includes(engine+'-'+k+'/')&&v.features===({points:259,routes:16,zones:4})[k])),JSON.stringify(responses));
  await page.locator('[data-wd-key="layer-list-item:points"]').click();
  await page.locator('[data-wd-key="layer-list-item:points:toggle-visibility"]').click();
  await page.waitForTimeout(800);await page.screenshot({path:P+'/maputnik-'+engine+'-lines-polygons.png'});
  await page.locator('[data-wd-key="layer-list-item:points:toggle-visibility"]').click();
  const radius=page.locator('[data-wd-key="spec-field-input:circle-radius"]');assert.equal(await radius.inputValue(),'4');
  await radius.fill('9');await radius.press('Tab');
  const color=page.locator('input[name="circle-color"]');await color.fill('#cc2255');await color.press('Tab');
  await page.waitForTimeout(1500);await page.screenshot({path:P+'/maputnik-'+engine+'-edited.png'});
  await page.locator('[data-wd-key="nav:export"]').click();
  const pending=page.waitForEvent('download');await page.locator('[data-wd-key="modal:export"]').getByRole('button',{name:'Save',exact:true}).click();
  const download=await pending;const filename=P+'/maputnik-'+engine+'-exported-style.json';await download.saveAs(filename);
  const style=JSON.parse(fs.readFileSync(filename));const circle=style.layers.find(v=>v.id==='points');assert.equal(circle.paint['circle-radius'],9);assert.equal(circle.paint['circle-color'],'#cc2255');
  for(const k of ['points','routes','zones'])assert(style.sources[k].data.includes('/collections/'+engine+'-'+k+'/items'));
  fs.copyFileSync(filename,P+'/maputnik-styles/'+engine+'-exported-style.json');
  const second=await context.newPage();second.on('dialog',d=>d.accept());second.on('pageerror',e=>errors.push(String(e)));
  await second.goto('http://127.0.0.1:18885/?style='+encodeURIComponent('http://127.0.0.1:18885/styles/'+engine+'-exported-style.json'),{waitUntil:'domcontentloaded'});
  await second.locator('[data-wd-key="layer-list-item:points"]').click();assert.equal(await second.locator('[data-wd-key="spec-field-input:circle-radius"]').inputValue(),'9');assert.equal(await second.locator('input[name="circle-color"]').inputValue(),'#cc2255');
  await second.waitForTimeout(1500);await second.screenshot({path:P+'/maputnik-'+engine+'-reimported.png'});assert.deepEqual(errors,[]);
  r.status='pass';r.details={GeoJSON_points:259,GeoJSON_routes:16,GeoJSON_zones:4,style_edit:{radius:9,color:'#cc2255'},exported_style:filename.split('/').pop(),reimport_verified:true,page_errors:errors,actual_API_responses:responses,external_asset:'Actual pinned RTL script served from locally downloaded copy; no GIS responses mocked'};
 }catch(e){r.status='error';r.error={message:String(e),stack:e.stack,page_errors:errors,API_responses:responses};}
 r.seconds=(Date.now()-start)/1000;record(r);await context.close();
}
const r={project:'uMap',engine:'mo',phase:'hybrid_PostGIS_metadata_MO_data',workflow:'browser_live_MO_layer_local_geometries_and_popup'};
const context=await browser.newContext({viewport:{width:1440,height:1000}});await context.route('**/*',route=>route.request().url().startsWith('http')&&!route.request().url().startsWith('http://127.0.0.1:')?route.abort():route.continue());
const page=await context.newPage(),errors=[],api=[];page.on('pageerror',e=>errors.push(String(e)));page.on('response',async resp=>{if(resp.url().includes('/collections/mo-points/')){const j=await resp.json();api.push({url:resp.url(),status:resp.status(),features:j.features.length});}});
try{
 const ids=JSON.parse(fs.readFileSync(P+'/umap-map-identifiers.json'));
 await page.goto('http://127.0.0.1:18881'+ids.view_url,{waitUntil:'domcontentloaded'});
 await page.getByText('MO 实时点位 (259)',{exact:true}).waitFor();await page.getByText('本地采集 (3)',{exact:true}).waitFor();
 await page.getByText("点位 1 café O'Brien",{exact:true}).first().click();await page.locator('.leaflet-popup').waitFor();
 const popup=await page.locator('.leaflet-popup').innerText();assert(popup.includes("点位 1 café O'Brien"),popup);
 const markers=await page.locator('.leaflet-marker-icon').count(),paths=await page.locator('.leaflet-overlay-pane path').count();assert(markers>=256,markers);assert(paths>=2,paths);assert(api.some(v=>v.status===200&&v.features===259));assert.deepEqual(errors,[]);
 await page.screenshot({path:P+'/umap-mo-live-map-popup.png'});
 r.status='pass';r.details={remote_MO_features:259,local_features:3,visible_markers:markers,SVG_paths:paths,Unicode_popup:popup,API_responses:api,page_errors:errors,metadata_backend:'PostGIS'};
}catch(e){r.status='error';r.error={message:String(e),stack:e.stack,API_responses:api,page_errors:errors};}
record(r);await context.close();
}finally{await browser.close();}
assert(records.every(r=>r.status==='pass'),JSON.stringify(records.filter(r=>r.status!=='pass')));
})().catch(e=>{console.error(e);process.exit(1);});
