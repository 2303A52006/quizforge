"""Business logic: starting attempts, deadlines, answers, marking, leaderboard, analytics.

Views stay thin and call these functions, which makes them easy to unit-test.
"""
import random
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone

from quizzes.models import Answer, Attempt, Option, Question, Quiz

# Network delay allowance when the final "Submit" request arrives just after the deadline.
GRACE_SECONDS = 5
# A topic below this percentage is flagged as weak in the analytics page.
WEAK_TOPIC_THRESHOLD = 50

TWO_PLACES = Decimal("0.01")


class StartError(Exception):
    """The student is not allowed to start (or resume) an attempt."""


class AnswerError(Exception):
    """An answer could not be saved."""


# ---------------------------------------------------------------- deadlines
def compute_deadline(quiz, started_at):
    """Start time + time limit, but never later than the quiz close date."""
    deadline = started_at + timedelta(minutes=quiz.time_limit_minutes)
    if quiz.closes_at is not None and quiz.closes_at < deadline:
        deadline = quiz.closes_at
    return deadline


def seconds_remaining(attempt, now=None):
    now = now or timezone.now()
    return max(0, int((attempt.deadline - now).total_seconds()))


# ---------------------------------------------------------------- starting
def build_attempt(quiz, student, started_at, attempt_number):
    """Create an attempt and store its (possibly shuffled) question/option order."""
    questions = list(quiz.questions.prefetch_related("options"))
    if quiz.shuffle_questions:
        random.shuffle(questions)

    question_order = [q.pk for q in questions]
    option_order = {}
    for question in questions:
        option_ids = [o.pk for o in question.options.all()]
        if quiz.shuffle_options:
            random.shuffle(option_ids)
        option_order[str(question.pk)] = option_ids

    return Attempt.objects.create(
        quiz=quiz,
        student=student,
        attempt_number=attempt_number,
        started_at=started_at,
        deadline=compute_deadline(quiz, started_at),
        question_order=question_order,
        option_order=option_order,
        total_questions=len(question_order),
    )


def finalize_expired(student=None, quiz=None, now=None):
    """Mark every unsubmitted attempt whose deadline has passed."""
    now = now or timezone.now()
    pending = Attempt.objects.filter(submitted_at__isnull=True, deadline__lt=now)
    if student is not None:
        pending = pending.filter(student=student)
    if quiz is not None:
        pending = pending.filter(quiz=quiz)
    for attempt in pending.select_related("quiz"):
        finalize_attempt(attempt, submitted_at=attempt.deadline)


def get_in_progress(quiz, student, now=None):
    now = now or timezone.now()
    return Attempt.objects.filter(
        quiz=quiz, student=student, submitted_at__isnull=True, deadline__gte=now
    ).first()


def check_can_start(quiz, student, now=None):
    """Raise StartError with a friendly message if the student cannot start a NEW attempt."""
    now = now or timezone.now()
    status = quiz.get_status(now)
    if status == "draft":
        raise StartError("This quiz is not available.")
    if status == "upcoming":
        raise StartError("This quiz has not opened yet.")
    if status == "closed":
        raise StartError("This quiz is closed.")
    if quiz.questions.count() == 0:
        raise StartError("This quiz has no questions yet.")
    used = Attempt.objects.filter(quiz=quiz, student=student).count()
    if used >= quiz.max_attempts:
        raise StartError(f"You have used all {quiz.max_attempts} attempt(s) for this quiz.")


def start_attempt(quiz, student, now=None):
    """Return (attempt, created). Resumes an unfinished attempt instead of starting a new one."""
    now = now or timezone.now()
    finalize_expired(student=student, quiz=quiz, now=now)

    existing = get_in_progress(quiz, student, now)
    if existing is not None:
        return existing, False

    check_can_start(quiz, student, now)
    number = Attempt.objects.filter(quiz=quiz, student=student).count() + 1
    try:
        with transaction.atomic():
            attempt = build_attempt(quiz, student, now, number)
    except IntegrityError:
        # Two requests raced; the other one won. Resume it.
        existing = get_in_progress(quiz, student, now)
        if existing is None:
            raise StartError("Could not start the attempt. Please try again.")
        return existing, False
    return attempt, True


