from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import is_student, is_teacher, student_required
from quizzes import services
from quizzes.models import Attempt, Quiz


def home(request):
    """Landing page for visitors; teachers and students go straight to their quiz list."""
    if request.user.is_authenticated:
        if is_teacher(request.user):
            return redirect("quizzes:teacher_list")
        if is_student(request.user):
            return redirect("quizzes:student_list")
    return render(request, "home.html")


@student_required
def student_list(request):
    now = timezone.now()
    services.finalize_expired(student=request.user, now=now)
    quizzes = list(services.student_quiz_filter())
    summary = services.attempts_summary(request.user, quizzes)

    upcoming, open_now, closed = [], [], []
    for quiz in quizzes:
        status = quiz.get_status(now)
        entry = {"quiz": quiz, "status": status, **summary[quiz.pk]}
        if status == "upcoming":
            upcoming.append(entry)
        elif status == "open":
            open_now.append(entry)
        else:
            closed.append(entry)
    upcoming.sort(key=lambda e: e["quiz"].opens_at)
    open_now.sort(key=lambda e: e["quiz"].closes_at)
    closed.sort(key=lambda e: e["quiz"].closes_at, reverse=True)
    return render(
        request,
        "quizzes/student_list.html",
        {"upcoming": upcoming, "open_now": open_now, "closed": closed},
    )


@student_required
def quiz_detail(request, pk):
    quiz = get_object_or_404(services.student_quiz_filter(), pk=pk)
    now = timezone.now()
    services.finalize_expired(student=request.user, quiz=quiz, now=now)
    attempts = list(
        Attempt.objects.filter(quiz=quiz, student=request.user).order_by("attempt_number")
    )
    in_progress = services.get_in_progress(quiz, request.user, now)

    can_start, reason = True, ""
    if in_progress is None:
        try:
            services.check_can_start(quiz, request.user, now)
        except services.StartError as error:
            can_start, reason = False, str(error)

    return render(
        request,
        "quizzes/detail.html",
        {
            "quiz": quiz,
            "status": quiz.get_status(now),
            "attempts": attempts,
            "submitted_attempts": [a for a in attempts if a.is_submitted],
            "attempts_used": len(attempts),
            "in_progress": in_progress,
            "can_start": can_start,
            "reason": reason,
        },
    )


@student_required
@require_POST
def start_quiz(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk, is_published=True)
    try:
        attempt, _created = services.start_attempt(quiz, request.user)
    except services.StartError as error:
        messages.error(request, str(error))
        return redirect("quizzes:detail", pk=quiz.pk)
    return redirect("quizzes:take", attempt_id=attempt.pk)


def _own_attempt(request, attempt_id):
    return get_object_or_404(
        Attempt.objects.select_related("quiz"), pk=attempt_id, student=request.user
    )


@student_required
def take_quiz(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    now = timezone.now()
    if attempt.is_submitted:
        return redirect("quizzes:result", attempt_id=attempt.pk)
    if now > attempt.deadline:
        services.finalize_attempt(attempt)
        messages.warning(request, "Time was up, so your attempt was submitted automatically.")
        return redirect("quizzes:result", attempt_id=attempt.pk)

    saved = {a.question_id: a.selected_option_id for a in attempt.answers.all()}
    items = []
    for question in services.questions_for_attempt(attempt):
        question["selected"] = saved.get(question["id"])
        items.append(question)

    return render(
        request,
        "quizzes/take.html",
        {
            "attempt": attempt,
            "quiz": attempt.quiz,
            "items": items,
            "remaining_seconds": services.seconds_remaining(attempt, now),
            "answered": sum(1 for item in items if item["selected"]),
        },
    )


@student_required
@require_POST
def save_answer(request, attempt_id):
    """Autosave one answer (called by JavaScript when an option is picked)."""
    attempt = _own_attempt(request, attempt_id)
    try:
        question_id = int(request.POST.get("question", ""))
        raw_option = request.POST.get("option", "")
        option_id = int(raw_option) if raw_option else None
    except ValueError:
        return JsonResponse({"ok": False, "error": "Bad request."}, status=400)
    try:
        services.record_answer(attempt, question_id, option_id)
    except services.AnswerError as error:
        status = 409 if attempt.is_submitted else 403
        return JsonResponse({"ok": False, "error": str(error)}, status=status)
    return JsonResponse({"ok": True, "answered": attempt.answers.count()})


@student_required
@require_POST
def submit_quiz(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    services.submit_attempt(attempt, request.POST)
    messages.success(request, "Your attempt has been submitted.")
    return redirect("quizzes:result", attempt_id=attempt.pk)


@student_required
def result(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    if not attempt.is_submitted:
        if timezone.now() > attempt.deadline:
            services.finalize_attempt(attempt)
        else:
            return redirect("quizzes:take", attempt_id=attempt.pk)

    quiz = attempt.quiz
    history = list(
        Attempt.objects.filter(quiz=quiz, student=request.user, submitted_at__isnull=False).order_by(
            "attempt_number"
        )
    )
    best = max(history, key=lambda a: (a.score, -a.duration_seconds), default=None)
    attempts_used = Attempt.objects.filter(quiz=quiz, student=request.user).count()
    can_retry = True
    try:
        services.check_can_start(quiz, request.user)
    except services.StartError:
        can_retry = False

    return render(
        request,
        "quizzes/result.html",
        {
            "attempt": attempt,
            "quiz": quiz,
            "review": services.build_review(attempt),
            "history": history,
            "best": best,
            "attempts_used": attempts_used,
            "can_retry": can_retry,
        },
    )
