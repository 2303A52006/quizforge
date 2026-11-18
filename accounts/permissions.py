"""Role helpers and view decorators.

Teacher  = a user who belongs to the "Teacher" group (set by the admin).
Student  = any other logged-in user who is not a superuser (self-registered).
"""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

TEACHER_GROUP = "Teacher"


def is_teacher(user):
    return bool(
        user.is_authenticated
        and user.is_active
        and user.groups.filter(name=TEACHER_GROUP).exists()
    )


def is_student(user):
    return bool(user.is_authenticated and not user.is_superuser and not is_teacher(user))


def _require(check):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not check(request.user):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


teacher_required = _require(is_teacher)
student_required = _require(is_student)