# ---------------------------------------------------------------- answers
def _save_answer(attempt, question_id, option_id):
    """Validate and store one answer (option_id None clears it)."""
    if question_id not in attempt.question_order:
        raise AnswerError("That question is not part of this attempt.")
    if option_id is None:
        Answer.objects.filter(attempt=attempt, question_id=question_id).delete()
        return
    valid = Option.objects.filter(pk=option_id, question_id=question_id).exists()
    if not valid:
        raise AnswerError("That option does not belong to the question.")
    Answer.objects.update_or_create(
        attempt=attempt, question_id=question_id, defaults={"selected_option_id": option_id}
    )


def record_answer(attempt, question_id, option_id, now=None):
    """Autosave one answer. Refused once the attempt is submitted or past its deadline."""
    now = now or timezone.now()
    if attempt.is_submitted:
        raise AnswerError("This attempt has already been submitted.")
    if now > attempt.deadline:
        raise AnswerError("Time is up.")
    _save_answer(attempt, question_id, option_id)


def submit_attempt(attempt, posted=None, now=None):
    """Final submit. Posted answers (keys 'q_<id>') count only if inside deadline + grace."""
    now = now or timezone.now()
    if attempt.is_submitted:
        return attempt
    if posted and now <= attempt.deadline + timedelta(seconds=GRACE_SECONDS):
        for question_id in attempt.question_order:
            raw = posted.get(f"q_{question_id}")
            if raw and str(raw).isdigit():
                try:
                    _save_answer(attempt, question_id, int(raw))
                except AnswerError:
                    pass
    return finalize_attempt(attempt, submitted_at=min(now, attempt.deadline))


# ---------------------------------------------------------------- marking
def grade_attempt(attempt):
    """Compute score fields from the stored answers. Uses option IDs, never positions."""
    quiz = attempt.quiz
    question_ids = list(attempt.question_order)
    answers = {
        a.question_id: a
        for a in attempt.answers.select_related("selected_option")
        if a.question_id in question_ids
    }

    correct = wrong = 0
    for question_id in question_ids:
        answer = answers.get(question_id)
        if answer is None or answer.selected_option is None:
            continue
        if answer.selected_option.is_correct:
            correct += 1
        else:
            wrong += 1

    total = len(question_ids)
    penalty = Decimal(str(quiz.negative_marking))
    raw_score = Decimal(correct) - Decimal(wrong) * penalty
    score = max(Decimal("0"), raw_score)
    percentage = (score / total * 100) if total else Decimal("0")

    attempt.total_questions = total
    attempt.correct_count = correct
    attempt.wrong_count = wrong
    attempt.unanswered_count = total - correct - wrong
    attempt.score = score.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    attempt.percentage = percentage.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    attempt.passed = total > 0 and percentage >= Decimal(quiz.pass_mark)
    return attempt


def finalize_attempt(attempt, submitted_at=None):
    """Mark an attempt and lock it. Safe to call more than once."""
    if attempt.is_submitted:
        return attempt
    submitted_at = submitted_at or min(timezone.now(), attempt.deadline)
    grade_attempt(attempt)
    attempt.submitted_at = submitted_at
    attempt.save()
    return attempt


# ---------------------------------------------------------------- taking / reviewing
def questions_for_attempt(attempt):
    """Questions + options in the order stored for this attempt.

    Returns dicts with option id/text ONLY (no is_correct) so the quiz page can
    never leak correct answers.
    """
    questions = {
        q.pk: q
        for q in Question.objects.filter(pk__in=attempt.question_order).prefetch_related("options")
    }
    items = []
    for question_id in attempt.question_order:
        question = questions.get(question_id)
        if question is None:
            continue
        options_by_id = {o.pk: o for o in question.options.all()}
        order = attempt.option_order.get(str(question_id), [])
        ordered = [options_by_id[i] for i in order if i in options_by_id]
        # Safety net: append any option missing from the stored order.
        ordered += [o for i, o in options_by_id.items() if i not in order]
        items.append(
            {
                "id": question.pk,
                "text": question.text,
                "topic": question.topic,
                "options": [{"id": o.pk, "text": o.text} for o in ordered],
            }
        )
    return items


