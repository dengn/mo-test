"""Small native Wagtail starter; all credentials and schema names come from env."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SECRET_KEY = os.environ['MO_NATIVE_SECRET_KEY']
DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
INSTALLED_APPS = [
    'home', 'wagtail.contrib.forms', 'wagtail.contrib.redirects', 'wagtail.embeds',
    'wagtail.sites', 'wagtail.snippets', 'wagtail.documents', 'wagtail.images',
    'wagtail.search', 'wagtail.admin', 'wagtail', 'modelcluster', 'taggit',
    'django_filters', 'django.contrib.admin', 'django.contrib.auth',
    'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages',
    'django.contrib.staticfiles',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'wagtail.contrib.redirects.middleware.RedirectMiddleware',
]
ROOT_URLCONF = 'urls'
WSGI_APPLICATION = 'wsgi.application'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [],
              'APP_DIRS': True, 'OPTIONS': {'context_processors': [
                  'django.template.context_processors.request',
                  'django.contrib.auth.context_processors.auth',
                  'django.contrib.messages.context_processors.messages']}}]
DATABASES = {'default': {
    'ENGINE': 'matrixone_backend', 'HOST': os.environ['MO_HOST'], 'PORT': os.environ['MO_PORT'],
    'USER': os.environ['MO_USER'], 'PASSWORD': os.environ['MO_PASSWORD'],
    'NAME': os.environ['MO_NATIVE_SCHEMA'], 'OPTIONS': {'charset': 'utf8mb4', 'use_pure': True},
}}
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
WAGTAIL_SITE_NAME = 'Native regression'
WAGTAILADMIN_BASE_URL = os.environ['MO_NATIVE_BASE_URL']
WAGTAILSEARCH_BACKENDS = {'default': {'BACKEND': 'wagtail.search.backends.database'}}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000
