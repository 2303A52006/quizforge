from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.forms import ProfileForm, RegisterForm, StyledPasswordChangeForm

User = get_user_model()


def register(request):
    """Student self-registration. Teachers are created by the admin."""
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome to QuizForge! Your account has been created.")
            return redirect("home")
    else:
        form = RegisterForm()
    return render(request, "registration/register.html", {"form": form})


@login_required
def profile(request):
    fresh_user = User.objects.get(pk=request.user.pk)
    profile_form = ProfileForm(instance=fresh_user)
    password_form = StyledPasswordChangeForm(request.user)

    if request.method == "POST":
        if "save_profile" in request.POST:
            profile_form = ProfileForm(request.POST, instance=fresh_user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Your profile has been updated.")
                return redirect("profile")
        elif "change_password" in request.POST:
            password_form = StyledPasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  # keep the user logged in
                messages.success(request, "Your password has been changed.")
                return redirect("profile")

    return render(
        request,
        "accounts/profile.html",
        {"profile_form": profile_form, "password_form": password_form},
    )
