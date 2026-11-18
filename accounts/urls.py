from django.contrib.auth import views as auth_views
from django.urls import path

from accounts import views
from accounts.forms import StyledAuthenticationForm

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(
            authentication_form=StyledAuthenticationForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    path("profile/", views.profile, name="profile"),
]
