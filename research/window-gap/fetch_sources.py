"""Fetch official pages through inherited proxy/CA and extract names, not articles."""
import concurrent.futures,datetime,hashlib,html,json,re,urllib.parse,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PAGES={
 'clickhouse_window':'https://clickhouse.com/docs/reference/functions/window-functions',
 'dolphindb_analytic':'https://docs.dolphindb.com/en/Programming/SQLStatements/analytic_functions.html',
 'dolphindb_categories':'https://docs.dolphindb.com/en/Functions/funcs_by_topics.html',
 'dolphindb_m':'https://docs.dolphindb.com/en/Functions/Themes/mFunctions.html',
 'dolphindb_tm':'https://docs.dolphindb.com/en/Functions/Themes/tmFunctions.html',
 'dolphindb_cum':'https://docs.dolphindb.com/en/Functions/Themes/cumFunctions.html',
 'dolphindb_m_topn':'https://docs.dolphindb.com/en/Functions/Themes/mTopN.html',
 'dolphindb_tm_topn':'https://docs.dolphindb.com/en/Functions/Themes/tmTopN.html',
 'dolphindb_cum_topn':'https://docs.dolphindb.com/en/Functions/Themes/cumTopN.html',
 'dolphindb_talib':'https://docs.dolphindb.com/en/Functions/Themes/TALib.html',
 'dolphindb_ewm':'https://docs.dolphindb.com/en/Functions/e/ewmMean.html',
 'dolphindb_window':'https://docs.dolphindb.com/en/Functions/Templates/window.html',
 'dolphindb_twindow':'https://docs.dolphindb.com/en/Functions/Templates/twindow.html',
 'dolphindb_moving':'https://docs.dolphindb.com/en/Functions/Templates/moving.html',
 'dolphindb_moving_dynamic':'https://docs.dolphindb.com/en/Functions/Templates/movingDynamic.html',
 'dolphindb_moving_valid':'https://docs.dolphindb.com/en/Functions/Templates/movingvalid.html',
 'dolphindb_rolling':'https://docs.dolphindb.com/en/Functions/Templates/rolling.html',
 'dolphindb_stream':'https://docs.dolphindb.com/en/Streaming/stateful_operator.html',
 'dolphindb_window_tutorial':'https://docs.dolphindb.com/en/3.00.5/Tutorials/Window_Calculations_in_DolphinDB.html',
 'mo_window':'https://docs.matrixorigin.cn/mo/zh/latest/MatrixOne/Develop/read-data/window-function/window-function.html',
 'mo_time_window':'https://docs.matrixorigin.cn/mo/zh/latest/MatrixOne/Develop/read-data/window-function/time-window.html',
}
def text(s):return html.unescape(re.sub('<[^>]+>',' ',s)).strip()
def anchors(s,url):
 out={}
 for href,label in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',s,re.S|re.I):
  label=text(label).strip();canonical=urllib.parse.urlparse(href).path.rsplit('/',1)[-1].removesuffix('.html')
  canonical={'miminlast':'miminLast','mimaxlast':'mimaxLast'}.get(canonical,canonical)
  if re.fullmatch('[A-Za-z][A-Za-z0-9_]*',canonical) and '/Functions/' in urllib.parse.urljoin(url,href):out[canonical]=urllib.parse.urljoin(url,href)
 return out
def fetch(item):
 name,url=item;when=datetime.datetime.now(datetime.timezone.utc).isoformat()
 try:
  with urllib.request.urlopen(url,timeout=60) as r:data=r.read();resolved=r.url
  (ROOT/'cache'/f'{name}.html').write_bytes(data);return dict(id=name,url=url,resolved_url=resolved,retrieved_at=when,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),status='ok')
 except Exception as exc:return dict(id=name,url=url,retrieved_at=when,status='error',error=str(exc))
def main():
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:manifest=list(pool.map(fetch,PAGES.items()))
 (ROOT/'sources/manifest.json').write_text(json.dumps(manifest,indent=2));catalog={};families={};notes=[]
 for name in ['dolphindb_m','dolphindb_tm','dolphindb_cum','dolphindb_m_topn','dolphindb_tm_topn','dolphindb_cum_topn','dolphindb_talib']:
  source=(ROOT/'cache'/f'{name}.html').read_text();m=re.search(r'<h2\b[^>]*>.*?List of Functions.*?</h2>(.*?)(?=<h2\b)',source,re.S|re.I)
  if not m:
   # DITA pages use a section wrapper rather than heading-level markup.
   start=source.find('List of Functions');end=source.find('Windowing Logic',start);assert start>=0 and end>start,name;chunk=source[start:end]
  else:chunk=m.group(1)
  entries=anchors(chunk,PAGES[name]);families[name]=sorted(entries)
  for fn,url in entries.items():catalog.setdefault(fn,dict(name=fn,url=url,families=[]))['families'].append(name)
  if name=='dolphindb_cum' and 'cumprod' in entries:notes.append('cum-functions overview prints mprod at one link; canonical name is cumprod, verified by function-page link and categories.')
 # Additional indexed window helpers and operators missing from the overview lists.
 source=(ROOT/'cache/dolphindb_categories.html').read_text()
 for chunk in re.findall(r'<li\b[^>]*>(.*?)</li>',source,re.S|re.I):
  t=' '.join(text(chunk).split())
  if not any(t.startswith(prefix) for prefix in ['Cumulative Window:','Moving:','Time-Based Moving:','mTopN:','tmTopN:','TA-Lib:']):continue
  label=t.split(':',1)[0];entries=anchors(chunk,PAGES['dolphindb_categories']);families['categories_'+label]=sorted(entries)
  for fn,url in entries.items():catalog.setdefault(fn,dict(name=fn,url=url,families=[]))['families'].append('categories_'+label)
 for fn in ['ewmMean','ewmVar','ewmStd','ewmCov','ewmCorr']:
  catalog[fn]=dict(name=fn,url=f'https://docs.dolphindb.com/en/Functions/e/{fn}.html',families=['exponential'])
 # SQL OVER supported-function table, independently listed from moving API families.
 source=(ROOT/'cache/dolphindb_analytic.html').read_text();start=source.find('Supported Functions',source.find('window_frame'));start=source.find('<table',start);end=source.find('</table>',start);assert start>=0 and end>start
 names=[]
 for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',source[start:end],re.S):
  cells=re.findall(r'<td\b[^>]*>(.*?)</td>',row,re.S)
  if cells:names.append(text(cells[0]).split('(',1)[0].strip())
 assert len(names)==39,(len(names),names)
 (ROOT/'dolphindb-catalog.json').write_text(json.dumps(dict(sql_analytic_names=names,named_window_apis=sorted(catalog.values(),key=lambda r:r['name']),families=families,notes=notes,scope='Union of the six official m/tm/cum/TopN themes, categories window lists, TA-Lib moving averages, and five EWM APIs. Higher-order templates and streaming engine APIs are listed separately; all general mathematical, row-vector and plugin functions excluded.'),indent=2))
 print('Official sources',[(r['id'],r['status']) for r in manifest],flush=True);print('DolphinDB',len(names),'SQL OVER functions;',len(catalog),'named window APIs', {k:len(v) for k,v in families.items()},flush=True)
if __name__=='__main__':main()
