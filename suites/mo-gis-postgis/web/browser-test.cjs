const {chromium}=require('playwright-core');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1100,height:800}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:18189/');await page.waitForFunction(()=>window.gisLoaded===true);
 const out=[];
 for(const engine of ['mo','pg']){
  await page.selectOption('#engine',engine);await page.waitForFunction(()=>window.gisLoaded===true&&document.querySelector('#status').textContent.includes(document.querySelector('#engine').value));
  await page.waitForFunction(()=>document.querySelector('canvas')!==null);
  const state=await page.evaluate(()=>({count:window.gisSource.getFeatures().length,ids:window.gisSource.getFeatures().map(f=>f.getId()).sort(),types:window.gisSource.getFeatures().map(f=>f.getGeometry().getType()),extent:window.gisSource.getExtent(),canvasCount:document.querySelectorAll('canvas').length,textStatus:document.querySelector('#status').textContent}));
  if(state.count!==3||state.types.some(t=>t!=='Point')||state.canvasCount<1)throw Error(JSON.stringify(state));
  await page.screenshot({path:__dirname+`/openlayers-${engine}.png`,fullPage:true});out.push({engine,status:'pass',...state});
 }
 if(errors.length)throw Error(errors.join(';'));
 fs.writeFileSync(__dirname+'/browser-results.json',JSON.stringify({results:out,pageErrors:errors},null,2));await browser.close();
 console.log(JSON.stringify(out));
})().catch(e=>{console.error(e);process.exit(1)});
