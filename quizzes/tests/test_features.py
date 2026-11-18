import csv
import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from quizzes import services
from quizzes.forms import QuestionForm, QuizForm
from quizzes.models import Option, Question, Quiz
from quizzes.tests.base import PASSWORD, QuizTestCase, make_quiz, make_student, quick_attempt

User = get_user_model()


class DuplicateTests(QuizTestCase):
    def test_duplicate_copies_everything_into_a_draft_without_dates(self):
        quiz = make_quiz(
            self.teacher, questions=3, max_attempts=3, negative_marking="0.25",
            shuffle_questions=True, shuffle_options=True, pass_mark=60, time_limit_minutes=45,
        )
        self.client.force_login(self.teacher)
        response = self.client.post(reverse("quizzes:duplicate", args=[quiz.pk]))
        clone = Quiz.objects.exclude(pk=quiz.pk).get()
        self.assertRedirects(response, reverse("quizzes:manage", args=[clone.pk]), fetch_redirect_response=False)

        self.assertEqual(clone.title, "Copy of Test quiz")
        self.assertFalse(clone.is_published)
        self.assertIsNone(clone.opens_at)
        self.assertIsNone(clone.closes_at)
        self.assertEqual(clone.teacher, self.teacher)
        self.assertEqual(
            (clone.max_attempts, str(clone.negative_marking), clone.pass_mark, clone.time_limit_minutes,
             clone.shuffle_questions, clone.shuffle_options),
            (3, "0.25", 60, 45, True, True),
        )
        self.assertEqual(clone.questions.count(), 3)
        for original, copy in zip(quiz.questions.all(), clone.questions.all()):
            self.assertNotEqual(original.pk, copy.pk)
            self.assertEqual((original.text, original.topic, original.explanation),
                             (copy.text, copy.topic, copy.explanation))
            self.assertEqual(copy.options.count(), 4)
            self.assertEqual(copy.options.filter(is_correct=True).count(), 1)
            self.assertEqual(
                [(o.text, o.is_correct) for o in original.options.all()],
                [(o.text, o.is_correct) for o in copy.options.all()],
            )
        # original untouched
        quiz.refresh_from_db()
        self.assertTrue(quiz.is_published)
        self.assertEqual(quiz.questions.count(), 3)


class PublishTests(QuizTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.teacher)

    def test_cannot_publish_without_dates(self):
        quiz = make_quiz(self.teacher, published=False, opens_at=None, closes_at=None)
        self.client.post(reverse("quizzes:publish", args=[quiz.pk]))
        quiz.refresh_from_db()
        self.assertFalse(quiz.is_published)

    def test_cannot_publish_without_questions(self):
        quiz = make_quiz(self.teacher, questions=0, published=False)
        self.client.post(reverse("quizzes:publish", args=[quiz.pk]))
        quiz.refresh_from_db()
        self.assertFalse(quiz.is_published)

    def test_publish_and_back_to_draft(self):
        quiz = make_quiz(self.teacher, published=False)
        self.client.post(reverse("quizzes:publish", args=[quiz.pk]))
        quiz.refresh_from_db()
        self.assertTrue(quiz.is_published)
        self.client.post(reverse("quizzes:publish", args=[quiz.pk]))
        quiz.refresh_from_db()
        self.assertFalse(quiz.is_published)

    def test_cannot_unpublish_after_attempts(self):
        quiz = make_quiz(self.teacher)
        quick_attempt(quiz, self.student, correct=1)
        self.client.post(reverse("quizzes:publish", args=[quiz.pk]))
        quiz.refresh_from_db()
        self.assertTrue(quiz.is_published)


