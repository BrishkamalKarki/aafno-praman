"""
Authentication routes.

Two populations authenticate here by two different mechanisms, and the URL
structure makes that boundary visible:

Email and password for every role. Citizens, organisation staff and registrars
all authenticate the same way; what differs is what their role permits, which is
re-read from the database on every request rather than baked into a token.
"""

from django.urls import path

from .views import (
    ChangePasswordView,
    LoginView,
    MeView,
    RefreshView,
    RegisterView,
    SeekerProfileView,
)

app_name = "accounts"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("me/password/", ChangePasswordView.as_view(), name="change-password"),
    path("me/seeker-profile/", SeekerProfileView.as_view(), name="seeker-profile"),
]
