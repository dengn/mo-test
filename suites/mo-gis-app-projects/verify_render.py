"""Check real Maputnik rendered line/fill colors after hiding the point layer."""
import json
from pathlib import Path
from PIL import Image
P=Path(__file__).resolve().parent
summary=[]
for engine in ['pg','mo']:
    file=P/('maputnik-'+engine+'-lines-polygons.png')
    im=Image.open(file).convert('RGB');pixels=list(im.crop((570,40,1440,1000)).getdata())
    orange=sum(abs(r-238)<8 and abs(g-136)<8 and b<15 for r,g,b in pixels)
    green=sum(abs(r-179)<12 and abs(g-217)<12 and abs(b-213)<12 for r,g,b in pixels)
    summary.append({'engine':engine,'image':file.name,'line_orange_pixels':orange,'fill_green_pixels':green})
    assert orange>100 and green>100,(engine,orange,green)
(P/'maputnik-render-pixel-verification.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
