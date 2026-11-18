import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from accounts.permissions import is_student, is_teacher, teacher_required
from quizzes import services
from quizzes.forms import QuestionForm, QuizForm
from quizzes.models import Attempt, Question, Quiz


def _own_quiz(request, pk):
    """A teacher can only reach their own quizzes (others give 404)."""
    return get_object_or_404(Quiz, pk=pk, teacher=request.user)


def _locked_response(request, quiz):
    """Questions cannot change once students have attempted the quiz (it would corrupt marking)."""
    if quiz.attempts.exists():
        messages.error(
            request,
            "Students have already attempted this quiz, so its questions are locked. "
            "Use 'Duplicate' to make an editable copy.",
        )
        return redirect("quizzes:manage", pk=quiz.pk)
    return None


@teacher_required
def teacher_list(request):
    quizzes = Quiz.objects.filter(teacher=request.user).annotate(
        num_questions=Count("questions", distinct=True),
        num_submitted=Count("attempts", filter=Q(attempts__submitted_at__isnull=False), distinct=True),
    )
    return render(request, "quizzes/teacher_list.html", {"quizzes": quizzes})


@teacher_required
def quiz_create(request):
    if request.method == "POST":
        form = QuizForm(request.POST)
        if form.is_valid():
            quiz = form.save(commit=False)
            quiz.teacher = request.user
            quiz.save()
            messages.success(request, "Quiz created as a draft. Now add questions.")
            return redirect("quizzes:manage", pk=quiz.pk)
    else:
        form = QuizForm()
    return render(request, "quizzes/quiz_form.html", {"form": form, "quiz": None})


@teacher_required
def quiz_edit(request, pk):
    quiz = _own_quiz(request, pk)
    if request.method == "POST":
        form = QuizForm(request.POST, instance=quiz)
        if form.is_valid():
            form.save()
            messages.success(request, "Quiz settings saved.")
            return redirect("quizzes:manage", pk=quiz.pk)
    else:
        form = QuizForm(instance=quiz)
    return render(request, "quizzes/quiz_form.html", {"form": form, "quiz": quiz})


@teacher_required
def quiz_manage(request, pk):
    quiz = _own_quiz(request, pk)
    questions = quiz.questions.prefetch_related("options")
    return render(
        request,
        "quizzes/manage.html",
        {
            "quiz": quiz,
            "questions": questions,
            "locked": quiz.attempts.exists(),
            "submitted_count": quiz.attempts.filter(submitted_at__isnull=False).count(),
        },
    )


@teacher_required
@require_POST
def quiz_publish(request, pk):
    """Toggle between draft and published."""
    quiz = _own_quiz(request, pk)
    if quiz.is_published:
        if quiz.attempts.exists():
            messages.error(request, "Students have already attempted this quiz, so it cannot go back to draft.")
        else:
            quiz.is_published = False
            quiz.save(update_fields=["is_published"])
            messages.success(request, "Quiz moved back to draft.")
    else:
        problems = services.publish_problems(quiz)
        if problems:
            for problem in problems:
                messages.error(request, problem)
        else:
            quiz.is_published = True
            quiz.save(update_fields=["is_published"])
            messages.success(request, "Quiz published. Students can see it now.")
    return redirect("quizzes:manage", pk=quiz.pk)


@teacher_required
@require_POST
def quiz_duplicate(request, pk):
    quiz = _own_quiz(request, pk)
    clone = services.duplicate_quiz(quiz)
    messages.success(request, f'Created "{clone.title}" as a draft. Set its dates, then publish.')
    return redirect("quizzes:manage", pk=clone.pk)


@teacher_required
def question_add(request, pk):
    quiz = _own_quiz(request, pk)
    locked = _locked_response(request, quiz)
    if locked:
        return locked
    if request.method == "POST":
        form = QuestionForm(request.POST)
        if form.is_valid():
            form.save(quiz)
            messages.success(request, "Question added.")
            if "save_and_add" in request.POST:
                return redirect("quizzes:question_add", pk=quiz.pk)
            return redirect("quizzes:manage", pk=quiz.pk)
    else:
        form = QuestionForm()
    return render(request, "quizzes/question_form.html", {"form": form, "quiz": quiz, "question": None})