def build_review(attempt):
    """Full review (correct answers + explanations) for a SUBMITTED attempt."""
    questions = {
        q.pk: q
        for q in Question.objects.filter(pk__in=attempt.question_order).prefetch_related("options")
    }
    selected = {a.question_id: a.selected_option_id for a in attempt.answers.all()}
    review = []
    for number, question_id in enumerate(attempt.question_order, start=1):
        question = questions.get(question_id)
        if question is None:
            continue
        options_by_id = {o.pk: o for o in question.options.all()}
        order = attempt.option_order.get(str(question_id), [])
        ordered = [options_by_id[i] for i in order if i in options_by_id]
        ordered += [o for i, o in options_by_id.items() if i not in order]
        chosen_id = selected.get(question_id)
        chosen = options_by_id.get(chosen_id) if chosen_id else None
        if chosen is None:
            state = "unanswered"
        elif chosen.is_correct:
            state = "correct"
        else:
            state = "wrong"
        review.append(
            {
                "number": number,
                "question": question,
                "state": state,
                "options": [
                    {
                        "text": o.text,
                        "is_correct": o.is_correct,
                        "is_selected": o.pk == chosen_id,
                    }
                    for o in ordered
                ],
            }
        )
    return review


# ---------------------------------------------------------------- leaderboard / analytics
def best_attempts(quiz):
    """Each student's best submitted attempt, ranked.

    Best = highest score; ties broken by shortest time taken, then earliest attempt number.
    """
    attempts = Attempt.objects.filter(quiz=quiz, submitted_at__isnull=False).select_related(
        "student"
    )
    best = {}
    for attempt in attempts:
        key = (-attempt.score, attempt.duration_seconds, attempt.attempt_number)
        current = best.get(attempt.student_id)
        if current is None or key < current[0]:
            best[attempt.student_id] = (key, attempt)
    ranked = sorted(best.values(), key=lambda pair: (pair[0], pair[1].student_id))
    return [attempt for _, attempt in ranked]


def _percent(part, whole):
    return round(part * 100 / whole, 1) if whole else 0.0


