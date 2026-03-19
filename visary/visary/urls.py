   
                                     

                                                                             
                                                           
         
              
                                               
                                                                   
                 
                                                       
                                                                       
                         
                                                                           
                                                                     
   
from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views
from django.views.generic.base import RedirectView

from system import views as system_views

urlpatterns = [
    path('favicon.ico', RedirectView.as_view(url='/static/favicon.png', permanent=False)),
    path('admin/', admin.site.urls),
    path('', system_views.home, name='home'),
    path('login/', system_views.login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('system/', include(('system.urls', 'system'), namespace='system')),
]
