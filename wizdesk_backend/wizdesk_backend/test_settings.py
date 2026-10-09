"""Isolated defaults for tests; TEST_DATABASE_URL enables PostgreSQL CI."""
import os

os.environ['SECRET_KEY'] = 'isolated-tests-only-key-do-not-use-in-production-123456789'
os.environ['SIMPLE_JWT_SIGNING_KEY'] = os.environ['SECRET_KEY']
os.environ['DATABASE_URL'] = os.getenv('TEST_DATABASE_URL', 'sqlite:///:memory:')
os.environ['CACHE_URL'] = ''
os.environ['JWT_ROTATE_REFRESH_TOKENS'] = 'True'
os.environ['JWT_BLACKLIST_AFTER_ROTATION'] = 'True'
from .settings import *  # noqa: E402,F403

DEBUG = False
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
SECURE_SSL_REDIRECT = False
EMAIL_VERIFICATION_REQUIRED = False
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
FRONTEND_URL = 'http://testserver'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
STORAGES['staticfiles'] = {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}