def quiz_analytics(quiz):
    """Numbers for the teacher analytics page, based on each student's best attempt."""
    best = best_attempts(quiz)
    count = len(best)
    questions = list(quiz.questions.all())
    data = {"has_data": count > 0, "students": count}
    if count == 0:
        return data

    scores = [float(a.score) for a in best]
    percentages = [float(a.percentage) for a in best]
    data.update(
        {
            "total_marks": len(questions),
            "average_score": round(sum(scores) / count, 2),
            "average_percentage": round(sum(percentages) / count, 1),
            "highest_score": max(scores),
            "lowest_score": min(scores),
            "pass_rate": _percent(sum(1 for a in best if a.passed), count),
        }
    )

    # Score distribution in ten buckets of percentage: 0-9, 10-19, ... 90-100.
    buckets = [0] * 10
    for value in percentages:
        buckets[min(int(value // 10), 9)] += 1
    data["distribution_labels"] = [f"{i * 10}-{i * 10 + 9}" if i < 9 else "90-100" for i in range(10)]
    data["distribution_counts"] = buckets

    # Percentage correct per question (unanswered counts as not correct).
    correct_rows = (
        Answer.objects.filter(attempt__in=[a.pk for a in best], selected_option__is_correct=True)
        .values("question_id")
        .annotate(n=Count("id"))
    )
    correct_by_question = {row["question_id"]: row["n"] for row in correct_rows}

    per_question = []
    topic_totals = {}
    for number, question in enumerate(questions, start=1):
        correct = correct_by_question.get(question.pk, 0)
        per_question.append(
            {
                "number": number,
                "text": question.text,
                "topic": question.topic,
                "percent_correct": _percent(correct, count),
            }
        )
        totals = topic_totals.setdefault(question.topic, {"correct": 0, "possible": 0})
        totals["correct"] += correct
        totals["possible"] += count

    topics = [
        {
            "topic": topic,
            "percent_correct": _percent(t["correct"], t["possible"]),
            "weak": _percent(t["correct"], t["possible"]) < WEAK_TOPIC_THRESHOLD,
        }
        for topic, t in topic_totals.items()
    ]
    topics.sort(key=lambda t: t["percent_correct"])
    data["per_question"] = per_question
    data["topics"] = topics
    data["weak_topics"] = [t for t in topics if t["weak"]]
    return data


# ---------------------------------------------------------------- duplicate
@transaction.atomic
def duplicate_quiz(quiz):
    """Copy settings, questions and options into a new draft with the dates cleared."""
    title = f"Copy of {quiz.title}"[:200]
    clone = Quiz.objects.create(
        teacher=quiz.teacher,
        title=title,
        description=quiz.description,
        time_limit_minutes=quiz.time_limit_minutes,
        pass_mark=quiz.pass_mark,
        max_attempts=quiz.max_attempts,
        negative_marking=quiz.negative_marking,
        shuffle_questions=quiz.shuffle_questions,
        shuffle_options=quiz.shuffle_options,
        opens_at=None,
        closes_at=None,
        is_published=False,
    )
    for question in quiz.questions.prefetch_related("options"):
        new_question = Question.objects.create(
            quiz=clone,
            text=question.text,
            topic=question.topic,
            explanation=question.explanation,
            position=question.position,
        )
        for option in question.options.all():
            Option.objects.create(
                question=new_question,
                text=option.text,
                is_correct=option.is_correct,
                position=option.position,
            )
    return clone


# ---------------------------------------------------------------- publish rules
def publish_problems(quiz):
    """List of reasons why a quiz cannot be published yet (empty list = OK)."""
    problems = []
    if quiz.questions.count() == 0:
        problems.append("Add at least one question first.")
    if quiz.opens_at is None or quiz.closes_at is None:
        problems.append("Set both the open date and the close date (Edit quiz).")
    elif quiz.closes_at <= quiz.opens_at:
        problems.append("The close date must be after the open date.")
    elif quiz.closes_at <= timezone.now():
        problems.append("The close date is already in the past.")
    return problems


def student_quiz_filter():
    """Quizzes a student is allowed to see."""
    return Quiz.objects.filter(
        is_published=True, opens_at__isnull=False, closes_at__isnull=False
    ).annotate(num_questions=Count("questions", distinct=True))


def attempts_summary(student, quizzes):
    """{quiz_id: {'used': n, 'best': Attempt|None, 'in_progress': Attempt|None}}"""
    summary = {q.pk: {"used": 0, "best": None, "in_progress": None} for q in quizzes}
    now = timezone.now()
    attempts = Attempt.objects.filter(student=student, quiz__in=[q.pk for q in quizzes])
    for attempt in attempts:
        entry = summary[attempt.quiz_id]
        entry["used"] += 1
        if attempt.is_submitted:
            best = entry["best"]
            if best is None or attempt.score > best.score:
                entry["best"] = attempt
        elif attempt.deadline >= now:
            entry["in_progress"] = attempt
    return summary


__all__ = [
    "GRACE_SECONDS",
    "StartError",
    "AnswerError",
    "compute_deadline",
    "build_attempt",
    "start_attempt",
    "check_can_start",
    "record_answer",
    "submit_attempt",
    "grade_attempt",
    "finalize_attempt",
    "finalize_expired",
    "questions_for_attempt",
    "build_review",
    "best_attempts",
    "quiz_analytics",
    "duplicate_quiz",
    "publish_problems",
]
