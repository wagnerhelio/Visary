   
                                   

                                                            

                                      
                                                      

                                                   
                                                   
   

import os
from pathlib import Path
from dotenv import load_dotenv
import sys

                                                                
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv()

                                                              
                                                                       

                                                                  
SECRET_KEY = 'django-insecure-jx!fl%jqva_85q_ids*a1y-qaelr-@11-pts1d0n@tw+b3^r%2'

                                                                 
DEBUG = True

ALLOWED_HOSTS = ['*']

                                                                        
CSRF_TRUSTED_ORIGINS = [
    'https://statistically-flocky-torie.ngrok-free.dev',
                                                           
                                                                  
]


                        

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'system.apps.SystemConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'visary.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'visary.wsgi.application'


          
                                                               

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


                     
                                                                              

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


                      
                                                    

LANGUAGE_CODE = 'pt-br'

TIME_ZONE = 'America/Sao_Paulo'

USE_I18N = True

USE_TZ = True

                  
DATE_INPUT_FORMATS = [
    '%Y-%m-%d',                                      
    '%d/%m/%Y',                      
    '%d-%m-%Y',                       
    '%Y-%m-%d',              
]

DATE_FORMAT = 'd/m/Y'
DATETIME_FORMAT = 'd/m/Y H:i'


                                        
                                                           

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'

                                
                                                                        

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
