from accounts.permissions import is_student, is_teacher


def roles(request):
    user = request.user
    return {
        "user_is_teacher": is_teacher(user),
        "user_is_student": is_student(user),
    }
