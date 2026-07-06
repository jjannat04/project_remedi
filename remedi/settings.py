"""
Django settings for remedi project.
"""

import os
import dj_database_url
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default=0):
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


# SECURITY
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "dev-only-remedi-secret-key-change-this-before-production-2026",
)
DEBUG = env_bool("DEBUG", False)
PRODUCTION_SECURITY = (
    env_bool("PRODUCTION", False)
    or env_bool("RENDER", False)
    or bool(os.environ.get("RENDER_EXTERNAL_HOSTNAME"))
)
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", PRODUCTION_SECURITY)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", PRODUCTION_SECURITY)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", PRODUCTION_SECURITY)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000 if PRODUCTION_SECURITY else 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", PRODUCTION_SECURITY)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", PRODUCTION_SECURITY)

DEMO_MODE = env_bool("DEMO_MODE", False)
AI_FALLBACK_ENABLED = env_bool("AI_FALLBACK_ENABLED", True)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODELS = [
    model.strip()
    for model in os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite").split(",")
    if model.strip()
]
OCR_SPACE_API_KEY = os.environ.get("OCR_SPACE_API_KEY", "")
OCR_SPACE_ENABLED = env_bool("OCR_SPACE_ENABLED", True)
USE_CLOUDINARY_STORAGE = env_bool("USE_CLOUDINARY_STORAGE", False)

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "project-remedi.onrender.com",
]

# APPS
INSTALLED_APPS = [
    *(['cloudinary_storage', 'cloudinary'] if USE_CLOUDINARY_STORAGE else []),

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'myapp',
]

# MIDDLEWARE
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'remedi.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'myapp.context_processors.demo_mode',
            ],
        },
    },
]

WSGI_APPLICATION = 'remedi.wsgi.application'


# DATABASE
if os.environ.get('DATABASE_URL'):
    DATABASES = {
        'default': dj_database_url.config(conn_max_age=600)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# AUTH
AUTH_USER_MODEL = 'myapp.User'
LOGIN_REDIRECT_URL = 'marketplace'
LOGIN_URL = 'login'
LOGOUT_REDIRECT_URL = 'marketplace'


# PASSWORD VALIDATION
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# INTERNATIONALIZATION
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# STATIC / MEDIA
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))

STATICFILES_STORAGE = "whitenoise.storage.StaticFilesStorage"
# Fixed WhiteNoise config.
# Avoid CompressedManifestStaticFilesStorage (causes missing file crash on Render)
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.StaticFilesStorage",
    },
}

# optional safety (prevents edge-case crashes)
WHITENOISE_KEEP_ONLY_HASHED_FILES = False
WHITENOISE_AUTOREFRESH = True
WHITENOISE_MANIFEST_STRICT = False

# CLOUDINARY
CLOUDINARY_STORAGE = {
    "CLOUD_NAME": os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
    "API_KEY": os.environ.get("CLOUDINARY_API_KEY", ""),
    "API_SECRET": os.environ.get("CLOUDINARY_API_SECRET", ""),
}

if USE_CLOUDINARY_STORAGE:
    STORAGES["default"] = {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    }

