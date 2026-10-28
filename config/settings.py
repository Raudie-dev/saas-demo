import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Cargar variables de entorno desde el archivo .env
load_dotenv(BASE_DIR / '.env')

ENVIRONMENT = 'develop'


SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if ENVIRONMENT == 'production':
        raise ValueError("CRITICAL: SECRET_KEY must be set in environment variables for production!")
    SECRET_KEY = 'django-insecure-dev-key-change-me'

DEBUG = True

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party apps
    'rest_framework',

    # BusinessOS Custom Apps
    'apps.core',
    'apps.business',
    'apps.crm',
    'apps.agenda',
    'apps.booking',
    'apps.pos',
    'apps.invoicing',
    'apps.inventory',
    'apps.commissions',
    'apps.analytics',
    'apps.ai_engine',
    'apps.marketing',
    'apps.properties',
    'apps.projects',
    'apps.travel',
    'apps.superadmin',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.business.middleware.BusinessMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.business.context_processors.business_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# (ENVIRONMENT)
if ENVIRONMENT == 'production' and os.getenv('DB_NAME'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME'),
            'USER': os.getenv('DB_USER'),
            'PASSWORD': os.getenv('DB_PASSWORD'),
            'HOST': os.getenv('DB_HOST', '127.0.0.1'),
            'PORT': os.getenv('DB_PORT', '3306'),
            'OPTIONS': {
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                'charset': 'utf8mb4',
            },
            'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', 600)),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'raudie_os.sqlite3',
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTH_USER_MODEL = 'business.User'

LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise Static Files Serving
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# CSRF Trusted Origins
csrf_trusted_env = os.getenv('CSRF_TRUSTED_ORIGINS', '')
default_trusted_origins = [
    'https://os.raudie.net',
    'http://os.raudie.net',
    'https://demos.raudie.net',
    'http://demos.raudie.net',
    'https://*.raudie.net',
    'http://*.raudie.net',
    'http://127.0.0.1:8000',
    'http://localhost:8000',
    'http://127.0.0.1',
    'http://localhost',
    'http://0.0.0.0:5555',
]
if csrf_trusted_env:
    CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(
        default_trusted_origins + [origin.strip() for origin in csrf_trusted_env.split(',') if origin.strip()]
    ))
else:
    CSRF_TRUSTED_ORIGINS = default_trusted_origins

# Allow embedding in same origin for portal preview iframes
X_FRAME_OPTIONS = 'SAMEORIGIN'

# Recognize HTTPS behind reverse proxies (Nginx, Traefik, Cloudflare, etc.)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Security Hardening for Production (HTTPS / Cookie security)
IS_RUNSERVER = any('runserver' in arg for arg in sys.argv)

if ENVIRONMENT == 'production' and not DEBUG and not IS_RUNSERVER:
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'False').lower() in ('true', '1', 't')
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'True').lower() in ('true', '1', 't')
    CSRF_COOKIE_SECURE = os.getenv('CSRF_COOKIE_SECURE', 'True').lower() in ('true', '1', 't')
    if SECURE_SSL_REDIRECT:
        SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', 31536000))  # 1 year
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True
    else:
        SECURE_HSTS_SECONDS = 0
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0

# Session Configuration (Sesión persistente sin límite de tiempo)
# 315360000 segundos = 10 años (sesión permanente, no expira por inactividad ni al cerrar el navegador)
SESSION_COOKIE_AGE = int(os.getenv('SESSION_COOKIE_AGE', 315360000))
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Authentication URLs
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

# Dominio Principal y WhatsApp Gateway Microservice URL según entorno
if ENVIRONMENT == 'production':
    SITE_URL = os.getenv('SITE_URL', 'https://os.raudie.net').rstrip('/')
    WHATSAPP_GATEWAY_URL = os.getenv('WHATSAPP_GATEWAY_URL', 'https://os.raudie.net/whatsapp').rstrip('/')
else:
    SITE_URL = os.getenv('SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
    WHATSAPP_GATEWAY_URL = os.getenv('WHATSAPP_GATEWAY_URL', 'http://127.0.0.1:3000').rstrip('/')

# Email Configuration (for password recovery and notifications)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 't')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)

# Password Reset Timeout (Tiempo de vida del enlace de recuperación: 30 minutos = 1800 segundos)
PASSWORD_RESET_TIMEOUT = 1800



