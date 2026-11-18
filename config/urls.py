from django.contrib import admin
from django.urls import include, path

from quizzes import views_student

urlpatterns = [
    path("", views_student.home, name="home"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", include("quizzes.urls")),
]
