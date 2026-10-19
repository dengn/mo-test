from django.urls import re_path
from django.views.static import serve
from django.conf import settings
from umap.urls import urlpatterns
urlpatterns = list(urlpatterns) + [
    re_path(r'^static/(?P<path>.*)$',serve,{'document_root':settings.STATIC_ROOT}),
    re_path(r'^uploads/(?P<path>.*)$',serve,{'document_root':settings.MEDIA_ROOT}),
]
