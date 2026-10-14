"""Native Django auth ORM provisioning, not SQL account or migration seeding."""
import os
import django
django.setup()
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

user = get_user_model().objects.create_user(
    username='moobserver', email='observer@example.test', password=os.environ['MO_NATIVE_OBSERVER_PASSWORD'])
user.user_permissions.add(Permission.objects.get(content_type__app_label='wagtailadmin', codename='access_admin'))
