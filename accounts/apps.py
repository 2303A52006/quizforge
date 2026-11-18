from django.apps import AppConfig
from django.db.models.signals import post_migrate


def create_teacher_group(sender, **kwargs):
    """Make sure the 'Teacher' group exists after every migrate.

    Admins turn a user into a teacher by adding them to this group in /admin/.
    """
    from django.contrib.auth.models import Group

    from accounts.permissions import TEACHER_GROUP

    Group.objects.get_or_create(name=TEACHER_GROUP)


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        post_migrate.connect(create_teacher_group, dispatch_uid="quizforge_create_teacher_group")
