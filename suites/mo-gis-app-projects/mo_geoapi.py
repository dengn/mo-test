"""Application adapter: explicit SRID and bbox intersection semantics."""
from sqlalchemy import func
from pygeoapi.provider.sql import MySQLProvider
from pygeoapi.crs import get_srid

class MySQLWithSRIDProvider(MySQLProvider):
    def _get_bbox_filter(self,bbox):
        if not bbox:
            return True
        a,b,c,d=bbox
        wkt=f'POLYGON(({a} {b},{c} {b},{c} {d},{a} {d},{a} {b}))'
        return func.ST_Intersects(func.ST_GeomFromText(wkt,get_srid(self.storage_crs)),getattr(self.table_model,self.geom))
