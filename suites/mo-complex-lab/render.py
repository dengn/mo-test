import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH','/workspace/cache/ms-playwright')
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto((root/'report.html').as_uri(),wait_until='load')
 assert page.locator('h1').inner_text()=='MatrixOne 复杂数据科学 100,000 例实测'
 first=page.locator('table').first.inner_text();assert '100000' in first and '98992' in first
 assert page.locator('img').count()==1
 assert page.locator('img').evaluate('(im)=>im.complete && im.naturalWidth>0')
 assert page.locator('a[href="https://github.com/matrixorigin/matrixone/issues/29838"]').count()==1
 assert page.locator('a[href="https://github.com/matrixorigin/matrixone/issues/29839"]').count()==1
 assert not errors
 page.screenshot(path=str(root/'report-preview.png'))
 issues=page.evaluate('({overflow:document.documentElement.scrollWidth>window.innerWidth,width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight})')
 assert not issues['overflow'],issues
 (root/'render-validation.json').write_text(json.dumps({'table_count':page.locator('table').count(),'javascript_errors':errors,'layout':issues,'chart_loaded':True,'canonical_summary':'verified'},indent=2))
 browser.close()
print('report rendered and validated')
