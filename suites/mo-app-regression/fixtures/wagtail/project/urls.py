from django.contrib import admin
from django.urls import include, path
from wagtail.admin import urls as admin_urls
from wagtail import urls as page_urls
from wagtail.api.v2.router import WagtailAPIRouter
from wagtail.api.v2.views import PagesAPIViewSet

router = WagtailAPIRouter('wagtailapi')
router.register_endpoint('pages', PagesAPIViewSet)
urlpatterns = [path('django-admin/', admin.site.urls), path('admin/', include(admin_urls)),
               path('api/v2/', router.urls), path('', include(page_urls))]
