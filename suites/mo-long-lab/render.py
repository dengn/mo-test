import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent;os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH','/workspace/cache/ms-playwright')
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1440,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto((root/'report.html').as_uri(),wait_until='load')
 assert page.locator('h1').inner_text()=='MatrixOne 长分析组合 10,000 例实测'
 summary=page.locator('table').first.inner_text();assert '10000' in summary
 if page.locator('img').count():assert page.locator('img').evaluate('(i)=>i.complete && i.naturalWidth>0')
 assert not errors
 page.screenshot(path=str(root/'report-preview.png'));layout=page.evaluate('({overflow:document.documentElement.scrollWidth>window.innerWidth,height:document.documentElement.scrollHeight})');assert not layout['overflow']
 (root/'render-validation.json').write_text(json.dumps({'layout':layout,'javascript_errors':errors,'table_count':page.locator('table').count(),'summary':'10000 verified'},indent=2));browser.close()
print('render validation passed')
