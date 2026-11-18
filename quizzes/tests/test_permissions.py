from django.test import Client
from django.urls import reverse

from quizzes import services
from quizzes.models import Attempt, Question
from quizzes.tests.base import (
    PASSWORD,
    QuizTestCase,
    make_quiz,
    make_student,
    make_teacher,
    quick_attempt,
)


class PermissionTests(QuizTestCase):
    def setUp(self):
        super().setUp()
        self.quiz = make_quiz(self.teacher)
        self.other_teacher = make_teacher("teacher2")
        self.question = self.quiz.questions.first()

    # URLs only teachers may open (GET), and ones that need the quiz id
    def teacher_get_urls(self):
        pk = self.quiz.pk
        return [
            reverse("quizzes:teacher_list"),
            reverse("quizzes:create"),
            reverse("quizzes:manage", args=[pk]),
            reverse("quizzes:edit", args=[pk]),
            reverse("quizzes:analytics", args=[pk]),
            reverse("quizzes:export_csv", args=[pk]),
            reverse("quizzes:question_add", args=[pk]),
            reverse("quizzes:question_edit", args=[pk, self.question.pk]),
        ]

    def teacher_post_urls(self):
        pk = self.quiz.pk
        return [
            reverse("quizzes:publish", args=[pk]),
            reverse("quizzes:duplicate", args=[pk]),
            reverse("quizzes:question_delete", args=[pk, self.question.pk]),
        ]

    def owned_quiz_urls(self):
        """Teacher URLs that belong to one specific quiz."""
        return [u for u in self.teacher_get_urls() + self.teacher_post_urls()
                if str(self.quiz.pk) in u]

    # ----- anonymous
    def test_anonymous_users_are_sent_to_login(self):
        for url in self.teacher_get_urls() + [reverse("quizzes:student_list")]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertTrue(response["Location"].startswith(reverse("login")), url)
        for url in self.teacher_post_urls():
            response = self.client.post(url)
            self.assertTrue(response["Location"].startswith(reverse("login")), url)

    # ----- students
    def test_students_cannot_open_teacher_pages(self):
        self.client.force_login(self.student)
        for url in self.teacher_get_urls():
            self.assertEqual(self.client.get(url).status_code, 403, url)
        for url in self.teacher_post_urls():
            self.assertEqual(self.client.post(url).status_code, 403, url)

    def test_student_cannot_publish_or_duplicate_via_post(self):
        self.client.force_login(self.student)
        before = self.quiz.__class__.objects.count()
        self.client.post(reverse("quizzes:duplicate", args=[self.quiz.pk]))
        self.assertEqual(self.quiz.__class__.objects.count(), before)

    # ----- teachers
    def test_teachers_cannot_open_student_pages(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("quizzes:student_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("quizzes:detail", args=[self.quiz.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("quizzes:start", args=[self.quiz.pk])).status_code, 403)

    def test_teacher_can_open_own_pages(self):
        self.client.force_login(self.teacher)
        for url in self.teacher_get_urls():
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_teacher_cannot_manage_another_teachers_quiz(self):
        self.client.force_login(self.other_teacher)
        for url in self.owned_quiz_urls():
            if url in self.teacher_post_urls():
                self.assertEqual(self.client.post(url).status_code, 404, url)
            else:
                self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertTrue(Question.objects.filter(pk=self.question.pk).exists())
        self.quiz.refresh_from_db()
        self.assertFalse(self.quiz.title.startswith("Copy of"))

    def test_other_teacher_cannot_see_leaderboard(self):
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(reverse("quizzes:leaderboard", args=[self.quiz.pk])).status_code, 404)

    def test_owner_can_see_leaderboard(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("quizzes:leaderboard", args=[self.quiz.pk])).status_code, 200)

    # ----- leaderboard visibility for students
    def test_student_needs_a_finished_attempt_to_see_leaderboard(self):
        url = reverse("quizzes:leaderboard", args=[self.quiz.pk])
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(url).status_code, 403)
        quick_attempt(self.quiz, self.student, correct=2)
        self.assertEqual(self.client.get(url).status_code, 200)

    # ----- attempts belong to their owner
    def test_student_cannot_touch_another_students_attempt(self):
        attempt, _ = services.start_attempt(self.quiz, self.student)
        intruder = make_student("intruder")
        self.client.force_login(intruder)
        self.assertEqual(self.client.get(reverse("quizzes:take", args=[attempt.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("quizzes:result", args=[attempt.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("quizzes:submit", args=[attempt.pk])).status_code, 404)
        response = self.client.post(
            reverse("quizzes:save_answer", args=[attempt.pk]),
            {"question": self.question.pk, "option": ""},
        )
        self.assertEqual(response.status_code, 404)
        attempt.refresh_from_db()
        self.assertFalse(attempt.is_submitted)

    def test_students_cannot_see_draft_quizzes(self):
        draft = make_quiz(self.teacher, published=False, title="Secret draft")
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("quizzes:detail", args=[draft.pk])).status_code, 404)
        response = self.client.get(reverse("quizzes:student_list"))
        listed = [e["quiz"].pk for key in ("open_now", "upcoming", "closed") for e in response.context[key]]
        self.assertNotIn(draft.pk, listed)
        self.assertEqual(self.client.post(reverse("quizzes:start", args=[draft.pk])).status_code, 404)
        self.assertEqual(Attempt.objects.count(), 0)

    # ----- CSRF
    def test_post_without_csrf_token_is_rejected(self):
        strict = Client(enforce_csrf_checks=True)
        strict.login(username="student", password=PASSWORD)
        response = strict.post(reverse("quizzes:start", args=[self.quiz.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Attempt.objects.count(), 0)

    def test_login_page_contains_csrf_token(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, "csrfmiddlewaretoken")
