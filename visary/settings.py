from pathlib import Path

from decouple import Config, RepositoryEnv

BASE_DIR = Path(__file__).resolve().parent.parent

config = Config(RepositoryEnv(str(BASE_DIR / ".env")))

SECRET_KEY = config(
    "DJANGO_SECRET_KEY",
    default="django-insecure-dev-only-change-me",
)

DEBUG = config("DJANGO_DEBUG", default=True, cast=bool)

ALLOWED_HOSTS = [
    host.strip()
    for host in config(
        "DJANGO_ALLOWED_HOSTS",
        default="127.0.0.1,localhost,localhost.,0.0.0.0",
    ).split(",")
    if host.strip()
]
if DEBUG and "*" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("*")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in config(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        default=(
            "http://127.0.0.1,http://localhost,https://127.0.0.1,https://localhost,"
            "https://*.ngrok-free.dev,https://*.ngrok.io"
        ),
    ).split(",")
    if origin.strip()
]

ADMIN_SUPERUSER_USERNAME = config("ADMIN_SUPERUSER_USERNAME", default="")
ADMIN_SUPERUSER_EMAIL = config("ADMIN_SUPERUSER_EMAIL", default="")
ADMIN_SUPERUSER_PASSWORD = config("ADMIN_SUPERUSER_PASSWORD", default="")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "system.apps.SystemConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "system.middleware.VisaryRequestMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "visary.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "libraries": {
                "dict_filters": "system.templatetags.dict_filters",
            },
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "visary.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "pt-br"

TIME_ZONE = "America/Sao_Paulo"

USE_I18N = True

USE_TZ = True

DATE_INPUT_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
]

DATE_FORMAT = "d/m/Y"
DATETIME_FORMAT = "d/m/Y H:i"

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

LOGIN_URL = "system:login"
LOGIN_REDIRECT_URL = "system:home"
LOGOUT_REDIRECT_URL = "system:login"

EMAIL_BACKEND = config(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = config(
    "DJANGO_DEFAULT_FROM_EMAIL",
    default="nao-responda@visary.local",
)


def _env_value_strip_outer_quotes(key: str, default: str = "") -> str:
    raw = config(key, default=default).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        return raw[1:-1].strip()
    return raw


SYSTEM_SEED_USERS_PASSWORDS = _env_value_strip_outer_quotes(
    "SYSTEM_SEED_USERS_PASSWORDS",
    default="",
)
SYSTEM_SEED_PARTNER_PASSWORDS = _env_value_strip_outer_quotes(
    "SYSTEM_SEED_PARTNER_PASSWORDS",
    default="",
)

LEGACY_DB_HOST = config("LEGACY_DB_HOST", default="").strip()
LEGACY_DB_PORT = config("LEGACY_DB_PORT", default="3306").strip()
LEGACY_DB_NAME = config("LEGACY_DB_NAME", default="").strip()
LEGACY_DB_USER = config("LEGACY_DB_USER", default="").strip()
LEGACY_DB_PASSWORD = config("LEGACY_DB_PASSWORD", default="").strip()

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
