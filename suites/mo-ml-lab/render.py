"""Browser verification of real report data, filters, case lookup and layout."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from data import ROOT
def main():
 checks={};errors=[]
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)));page.goto((ROOT/'report.html').as_uri(),wait_until='load');assert page.locator('#main-count').inner_text()=='20,000';checks['main_20000']=True
  assert page.locator('#missions tr').count()==20;checks['mission_rows_20']=True;page.locator('#case-id').fill('19999');page.locator('#lookup').click();assert '#19999' in page.locator('#case-title').inner_text();assert 'gcn' in page.locator('#case-title').inner_text();checks['last_case']=True
  page.locator('#case-id').fill('19999.9');page.locator('#lookup').click();assert page.locator('#case-id').input_value()=='19999';checks['fractional_id_normalized']=True
  page.locator('#arch').select_option('attention');assert 'attention' in page.locator('#case-title').inner_text();assert '4,000' in page.locator('#match').inner_text();checks['architecture_filter']=True
  page.locator('#task').select_option('classification');assert '1,000' in page.locator('#match').inner_text();checks['task_filter']=True;page.locator('#client').select_option('pandas_sqlalchemy');assert '500' in page.locator('#match').inner_text();checks['client_filter']=True
  assert page.evaluate('document.querySelector("img").complete && document.querySelector("img").naturalWidth>0');checks['figure_loaded']=True;assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth');checks['desktop_no_overflow']=True
  page.locator('#arch').select_option('');page.locator('#task').select_option('');page.locator('#client').select_option('');page.locator('#case-id').fill('0');page.locator('#lookup').click();page.screenshot(path=str(ROOT/'report-preview.png'),full_page=True);page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth');checks['mobile_no_overflow']=True;assert not errors,errors;checks['no_js_errors']=True;browser.close()
 (ROOT/'render-validation.json').write_text(json.dumps(dict(checks=checks,errors=errors),indent=2));print(checks)
if __name__=='__main__':main()
