from django.contrib import admin
from django.urls import path, include

from .api import api


urlpatterns = [
    path('admin/', admin.site.urls),
    path('polls/', include('poll.main.urls')),
    path('api/', api.urls),
    path('accounts/', include('django.contrib.auth.urls')),
]
