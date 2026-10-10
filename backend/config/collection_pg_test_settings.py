"""Loopback-only synthetic test database. Never imports production DB settings.

The test runner creates/drops only test_collection_resource_test on a dedicated
local PostgreSQL instance (port 55439). No PostGIS is needed for these models;
historical PostGIS/search-index migrations are outside this test scope.
"""
from os import environ
from pathlib import Path
from .test_settings import *  # noqa: F403

socket_directory = environ.get("COLLECTION_TEST_SOCKET_DIR", "")
if socket_directory:
    socket_path = Path(socket_directory).resolve(strict=True)
    if not socket_path.is_dir() or not socket_path.is_relative_to(BASE_DIR.parent.parent.resolve()):
        raise ValueError("Collection test socket must be a directory inside the task workspace")

DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql",
                         "HOST": socket_directory or "127.0.0.1", "PORT": "55439",
                         "NAME": "collection_resource_test", "USER": "collection_test",
                         "OPTIONS": {"connect_timeout": 5}}}
MIGRATION_MODULES = {name: None for name in ("recommendations", "auth", "admin", "contenttypes", "sessions")}
