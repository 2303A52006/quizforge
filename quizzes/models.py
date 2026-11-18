from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Quiz(models.Model):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quizzes"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    time_limit_minutes = models.PositiveSmallIntegerField(
        default=30, validators=[MinValueValidator(1), MaxValueValidator(600)]
    )
    pass_mark = models.PositiveSmallIntegerField(
        default=40,
        validators=[MaxValueValidator(100)],
        help_text="Pass mark as a percentage of the total marks (0-100).",
    )
    max_attempts = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="How many times each student may attempt this quiz.",
    )
    negative_marking = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1"))],
        help_text="Marks deducted for each wrong answer (for example 0.25). Unanswered questions are not penalised.",
    )
    shuffle_questions = models.BooleanField(default=False)
    shuffle_options = models.BooleanField(default=False)
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "quizzes"

    def __str__(self):
        return self.title

    def get_status(self, now=None):
        """One of: draft, upcoming, open, closed."""
        if not self.is_published or self.opens_at is None or self.closes_at is None:
            return "draft"
        now = now or timezone.now()
        if now < self.opens_at:
            return "upcoming"
        if now >= self.closes_at:
            return "closed"
        return "open"

    @property
    def status(self):
        return self.get_status()

    @property
    def has_attempts(self):
        return self.attempts.exists()


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    topic = models.CharField(max_length=100)
    explanation = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.text[:60]


class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["question"],
                condition=models.Q(is_correct=True),
                name="one_correct_option_per_question",
            )
        ]

    def __str__(self):
        return self.text[:60]


class Attempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attempts"
    )
    attempt_number = models.PositiveSmallIntegerField()
    started_at = models.DateTimeField()
    deadline = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)

    # Order generated ONCE when the attempt starts, so a refresh never changes it.
    question_order = models.JSONField(default=list)  # [question_id, ...]
    option_order = models.JSONField(default=dict)  # {"<question_id>": [option_id, ...]}

    # Filled in when the attempt is marked.
    score = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    total_questions = models.PositiveSmallIntegerField(default=0)
    correct_count = models.PositiveSmallIntegerField(default=0)
    wrong_count = models.PositiveSmallIntegerField(default=0)
    unanswered_count = models.PositiveSmallIntegerField(default=0)
    passed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-started_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["quiz", "student", "attempt_number"], name="unique_attempt_number"
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.quiz} - attempt {self.attempt_number}"

    @property
    def is_submitted(self):
        return self.submitted_at is not None

    @property
    def duration_seconds(self):
        if not self.submitted_at:
            return None
        return max(0, int((self.submitted_at - self.started_at).total_seconds()))

    @property
    def duration_display(self):
        seconds = self.duration_seconds
        if seconds is None:
            return "-"
        minutes, secs = divmod(seconds, 60)
        return f"{minutes}m {secs:02d}s"


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    selected_option = models.ForeignKey(
        Option, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    saved_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["attempt", "question"], name="one_answer_per_question")
        ]

    def __str__(self):
        return f"Answer(attempt={self.attempt_id}, question={self.question_id})"
