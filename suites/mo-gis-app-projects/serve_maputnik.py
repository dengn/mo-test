"""Serve the unmodified pinned Maputnik build and local style fixtures."""
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
import json
P=Path(__file__).resolve().parent
styles=P/'maputnik-styles';styles.mkdir(exist_ok=True)
for engine in ['mo','pg']:
    base='http://127.0.0.1:18880/collections/'+engine+'-'
    style={'version':8,'name':engine.upper()+' GIS application test','center':[116.315,39.815],'zoom':12,
        'sources':{k:{'type':'geojson','data':base+k+'/items?f=json&limit=500'} for k in ['points','routes','zones']},
        'layers':[{'id':'background','type':'background','paint':{'background-color':'#e8ecef'}},
            {'id':'zones','type':'fill','source':'zones','paint':{'fill-color':'#16a085','fill-opacity':0.25}},
            {'id':'routes','type':'line','source':'routes','paint':{'line-color':'#ee8800','line-width':3}},
            {'id':'points','type':'circle','source':'points','paint':{'circle-color':'#2266cc','circle-radius':4,'circle-stroke-width':1,'circle-stroke-color':'#ffffff'}}]}
    styles.joinpath(engine+'-style.json').write_text(json.dumps(style,indent=2)+'\n')
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(P/'projects/maputnik/dist'),**kwargs)
    def translate_path(self,path):
        if path.startswith('/maputnik/'):
            path=path[len('/maputnik'):]
        if path.startswith('/styles/'):
            name=path.split('?',1)[0].rsplit('/',1)[-1]
            return str(styles/name)
        return super().translate_path(path)
ThreadingHTTPServer(('127.0.0.1',18885),Handler).serve_forever()
