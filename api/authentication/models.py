# Task 1 placeholder — Task 4 replaces this with the real User model.
#
# AUTH_USER_MODEL = "authentication.User" must resolve to an actual model class as
# soon as Django's app registry populates: django-unfold's app config eagerly
# instantiates its admin site during `ready()`, which imports
# django.contrib.admin.forms -> django.contrib.auth.forms, and that module calls
# get_user_model() at import time. Without a real class here, django.setup() itself
# raises ImproperlyConfigured before any test can even run.
#
# This intentionally subclasses AbstractBaseUser (not AbstractUser) so it carries no
# relations to auth.Group / auth.Permission. This app also intentionally has no
# migrations/ package (see Step 7 deviation), so pytest-django's test database
# creation treats it as unmigrated and syncs its table directly — an AbstractUser
# subclass here would need auth_group to already exist when that sync runs, which it
# doesn't yet since sync-created tables are built before migrated apps' tables.
#
# Task 4 should replace this file's contents outright with the real model.
from django.contrib.auth.models import AbstractBaseUser


class User(AbstractBaseUser):
    pass
