import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent;os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH','/workspace/cache/ms-playwright')
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1440,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto((root/'report.html').as_uri(),wait_until='load');assert '复杂关联' in page.locator('h1').inner_text();assert '10000' in page.locator('table').first.inner_text()
    page.locator('#case-id').fill('9999');assert '9999' in page.locator('#detail').inner_text();assert 'integrated_planning' in page.locator('#detail').inner_text()
    page.locator('#mission').select_option('credit_calibration');assert 'credit_calibration' in page.locator('#detail').inner_text()
    page.locator('#case-id').fill('1.5');assert '"case_id": 1,' in page.locator('#detail').inner_text()
    page.locator('#case-id').fill('0');assert not errors
    assert page.locator('img').evaluate('(i)=>i.complete && i.naturalWidth>0')
    layout=page.evaluate('({overflow:document.documentElement.scrollWidth>window.innerWidth,height:document.documentElement.scrollHeight})');assert not layout['overflow']
    page.screenshot(path=str(root/'report-preview.png'));(root/'render-validation.json').write_text(json.dumps({'layout':layout,'javascript_errors':errors,'case_lookup_9999':'pass','mission_selection':'pass','fractional_case_id_normalized':'pass'},indent=2));browser.close()
print('interactive report validation passed')
