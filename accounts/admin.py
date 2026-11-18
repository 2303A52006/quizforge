from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

User = get_user_model()

admin.site.unregister(User)


@admin.register(User)
class QuizForgeUserAdmin(UserAdmin):
    """Default user admin. To create a teacher: add the user, then put them in the 'Teacher' group."""

    list_display = ("username", "first_name", "last_name", "email", "is_superuser", "is_teacher")
    list_filter = ("groups", "is_superuser", "is_active")

    @admin.display(boolean=True, description="Teacher")
    def is_teacher(self, obj):
        return obj.groups.filter(name="Teacher").exists()
