from django.urls import path

from . import views

app_name = 'polls'

urlpatterns = [
    path('<uuid:uuid>/answers.csv', views.question_answers_csv, name='question_answers_csv'),
    path('create/', views.question_create, name='question_create'),
    path('<uuid:uuid>/review/', views.question_review, name='question_review'),
    path('<uuid:uuid>/', views.question_detail, name='question_detail'),
    path('', views.question_list, name='question_list'),
]
