import pytest
from django.db import connection


@pytest.mark.django_db
def test_database_is_postgres():
    assert connection.vendor == "postgresql"


def test_settings_module_loads():
    from django.conf import settings

    assert settings.AUTH_USER_MODEL == "authentication.User"