class QuestionBuilderTests(QuizTestCase):
    def valid_data(self, **extra):
        data = {
            "text": "What is 2 + 2?", "topic": "Maths",
            "option_1": "3", "option_2": "4", "option_3": "5", "option_4": "6",
            "correct": "2", "explanation": "Basic addition.",
        }
        data.update(extra)
        return data

    def test_question_form_creates_four_options_with_one_correct(self):
        quiz = make_quiz(self.teacher, questions=0, published=False)
        form = QuestionForm(self.valid_data())
        self.assertTrue(form.is_valid(), form.errors)
        question = form.save(quiz)
        self.assertEqual(question.options.count(), 4)
        self.assertEqual(question.options.get(is_correct=True).text, "4")

    def test_editing_can_move_the_correct_answer(self):
        quiz = make_quiz(self.teacher, questions=0, published=False)
        first = QuestionForm(self.valid_data())
        self.assertTrue(first.is_valid(), first.errors)
        question = first.save(quiz)
        form = QuestionForm(self.valid_data(correct="4"), question=question)
        self.assertTrue(form.is_valid(), form.errors)
        form.save(quiz)
        self.assertEqual(question.options.filter(is_correct=True).count(), 1)
        self.assertEqual(question.options.get(is_correct=True).text, "6")

    def test_duplicate_options_are_rejected(self):
        form = QuestionForm(self.valid_data(option_3="3"))
        self.assertFalse(form.is_valid())

    def test_correct_answer_is_required(self):
        data = self.valid_data()
        del data["correct"]
        self.assertFalse(QuestionForm(data).is_valid())

    def test_questions_are_locked_after_students_attempt(self):
        quiz = make_quiz(self.teacher)
        quick_attempt(quiz, self.student, correct=1)
        self.client.force_login(self.teacher)
        before = Question.objects.count()
        self.client.post(reverse("quizzes:question_add", args=[quiz.pk]), self.valid_data())
        self.assertEqual(Question.objects.count(), before)
        question = quiz.questions.first()
        self.client.post(reverse("quizzes:question_delete", args=[quiz.pk, question.pk]))
        self.assertTrue(Question.objects.filter(pk=question.pk).exists())

    def test_quiz_form_rejects_close_before_open(self):
        now = timezone.now().replace(microsecond=0)
        fmt = "%Y-%m-%dT%H:%M"
        form = QuizForm({
            "title": "X", "time_limit_minutes": 10, "pass_mark": 40, "max_attempts": 1,
            "negative_marking": "0", "opens_at": (now + timedelta(days=2)).strftime(fmt),
            "closes_at": (now + timedelta(days=1)).strftime(fmt),
        })
        self.assertFalse(form.is_valid())
        self.assertIn("closes_at", form.errors)

    def test_negative_marking_must_be_between_zero_and_one(self):
        base = {"title": "X", "time_limit_minutes": 10, "pass_mark": 40, "max_attempts": 1}
        self.assertFalse(QuizForm({**base, "negative_marking": "-0.5"}).is_valid())
        self.assertFalse(QuizForm({**base, "negative_marking": "2"}).is_valid())
        self.assertTrue(QuizForm({**base, "negative_marking": "0.25"}).is_valid())

    def test_teacher_can_create_quiz_through_the_view(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse("quizzes:create"), {
            "title": "Brand new", "description": "", "time_limit_minutes": 20, "pass_mark": 50,
            "max_attempts": 2, "negative_marking": "0.25", "opens_at": "", "closes_at": "",
        })
        quiz = Quiz.objects.get(title="Brand new")
        self.assertRedirects(response, reverse("quizzes:manage", args=[quiz.pk]), fetch_redirect_response=False)
        self.assertEqual(quiz.teacher, self.teacher)
        self.assertFalse(quiz.is_published)
        self.assertEqual(quiz.max_attempts, 2)


class StudentListTests(QuizTestCase):
    def test_quizzes_are_grouped_into_upcoming_open_and_closed(self):
        now = timezone.now()
        make_quiz(self.teacher, title="Soon", opens_at=now + timedelta(days=1), closes_at=now + timedelta(days=2))
        make_quiz(self.teacher, title="Now")
        make_quiz(self.teacher, title="Past", opens_at=now - timedelta(days=3), closes_at=now - timedelta(days=1))
        self.client.force_login(self.student)
        response = self.client.get(reverse("quizzes:student_list"))
        self.assertEqual([e["quiz"].title for e in response.context["upcoming"]], ["Soon"])
        self.assertEqual([e["quiz"].title for e in response.context["open_now"]], ["Now"])
        self.assertEqual([e["quiz"].title for e in response.context["closed"]], ["Past"])


