from django.urls import path
from .views import MCPInfoView, MCPHealthView

app_name = 'mcp'

urlpatterns = [
    path('', MCPInfoView.as_view(), name='info'),
    path('health/', MCPHealthView.as_view(), name='health'),
]
