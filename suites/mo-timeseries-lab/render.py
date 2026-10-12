"""Check both standalone artifacts, including all-ID filters and mobile width."""
import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent
def main():
 os.environ['PLAYWRIGHT_BROWSERS_PATH']='/workspace/cache/ms-playwright';checks={};errors=[]
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
  for label,width in [('desktop',1440),('mobile',390)]:
   page=browser.new_page(viewport={'width':width,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)));page.goto((ROOT/'report.html').as_uri());page.wait_for_selector('#cases tr');checks[label+'_all_case_ids']=page.evaluate('data.length')==10000;checks[label+'_default_count']=page.locator('#count').inner_text()=='10000 / 10000';page.locator('#status').select_option('sql_or_stage_error');checks[label+'_failure_count']=page.locator('#count').inner_text()=='200 / 10000';page.locator('#status').select_option('');page.locator('#family').select_option('47');checks[label+'_family_count']=page.locator('#count').inner_text()=='200 / 10000';page.locator('#family').select_option('');page.locator('#id').fill('9999');checks[label+'_last_case']=page.locator('#count').inner_text()=='1 / 10000' and page.locator('#cases td').first.inner_text()=='9999';page.locator('#id').fill('9999.8');checks[label+'_fraction_id_floor']=page.locator('#count').inner_text()=='1 / 10000';page.locator('#id').fill('');page.locator('#client').select_option('pandas_sqlalchemy');checks[label+'_client_count']=page.locator('#count').inner_text()=='5000 / 10000';page.locator('#client').select_option('');checks[label+'_plot_loaded']=page.locator('img').evaluate('(e)=>e.complete && e.naturalWidth>0');checks[label+'_no_document_overflow']=page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
   if label=='desktop':page.screenshot(path=str(ROOT/'report-preview.png'),full_page=False)
   page.close()
  gap=Path('/workspace/mo-window-gap');page=browser.new_page(viewport={'width':390,'height':900});page.on('pageerror',lambda e:errors.append(str(e)));page.goto((gap/'report.html').as_uri());checks['gap_rows']=page.locator('#count').inner_text().strip()=='53 / 53';page.locator('#search').fill('lagInFrame');checks['gap_filter']=page.locator('#count').inner_text().strip()=='1 / 53';checks['gap_mobile_no_overflow']=page.evaluate('document.documentElement.scrollWidth <= innerWidth+1');page.locator('#search').fill('');page.screenshot(path=str(gap/'report-preview.png'),full_page=False);browser.close()
 checks['no_js_errors']=not errors;result=dict(checks=checks,errors=errors,all_passed=all(checks.values()));(ROOT/'render-validation.json').write_text(json.dumps(result,indent=2));(Path('/workspace/mo-window-gap')/'render-validation.json').write_text(json.dumps(result,indent=2));print(result);assert result['all_passed']
if __name__=='__main__':main()