class ExportTests(QuizTestCase):
    def test_csv_has_one_row_per_attempt_with_attempt_number(self):
        quiz = make_quiz(self.teacher, questions=4, max_attempts=3)
        other = make_student("other")
        quick_attempt(quiz, self.student, correct=1)
        quick_attempt(quiz, self.student, correct=3)
        quick_attempt(quiz, other, correct=2)
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("quizzes:export_csv", args=[quiz.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        header, body = rows[0], rows[1:]
        self.assertIn("Attempt number", header)
        self.assertEqual(len(body), 3)
        column = header.index("Attempt number")
        self.assertEqual(sorted((r[0], r[column]) for r in body),
                         [("other", "1"), ("student", "1"), ("student", "2")])

    def test_csv_cells_cannot_start_a_spreadsheet_formula(self):
        from quizzes.views_teacher import _safe_cell

        self.assertEqual(_safe_cell("=SUM(A1)"), "'=SUM(A1)")
        self.assertEqual(_safe_cell("normal"), "normal")


class AccountTests(QuizTestCase):
    def test_student_registration_creates_a_student_with_hashed_password(self):
        response = self.client.post(reverse("register"), {
            "username": "newbie", "first_name": "New", "last_name": "Student",
            "email": "newbie@example.com", "password1": PASSWORD, "password2": PASSWORD,
        })
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        user = User.objects.get(username="newbie")
        self.assertNotEqual(user.password, PASSWORD)  # never stored as plain text
        self.assertNotIn(PASSWORD, user.password)
        self.assertTrue(user.check_password(PASSWORD))  # Django's hasher verifies it
        self.assertFalse(user.groups.filter(name="Teacher").exists())
        self.assertFalse(user.is_staff)

    def test_login_and_logout(self):
        response = self.client.post(reverse("login"), {"username": "student", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)
        self.client.post(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_home_sends_each_role_to_its_own_page(self):
        self.client.force_login(self.teacher)
        self.assertRedirects(self.client.get(reverse("home")), reverse("quizzes:teacher_list"),
                             fetch_redirect_response=False)
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get(reverse("home")), reverse("quizzes:student_list"),
                             fetch_redirect_response=False)

    def test_profile_update(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse("profile"), {
            "save_profile": "1", "first_name": "Renamed", "last_name": "Person", "email": "renamed@example.com",
        })
        self.assertRedirects(response, reverse("profile"), fetch_redirect_response=False)
        self.student.refresh_from_db()
        self.assertEqual(
            (self.student.first_name, self.student.last_name, self.student.email),
            ("Renamed", "Person", "renamed@example.com"),
        )

    def test_profile_email_must_be_unique(self):
        make_student("someone")
        self.client.force_login(self.student)
        self.client.post(reverse("profile"), {
            "save_profile": "1", "first_name": "A", "last_name": "B", "email": "someone@example.com",
        })
        self.student.refresh_from_db()
        self.assertNotEqual(self.student.email, "someone@example.com")

    def test_change_password_keeps_user_logged_in(self):
        self.client.force_login(self.student)
        new_password = "An0ther!Strong#Pass77"
        response = self.client.post(reverse("profile"), {
            "change_password": "1", "old_password": PASSWORD,
            "new_password1": new_password, "new_password2": new_password,
        })
        self.assertRedirects(response, reverse("profile"), fetch_redirect_response=False)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(new_password))
        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)  # still logged in

    def test_wrong_old_password_is_rejected(self):
        self.client.force_login(self.student)
        self.client.post(reverse("profile"), {
            "change_password": "1", "old_password": "nope",
            "new_password1": "An0ther!Strong#Pass77", "new_password2": "An0ther!Strong#Pass77",
        })
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(PASSWORD))


class FullFlowTests(QuizTestCase):
    def test_student_takes_quiz_and_sees_result_with_review(self):
        quiz = make_quiz(self.teacher, questions=2, max_attempts=2, negative_marking="0.25")
        self.client.force_login(self.student)
        response = self.client.post(reverse("quizzes:start", args=[quiz.pk]))
        attempt = quiz.attempts.get()
        self.assertRedirects(response, reverse("quizzes:take", args=[attempt.pk]), fetch_redirect_response=False)

        q1, q2 = list(quiz.questions.all())
        data = {
            f"q_{q1.pk}": q1.options.get(is_correct=True).pk,
            f"q_{q2.pk}": q2.options.filter(is_correct=False).first().pk,
        }
        self.client.post(reverse("quizzes:submit", args=[attempt.pk]), data)
        result = self.client.get(reverse("quizzes:result", args=[attempt.pk]))
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Explanation 1")
        self.assertContains(result, "Correct answer")
        attempt.refresh_from_db()
        self.assertEqual(float(attempt.score), 0.75)  # 1 - 0.25
        self.assertEqual([h.pk for h in result.context["history"]], [attempt.pk])

    def test_services_exports_match_what_views_use(self):
        for name in ("start_attempt", "record_answer", "submit_attempt", "best_attempts",
                     "quiz_analytics", "duplicate_quiz", "publish_problems", "finalize_expired"):
            self.assertTrue(callable(getattr(services, name)), name)
        self.assertEqual(Option.objects.count(), 0)
