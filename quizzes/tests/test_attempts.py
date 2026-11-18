from datetime import timedelta

from django.utils import timezone

from quizzes import services
from quizzes.models import Attempt
from quizzes.tests.base import QuizTestCase, make_quiz, make_student, quick_attempt


class AttemptLimitTests(QuizTestCase):
    def test_default_limit_is_one_attempt(self):
        quiz = make_quiz(self.teacher)
        self.assertEqual(quiz.max_attempts, 1)
        attempt, _ = services.start_attempt(quiz, self.student)
        services.submit_attempt(attempt)
        with self.assertRaises(services.StartError):
            services.start_attempt(quiz, self.student)

    def test_two_attempts_allowed_third_refused(self):
        quiz = make_quiz(self.teacher, max_attempts=2)
        first, _ = services.start_attempt(quiz, self.student)
        services.submit_attempt(first)
        second, created = services.start_attempt(quiz, self.student)
        self.assertTrue(created)
        services.submit_attempt(second)
        self.assertEqual((first.attempt_number, second.attempt_number), (1, 2))
        with self.assertRaises(services.StartError):
            services.start_attempt(quiz, self.student)

    def test_starting_again_resumes_the_unfinished_attempt(self):
        quiz = make_quiz(self.teacher, max_attempts=3)
        first, created_first = services.start_attempt(quiz, self.student)
        again, created_again = services.start_attempt(quiz, self.student)
        self.assertTrue(created_first)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(Attempt.objects.count(), 1)

    def test_timed_out_attempt_still_uses_up_an_attempt(self):
        quiz = make_quiz(self.teacher, max_attempts=1)
        attempt, _ = services.start_attempt(quiz, self.student)
        self.expire(attempt, 60)
        with self.assertRaises(services.StartError):
            services.start_attempt(quiz, self.student)
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_submitted)  # it was auto-marked

    def test_limits_are_per_student(self):
        quiz = make_quiz(self.teacher, max_attempts=1)
        other = make_student("other")
        a, _ = services.start_attempt(quiz, self.student)
        b, _ = services.start_attempt(quiz, other)
        self.assertNotEqual(a.pk, b.pk)


class BestAttemptTests(QuizTestCase):
    def test_best_attempt_counts_once_per_student(self):
        quiz = make_quiz(self.teacher, questions=4, max_attempts=3)
        quick_attempt(quiz, self.student, correct=1)
        quick_attempt(quiz, self.student, correct=3)
        quick_attempt(quiz, self.student, correct=2)
        best = services.best_attempts(quiz)
        self.assertEqual(len(best), 1)
        self.assertEqual(best[0].attempt_number, 2)
        self.assertEqual(float(best[0].score), 3.0)

    def test_leaderboard_orders_by_score_then_time(self):
        quiz = make_quiz(self.teacher, questions=4)
        fast = make_student("fast")
        slow = make_student("slow")
        top = make_student("top")
        quick_attempt(quiz, slow, correct=3, seconds=300)
        quick_attempt(quiz, fast, correct=3, seconds=90)
        quick_attempt(quiz, top, correct=4, seconds=500)
        ranking = [a.student.username for a in services.best_attempts(quiz)]
        self.assertEqual(ranking, ["top", "fast", "slow"])

    def test_unsubmitted_attempts_are_not_ranked(self):
        quiz = make_quiz(self.teacher)
        services.start_attempt(quiz, self.student)
        self.assertEqual(services.best_attempts(quiz), [])


class AnalyticsTests(QuizTestCase):
    def test_numbers_use_each_students_best_attempt(self):
        quiz = make_quiz(self.teacher, questions=2, pass_mark=50, max_attempts=2)
        s2, s3 = make_student("s2"), make_student("s3")
        quick_attempt(quiz, self.student, correct=0)  # first try: 0
        quick_attempt(quiz, self.student, correct=2)  # best: 2 of 2
        quick_attempt(quiz, s2, correct=1, wrong=1)  # q1 right, q2 wrong
        quick_attempt(quiz, s3, correct=0, wrong=2)  # both wrong

        stats = services.quiz_analytics(quiz)
        self.assertEqual(stats["students"], 3)
        self.assertEqual(stats["highest_score"], 2.0)
        self.assertEqual(stats["lowest_score"], 0.0)
        self.assertEqual(stats["average_percentage"], 50.0)
        self.assertEqual(stats["pass_rate"], 66.7)
        self.assertEqual(sum(stats["distribution_counts"]), 3)
        self.assertEqual(stats["distribution_counts"][9], 1)  # the 100% student

        per_question = {q["number"]: q["percent_correct"] for q in stats["per_question"]}
        self.assertEqual(per_question, {1: 66.7, 2: 33.3})

        topics = {t["topic"]: t for t in stats["topics"]}
        self.assertEqual(topics["Topic A"]["percent_correct"], 66.7)
        self.assertFalse(topics["Topic A"]["weak"])
        self.assertTrue(topics["Topic B"]["weak"])
        self.assertEqual(stats["weak_topics"][0]["topic"], "Topic B")

    def test_empty_quiz_has_no_data(self):
        quiz = make_quiz(self.teacher)
        self.assertFalse(services.quiz_analytics(quiz)["has_data"])

    def test_old_attempts_are_finalised_for_analytics(self):
        quiz = make_quiz(self.teacher)
        started = timezone.now() - timedelta(hours=3)
        attempt = services.build_attempt(quiz, self.student, started, 1)
        services.finalize_expired(quiz=quiz)
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_submitted)
