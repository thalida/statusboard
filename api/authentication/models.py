# Task 1 placeholder. Task 5 replaces it with the real User model.
#
# AUTH_USER_MODEL must resolve to a real class before django.setup() runs.
# unfold and django.contrib.admin both import django.contrib.auth.forms.
# That module calls get_user_model() at import time.
#
# AbstractBaseUser, not AbstractUser: it carries no auth.Group relations.
# This app has no migrations package, so pytest-django syncs its table
# directly. auth_group does not exist yet at that point.
from django.contrib.auth.models import AbstractBaseUser


class User(AbstractBaseUser):
    pass
