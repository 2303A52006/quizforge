from decimal import Decimal

from quizzes import services
from quizzes.tests.base import QuizTestCase, correct_option, make_quiz, wrong_option


class ScoringTests(QuizTestCase):
    def finish(self, quiz, correct=0, wrong=0):
        attempt, _ = services.start_attempt(quiz, self.student)
        questions = list(quiz.questions.all())
        for question in questions[:correct]:
            services.record_answer(attempt, question.pk, correct_option(question).pk)
        for question in questions[correct : correct + wrong]:
            services.record_answer(attempt, question.pk, wrong_option(question).pk)
        services.submit_attempt(attempt)
        attempt.refresh_from_db()
        return attempt

    def test_all_correct_gives_full_marks(self):
        quiz = make_quiz(self.teacher, questions=4)
        attempt = self.finish(quiz, correct=4)
        self.assertEqual(attempt.score, Decimal("4.00"))
        self.assertEqual(attempt.percentage, Decimal("100.00"))
        self.assertTrue(attempt.passed)
        self.assertEqual((attempt.correct_count, attempt.wrong_count, attempt.unanswered_count), (4, 0, 0))

    def test_wrong_answers_cost_nothing_without_negative_marking(self):
        quiz = make_quiz(self.teacher, questions=4)
        attempt = self.finish(quiz, correct=2, wrong=2)
        self.assertEqual(attempt.score, Decimal("2.00"))

    def test_negative_marking_deducts_for_wrong_answers_only(self):
        quiz = make_quiz(self.teacher, questions=4, negative_marking=Decimal("0.25"))
        # 2 correct, 1 wrong, 1 unanswered -> 2 - 0.25 = 1.75
        attempt = self.finish(quiz, correct=2, wrong=1)
        self.assertEqual(attempt.score, Decimal("1.75"))
        self.assertEqual(attempt.percentage, Decimal("43.75"))
        self.assertEqual(attempt.unanswered_count, 1)
        self.assertFalse(attempt.passed)  # pass mark is 50%

    def test_unanswered_questions_are_not_penalised(self):
        quiz = make_quiz(self.teacher, questions=4, negative_marking=Decimal("0.50"))
        attempt = self.finish(quiz, correct=2, wrong=0)
        self.assertEqual(attempt.score, Decimal("2.00"))
        self.assertEqual(attempt.unanswered_count, 2)

    def test_score_never_goes_below_zero(self):
        quiz = make_quiz(self.teacher, questions=4, negative_marking=Decimal("1.00"))
        attempt = self.finish(quiz, correct=1, wrong=3)  # 1 - 3 = -2 -> 0
        self.assertEqual(attempt.score, Decimal("0.00"))
        self.assertEqual(attempt.percentage, Decimal("0.00"))
        self.assertFalse(attempt.passed)

    def test_pass_mark_boundary(self):
        quiz = make_quiz(self.teacher, questions=4, pass_mark=50, max_attempts=2)
        first = self.finish(quiz, correct=2)  # exactly 50%
        self.assertTrue(first.passed)
        second = self.finish(quiz, correct=1)  # 25%
        self.assertFalse(second.passed)

    def test_scoring_uses_option_ids_not_positions(self):
        quiz = make_quiz(self.teacher, questions=1, shuffle_options=True)
        attempt, _ = services.start_attempt(quiz, self.student)
        question = quiz.questions.get()
        # Force a known display order: correct option shown last.
        ids = [o.pk for o in question.options.all()]
        attempt.option_order = {str(question.pk): list(reversed(ids))}
        attempt.save()

        shown = services.questions_for_attempt(attempt)[0]["options"]
        self.assertEqual([o["id"] for o in shown], list(reversed(ids)))
        services.record_answer(attempt, question.pk, correct_option(question).pk)
        services.submit_attempt(attempt)
        attempt.refresh_from_db()
        self.assertEqual(attempt.correct_count, 1)
        self.assertEqual(attempt.score, Decimal("1.00"))

    def test_option_from_another_question_is_rejected(self):
        quiz = make_quiz(self.teacher, questions=2)
        attempt, _ = services.start_attempt(quiz, self.student)
        q1, q2 = list(quiz.questions.all())
        with self.assertRaises(services.AnswerError):
            services.record_answer(attempt, q1.pk, correct_option(q2).pk)

    def test_review_shows_correct_answer_and_explanation(self):
        quiz = make_quiz(self.teacher, questions=1)
        attempt = self.finish(quiz, wrong=1)
        review = services.build_review(attempt)
        self.assertEqual(review[0]["state"], "wrong")
        self.assertEqual([o["is_correct"] for o in review[0]["options"]].count(True), 1)
        self.assertEqual(review[0]["question"].explanation, "Explanation 1")
