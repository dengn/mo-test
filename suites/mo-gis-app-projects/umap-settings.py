"""Local settings overlay for the real uMap package, with separate databases."""
import os
from pathlib import Path
import pymysql
pymysql.install_as_MySQLdb()
from umap.settings.base import *

P=Path('/workspace/mo-gis-app-projects')
mode=os.environ.get('UMAP_TEST_BACKEND','pg')
SECRET_KEY='local-synthetic-gis-application-test-secret-20261013'
DEBUG=False
ENABLE_ACCOUNT_LOGIN=True
UMAP_ALLOW_ANONYMOUS=True
ALLOWED_HOSTS=['127.0.0.1','localhost','testserver']
CSRF_TRUSTED_ORIGINS=['http://127.0.0.1:18881','http://127.0.0.1:18882','http://127.0.0.1:18884']
SESSION_COOKIE_NAME='sessionid'
CSRF_COOKIE_NAME='csrftoken'
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
STATIC_ROOT=str(P/'umap-static')
MEDIA_ROOT=str(P/('umap-media-'+mode))
MEDIA_URL='/uploads/'
ROOT_URLCONF='umap_urls'
SITE_URL=f'http://127.0.0.1:{18881 if mode=="pg" else 18882 if mode=="mo" else 18884}'
DATABASES={'default':{'ENGINE':'django.contrib.gis.db.backends.postgis' if mode=='pg' else 'django.contrib.gis.db.backends.mysql',
    'NAME':'gis_app_umap','USER':'gis' if mode=='pg' else 'root','PASSWORD':'gis_local_test' if mode=='pg' else '111' if mode=='mo' else '',
    'HOST':'127.0.0.1','PORT':65432 if mode=='pg' else 6013 if mode=='mo' else 63306}}
EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache'}}
AJAX_PROXY_CACHE_DIR=str(P/'umap-proxy-cache')
Path(AJAX_PROXY_CACHE_DIR).mkdir(exist_ok=True)
# Installed package already contains JS/CSS; requests remain local.
LEAFLET_SETTINGS={'TILES':[('Local blank basemap','http://127.0.0.1:18880/static/local-tile.png','Local synthetic test')],
                  'DEFAULT_CENTER':(39.81,116.31),'DEFAULT_ZOOM':12}
