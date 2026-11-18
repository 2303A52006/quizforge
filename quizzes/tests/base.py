"""Shared helpers for the QuizForge tests."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone

from accounts.permissions import TEACHER_GROUP
from quizzes import services
from quizzes.models import Attempt, Option, Question, Quiz

User = get_user_model()
PASSWORD = "Str0ng!Pass#2024"


def make_teacher(username="teacher"):
    user = User.objects.create_user(username=username, password=PASSWORD)
    group, _ = Group.objects.get_or_create(name=TEACHER_GROUP)
    user.groups.add(group)
    return user


def make_student(username="student"):
    return User.objects.create_user(
        username=username, password=PASSWORD, first_name=username.title(), email=f"{username}@example.com"
    )


def make_quiz(teacher, questions=4, published=True, **overrides):
    """A published quiz that is open now. Option 1 of every question is the correct one."""
    now = timezone.now()
    fields = {
        "teacher": teacher,
        "title": "Test quiz",
        "time_limit_minutes": 30,
        "pass_mark": 50,
        "max_attempts": 1,
        "is_published": published,
        "opens_at": now - timedelta(hours=1),
        "closes_at": now + timedelta(days=1),
    }
    fields.update(overrides)
    quiz = Quiz.objects.create(**fields)
    for i in range(1, questions + 1):
        question = Question.objects.create(
            quiz=quiz,
            text=f"Question {i}",
            topic="Topic A" if i % 2 else "Topic B",
            explanation=f"Explanation {i}",
            position=i,
        )
        for position in range(1, 5):
            Option.objects.create(
                question=question,
                text=f"Q{i} option {position}",
                is_correct=(position == 1),
                position=position,
            )
    return quiz


def correct_option(question):
    return question.options.get(is_correct=True)


def wrong_option(question):
    return question.options.filter(is_correct=False).first()


def quick_attempt(quiz, student, correct=0, wrong=0, seconds=60, started_at=None):
    """Create a finished attempt directly (answers the first `correct` questions right, then `wrong` wrong)."""
    started_at = started_at or timezone.now() - timedelta(minutes=10)
    number = Attempt.objects.filter(quiz=quiz, student=student).count() + 1
    attempt = services.build_attempt(quiz, student, started_at, number)
    questions = list(quiz.questions.all())
    for question in questions[:correct]:
        services._save_answer(attempt, question.pk, correct_option(question).pk)
    for question in questions[correct : correct + wrong]:
        services._save_answer(attempt, question.pk, wrong_option(question).pk)
    services.finalize_attempt(attempt, submitted_at=started_at + timedelta(seconds=seconds))
    attempt.refresh_from_db()
    return attempt


class QuizTestCase(TestCase):
    def setUp(self):
        self.teacher = make_teacher("teacher")
        self.student = make_student("student")

    def expire(self, attempt, seconds_past=30):
        """Push an attempt's deadline into the past."""
        Attempt.objects.filter(pk=attempt.pk).update(
            deadline=timezone.now() - timedelta(seconds=seconds_past)
        )
        attempt.refresh_from_db()
        return attempt
