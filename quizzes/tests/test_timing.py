from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from quizzes import services
from quizzes.models import Answer, Attempt
from quizzes.tests.base import QuizTestCase, correct_option, make_quiz


class OpenCloseWindowTests(QuizTestCase):
    def test_cannot_start_before_open_date(self):
        now = timezone.now()
        quiz = make_quiz(self.teacher, opens_at=now + timedelta(hours=1), closes_at=now + timedelta(hours=2))
        with self.assertRaises(services.StartError):
            services.start_attempt(quiz, self.student)

    def test_cannot_start_after_close_date(self):
        now = timezone.now()
        quiz = make_quiz(self.teacher, opens_at=now - timedelta(days=2), closes_at=now - timedelta(days=1))
        with self.assertRaises(services.StartError):
            services.start_attempt(quiz, self.student)

    def test_cannot_start_a_draft(self):
        quiz = make_quiz(self.teacher, published=False)
        with self.assertRaises(services.StartError):
            services.start_attempt(quiz, self.student)

    def test_start_view_enforces_the_window_on_the_server(self):
        now = timezone.now()
        quiz = make_quiz(self.teacher, opens_at=now + timedelta(hours=1), closes_at=now + timedelta(hours=2))
        self.client.force_login(self.student)
        response = self.client.post(reverse("quizzes:start", args=[quiz.pk]))
        self.assertRedirects(response, reverse("quizzes:detail", args=[quiz.pk]), fetch_redirect_response=False)
        self.assertEqual(Attempt.objects.count(), 0)

    def test_status_labels(self):
        now = timezone.now()
        upcoming = make_quiz(self.teacher, opens_at=now + timedelta(hours=1), closes_at=now + timedelta(hours=2))
        open_quiz = make_quiz(self.teacher)
        closed = make_quiz(self.teacher, opens_at=now - timedelta(days=2), closes_at=now - timedelta(days=1))
        draft = make_quiz(self.teacher, published=False)
        self.assertEqual(
            [q.get_status() for q in (upcoming, open_quiz, closed, draft)],
            ["upcoming", "open", "closed", "draft"],
        )


class DeadlineTests(QuizTestCase):
    def test_deadline_is_start_plus_time_limit(self):
        quiz = make_quiz(self.teacher, time_limit_minutes=30)
        now = timezone.now()
        attempt, _ = services.start_attempt(quiz, self.student, now=now)
        self.assertEqual(attempt.deadline, now + timedelta(minutes=30))

    def test_deadline_never_later_than_close_date(self):
        now = timezone.now()
        quiz = make_quiz(self.teacher, time_limit_minutes=30, closes_at=now + timedelta(minutes=10))
        attempt, _ = services.start_attempt(quiz, self.student, now=now)
        self.assertEqual(attempt.deadline, quiz.closes_at)


class DeadlineEnforcementTests(QuizTestCase):
    def setUp(self):
        super().setUp()
        self.quiz = make_quiz(self.teacher, questions=3)
        self.attempt, _ = services.start_attempt(self.quiz, self.student)
        self.client.force_login(self.student)

    def posted_correct_answers(self):
        data = {}
        for question in self.quiz.questions.all():
            data[f"q_{question.pk}"] = correct_option(question).pk
        return data

    def test_autosave_is_refused_after_deadline(self):
        self.expire(self.attempt, 30)
        question = self.quiz.questions.first()
        with self.assertRaises(services.AnswerError):
            services.record_answer(self.attempt, question.pk, correct_option(question).pk)

    def test_autosave_view_returns_403_after_deadline(self):
        self.expire(self.attempt, 30)
        question = self.quiz.questions.first()
        response = self.client.post(
            reverse("quizzes:save_answer", args=[self.attempt.pk]),
            {"question": question.pk, "option": correct_option(question).pk},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Answer.objects.count(), 0)

    def test_autosave_works_before_deadline(self):
        question = self.quiz.questions.first()
        response = self.client.post(
            reverse("quizzes:save_answer", args=[self.attempt.pk]),
            {"question": question.pk, "option": correct_option(question).pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Answer.objects.count(), 1)

    def test_late_submit_ignores_posted_answers(self):
        self.expire(self.attempt, 60)  # a minute late: well outside the grace period
        self.client.post(reverse("quizzes:submit", args=[self.attempt.pk]), self.posted_correct_answers())
        self.attempt.refresh_from_db()
        self.assertTrue(self.attempt.is_submitted)
        self.assertEqual(self.attempt.correct_count, 0)
        self.assertEqual(self.attempt.unanswered_count, 3)

    def test_submit_inside_grace_period_counts(self):
        self.expire(self.attempt, 1)  # one second late: inside the 5 second grace
        self.client.post(reverse("quizzes:submit", args=[self.attempt.pk]), self.posted_correct_answers())
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.correct_count, 3)

    def test_submitted_time_is_capped_at_deadline(self):
        self.expire(self.attempt, 600)
        self.client.post(reverse("quizzes:submit", args=[self.attempt.pk]), {})
        self.attempt.refresh_from_db()
        self.assertLessEqual(self.attempt.submitted_at, self.attempt.deadline)

    def test_opening_quiz_page_after_deadline_auto_submits(self):
        question = self.quiz.questions.first()
        services.record_answer(self.attempt, question.pk, correct_option(question).pk)
        self.expire(self.attempt, 5)
        response = self.client.get(reverse("quizzes:take", args=[self.attempt.pk]))
        self.assertRedirects(
            response, reverse("quizzes:result", args=[self.attempt.pk]), fetch_redirect_response=False
        )
        self.attempt.refresh_from_db()
        self.assertTrue(self.attempt.is_submitted)
        self.assertEqual(self.attempt.correct_count, 1)  # the autosaved answer still counts

    def test_cannot_change_answers_after_submission(self):
        services.submit_attempt(self.attempt)
        question = self.quiz.questions.first()
        response = self.client.post(
            reverse("quizzes:save_answer", args=[self.attempt.pk]),
            {"question": question.pk, "option": correct_option(question).pk},
        )
        self.assertEqual(response.status_code, 409)

    def test_answers_survive_a_refresh(self):
        question = self.quiz.questions.first()
        option = correct_option(question)
        services.record_answer(self.attempt, question.pk, option.pk)
        for _ in range(2):  # "refresh" twice
            response = self.client.get(reverse("quizzes:take", args=[self.attempt.pk]))
            self.assertEqual(response.status_code, 200)
            selected = {item["id"]: item["selected"] for item in response.context["items"]}
            self.assertEqual(selected[question.pk], option.pk)

    def test_remaining_time_comes_from_the_server(self):
        response = self.client.get(reverse("quizzes:take", args=[self.attempt.pk]))
        remaining = response.context["remaining_seconds"]
        self.assertTrue(29 * 60 <= remaining <= 30 * 60)

    def test_correct_answers_are_never_sent_before_submission(self):
        response = self.client.get(reverse("quizzes:take", args=[self.attempt.pk]))
        html = response.content.decode()
        self.assertNotIn("Explanation", html)
        self.assertNotIn("is_correct", html)
        for item in response.context["items"]:
            for option in item["options"]:
                self.assertEqual(set(option.keys()), {"id", "text"})

    def test_result_page_is_not_available_until_submitted(self):
        response = self.client.get(reverse("quizzes:result", args=[self.attempt.pk]))
        self.assertRedirects(
            response, reverse("quizzes:take", args=[self.attempt.pk]), fetch_redirect_response=False
        )
