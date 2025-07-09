from django.urls import path

from . import views

app_name = 'polls'

urlpatterns = [
    path('<uuid:uuid>/', views.question_detail, name='question_detail'),
]
