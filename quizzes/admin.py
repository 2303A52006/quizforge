from django.contrib import admin

from quizzes.models import Answer, Attempt, Option, Question, Quiz


class OptionInline(admin.TabularInline):
    model = Option
    extra = 0


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "teacher", "is_published", "opens_at", "closes_at", "max_attempts")
    list_filter = ("is_published", "teacher")
    search_fields = ("title",)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "quiz", "topic")
    list_filter = ("topic", "quiz")
    inlines = [OptionInline]


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    readonly_fields = ("question", "selected_option")
    can_delete = False


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("student", "quiz", "attempt_number", "score", "percentage", "passed", "submitted_at")
    list_filter = ("quiz", "passed")
    inlines = [AnswerInline]
