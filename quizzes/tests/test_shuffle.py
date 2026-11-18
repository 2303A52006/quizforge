from django.urls import reverse

from quizzes import services
from quizzes.tests.base import QuizTestCase, make_quiz, make_student


class ShuffleTests(QuizTestCase):
    def test_without_shuffle_the_original_order_is_used(self):
        quiz = make_quiz(self.teacher, questions=6)
        attempt, _ = services.start_attempt(quiz, self.student)
        natural = list(quiz.questions.values_list("pk", flat=True))
        self.assertEqual(attempt.question_order, natural)
        for question in quiz.questions.all():
            natural_options = list(question.options.values_list("pk", flat=True))
            self.assertEqual(attempt.option_order[str(question.pk)], natural_options)

    def test_order_is_a_permutation_of_all_questions_and_options(self):
        quiz = make_quiz(self.teacher, questions=8, shuffle_questions=True, shuffle_options=True)
        attempt, _ = services.start_attempt(quiz, self.student)
        self.assertEqual(sorted(attempt.question_order), sorted(quiz.questions.values_list("pk", flat=True)))
        for question in quiz.questions.all():
            stored = attempt.option_order[str(question.pk)]
            self.assertEqual(sorted(stored), sorted(question.options.values_list("pk", flat=True)))

    def test_shuffle_actually_shuffles(self):
        quiz = make_quiz(self.teacher, questions=10, shuffle_questions=True, shuffle_options=True, max_attempts=1)
        natural = list(quiz.questions.values_list("pk", flat=True))
        natural_options = {
            str(q.pk): list(q.options.values_list("pk", flat=True)) for q in quiz.questions.all()
        }
        question_orders, option_orders = [], []
        for i in range(6):
            attempt, _ = services.start_attempt(quiz, make_student(f"shuffler{i}"))
            question_orders.append(attempt.question_order)
            option_orders.append(attempt.option_order)
        self.assertTrue(any(order != natural for order in question_orders))
        self.assertTrue(any(order != natural_options for order in option_orders))

    def test_order_does_not_change_on_refresh(self):
        quiz = make_quiz(self.teacher, questions=10, shuffle_questions=True, shuffle_options=True)
        attempt, _ = services.start_attempt(quiz, self.student)
        self.client.force_login(self.student)

        seen = []
        for _ in range(3):  # three page loads = three "refreshes"
            response = self.client.get(reverse("quizzes:take", args=[attempt.pk]))
            items = response.context["items"]
            seen.append(
                (
                    [item["id"] for item in items],
                    {item["id"]: [o["id"] for o in item["options"]] for item in items},
                )
            )
        stored_questions = attempt.question_order
        stored_options = {int(k): v for k, v in attempt.option_order.items()}
        for question_ids, option_ids in seen:
            self.assertEqual(question_ids, stored_questions)
            self.assertEqual(option_ids, stored_options)

    def test_resuming_keeps_the_same_stored_order(self):
        quiz = make_quiz(self.teacher, questions=10, shuffle_questions=True, shuffle_options=True)
        first, _ = services.start_attempt(quiz, self.student)
        resumed, _ = services.start_attempt(quiz, self.student)
        self.assertEqual(first.question_order, resumed.question_order)
        self.assertEqual(first.option_order, resumed.option_order)
