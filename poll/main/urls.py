from django.urls import path

from . import views

app_name = 'polls'

urlpatterns = [
    path('<uuid:uuid>/answers.csv', views.question_answers_csv, name='question_answers_csv'),
    path('<uuid:uuid>/', views.question_detail, name='question_detail'),
    path('', views.question_detail, name='question_list'),
]
