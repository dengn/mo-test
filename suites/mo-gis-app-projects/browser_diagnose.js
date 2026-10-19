const {chromium}=require('/workspace/mo-gis-postgis/web/node_modules/playwright-core');
const fs=require('fs');const P='/workspace/mo-gis-app-projects';
(async()=>{
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
await context.addInitScript(()=>{Object.defineProperty(window,'showSaveFilePicker',{value:undefined,configurable:true});});
const out=[];
for(const project of ['Maputnik','uMap']){
 const page=await context.newPage();const errors=[],api=[];
 page.on('dialog',d=>d.accept());page.on('pageerror',e=>errors.push(String(e)));
 page.on('response',async r=>{if(r.url().includes('/collections/')){try{const j=await r.json();api.push({url:r.url(),status:r.status(),features:j.features?.length});}catch(e){api.push({url:r.url(),error:String(e)});}}});
 await page.route('**/*',async route=>{const url=route.request().url();if(url.startsWith('http')&&!url.startsWith('http://127.0.0.1:'))return route.abort();return route.continue();});
 const ids=JSON.parse(fs.readFileSync(P+'/umap-map-identifiers.json'));
 const url=project==='Maputnik'?'http://127.0.0.1:18885/?style='+encodeURIComponent('http://127.0.0.1:18885/styles/mo-style.json'):'http://127.0.0.1:18881'+ids.view_url;
 try{
 await page.goto(url,{waitUntil:'domcontentloaded',timeout:30000});await page.waitForTimeout(4500);
 if(project==='Maputnik')await page.locator('[data-wd-key="layer-list-item:points"]').click({timeout:10000}).catch(()=>page.getByText('points',{exact:true}).first().click());
 await page.screenshot({path:P+'/'+project.toLowerCase()+'-browser-initial.png'});
 const text=await page.locator('body').innerText();const inputs=await page.locator('input').evaluateAll(xs=>xs.map(x=>({type:x.type,name:x.name,id:x.id,value:x.value,aria:x.getAttribute('aria-label'),outer:x.outerHTML.slice(0,450)})));
 const keys=await page.locator('[data-wd-key]').evaluateAll(xs=>xs.map(x=>({key:x.getAttribute('data-wd-key'),text:x.innerText?.slice(0,70)})));
 out.push({project,url,status:'loaded',text,inputs,keys,errors,api,leafletMarkers:await page.locator('.leaflet-marker-icon').count(),leafletPaths:await page.locator('.leaflet-overlay-pane path').count()});
 }catch(e){out.push({project,status:'error',error:String(e),errors,api,text:await page.locator('body').innerText().catch(()=>'' )});}
 await page.close();
}
fs.writeFileSync(P+'/browser-diagnose.json',JSON.stringify(out,null,2));console.log(JSON.stringify(out.map(({project,status,errors,api,leafletMarkers,leafletPaths,error})=>({project,status,errors,api,leafletMarkers,leafletPaths,error})),null,2));
await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