@teacher_required
def question_edit(request, pk, question_id):
    quiz = _own_quiz(request, pk)
    question = get_object_or_404(Question, pk=question_id, quiz=quiz)
    locked = _locked_response(request, quiz)
    if locked:
        return locked
    if request.method == "POST":
        form = QuestionForm(request.POST, question=question)
        if form.is_valid():
            form.save(quiz)
            messages.success(request, "Question updated.")
            return redirect("quizzes:manage", pk=quiz.pk)
    else:
        form = QuestionForm(question=question)
    return render(
        request, "quizzes/question_form.html", {"form": form, "quiz": quiz, "question": question}
    )


@teacher_required
@require_POST
def question_delete(request, pk, question_id):
    quiz = _own_quiz(request, pk)
    question = get_object_or_404(Question, pk=question_id, quiz=quiz)
    locked = _locked_response(request, quiz)
    if locked:
        return locked
    question.delete()
    messages.success(request, "Question deleted.")
    return redirect("quizzes:manage", pk=quiz.pk)


@teacher_required
def quiz_analytics(request, pk):
    quiz = _own_quiz(request, pk)
    stats = services.quiz_analytics(quiz)
    chart_data = {}
    if stats["has_data"]:
        chart_data = {
            "distributionLabels": stats["distribution_labels"],
            "distributionCounts": stats["distribution_counts"],
            "questionLabels": [f"Q{q['number']}" for q in stats["per_question"]],
            "questionValues": [q["percent_correct"] for q in stats["per_question"]],
            "topicLabels": [t["topic"] for t in stats["topics"]],
            "topicValues": [t["percent_correct"] for t in stats["topics"]],
        }
    return render(
        request,
        "quizzes/analytics.html",
        {"quiz": quiz, "stats": stats, "chart_data": chart_data},
    )


def _safe_cell(value):
    """Stop spreadsheet formula injection: prefix risky text cells with an apostrophe."""
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


@teacher_required
def export_csv(request, pk):
    quiz = _own_quiz(request, pk)
    services.finalize_expired(quiz=quiz)
    attempts = (
        Attempt.objects.filter(quiz=quiz, submitted_at__isnull=False)
        .select_related("student")
        .order_by("student__username", "attempt_number")
    )
    response = HttpResponse(content_type="text/csv")
    filename = slugify(quiz.title) or "quiz"
    response["Content-Disposition"] = f'attachment; filename="{filename}-results.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "Username",
            "Student name",
            "Email",
            "Attempt number",
            "Started at",
            "Submitted at",
            "Time taken (seconds)",
            "Correct",
            "Wrong",
            "Unanswered",
            "Score",
            "Total marks",
            "Percentage",
            "Result",
        ]
    )
    for attempt in attempts:
        student = attempt.student
        writer.writerow(
            [
                _safe_cell(student.username),
                _safe_cell(student.get_full_name()),
                _safe_cell(student.email),
                attempt.attempt_number,
                timezone.localtime(attempt.started_at).strftime("%Y-%m-%d %H:%M:%S"),
                timezone.localtime(attempt.submitted_at).strftime("%Y-%m-%d %H:%M:%S"),
                attempt.duration_seconds,
                attempt.correct_count,
                attempt.wrong_count,
                attempt.unanswered_count,
                attempt.score,
                attempt.total_questions,
                attempt.percentage,
                "Pass" if attempt.passed else "Fail",
            ]
        )
    return response


@login_required
def leaderboard(request, pk):
    """Teacher (owner) or a student who has finished at least one attempt."""
    quiz = get_object_or_404(Quiz, pk=pk)
    if is_teacher(request.user):
        if quiz.teacher_id != request.user.pk:
            raise Http404
    elif is_student(request.user):
        has_finished = quiz.attempts.filter(
            student=request.user, submitted_at__isnull=False
        ).exists()
        if not quiz.is_published or not has_finished:
            raise PermissionDenied
    else:
        raise PermissionDenied
    services.finalize_expired(quiz=quiz)
    rows = services.best_attempts(quiz)
    return render(
        request,
        "quizzes/leaderboard.html",
        {"quiz": quiz, "rows": rows, "total_marks": quiz.questions.count()},
    )
