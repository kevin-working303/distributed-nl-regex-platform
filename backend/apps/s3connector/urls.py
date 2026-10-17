from django.urls import path

from . import views

urlpatterns = [
    path("connect/", views.connect, name="s3-connect"),
    path("files/", views.files, name="s3-files"),
    path("columns/", views.columns, name="s3-columns"),
]
