"""
URL configuration for django_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, re_path, include
from api.views.diagnostics import HealthCheckView, DeepDiagnosticsView

urlpatterns = [
    path('admin/', admin.site.urls),
    re_path(r'^api/health/?$', HealthCheckView.as_view(), name='api-health'),
    re_path(r'^api/health/diagnostics/?$', DeepDiagnosticsView.as_view(), name='api-deep-diagnostics'),
    re_path(r'^health/?$', HealthCheckView.as_view(), name='root-health'),
    re_path(r'^health/diagnostics/?$', DeepDiagnosticsView.as_view(), name='root-deep-diagnostics'),
    path('api/', include('api.urls')),
]

