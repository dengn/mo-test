import json,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/workspace/cache/ms-playwright/chromium-1234/chrome-linux64/chrome',headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda err:errors.append(str(err)));page.goto((root/'index.html').as_uri());page.wait_for_selector('#body tr');assert page.locator('#body tr').count()==100
 first=page.locator('#body tr').first.inner_text();assert first.startswith('0\t');page.locator('#q').fill('99999');assert page.locator('#body tr').count()==1;assert page.locator('#body tr').inner_text().startswith('99999\t');page.locator('#q').fill('causal');assert page.locator('#body tr').count()==100;assert '10000' in page.locator('#count').inner_text();page.locator('#next').click();assert '页 2' in page.locator('#count').inner_text();page.locator('#q').fill('');page.screenshot(path=str(root/'browser-preview.png'),full_page=False);assert not errors;result=dict(console_errors=errors,first_row=first,last_case_found=True,domain_filter_matches=10000,pagination=True);(root/'browser-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(result);browser.close()
