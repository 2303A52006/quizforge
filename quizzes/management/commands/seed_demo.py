"""Fill the database with demo data so every page looks full.

Usage:  python manage.py seed_demo
Safe to run again: it rebuilds the demo teacher's quizzes from scratch.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.permissions import TEACHER_GROUP
from quizzes import services
from quizzes.models import Answer, Option, Question, Quiz

User = get_user_model()

ADMIN = ("admin", "Admin@12345")
TEACHER = ("teacher1", "Teacher@12345")
STUDENT_PASSWORD = "Student@12345"

STUDENT_NAMES = [
    ("Aarav", "Sharma"), ("Diya", "Patel"), ("Kabir", "Singh"), ("Meera", "Nair"),
    ("Rohan", "Gupta"), ("Ananya", "Reddy"), ("Vivaan", "Joshi"), ("Isha", "Verma"),
    ("Arjun", "Mehta"), ("Sneha", "Iyer"),
]

# (topic, question, [4 options], index of the correct option, explanation)
QUESTIONS = [
    # ---- Python Basics (0-6)
    ("Python Basics", "Which keyword is used to define a function in Python?",
     ["func", "def", "function", "lambda only"], 1,
     "Functions are defined with the 'def' keyword followed by the name and parameters."),
    ("Python Basics", "What does type([]) return?",
     ["<class 'tuple'>", "<class 'dict'>", "<class 'list'>", "<class 'set'>"], 2,
     "[] is an empty list literal, so its type is list."),
    ("Python Basics", "Which of these data types is immutable?",
     ["list", "dict", "set", "tuple"], 3,
     "Tuples cannot be changed after creation; lists, dicts and sets can."),
    ("Python Basics", "What does len('QuizForge') return?",
     ["8", "9", "10", "7"], 1,
     "Q-u-i-z-F-o-r-g-e is 9 characters."),
    ("Python Basics", "Which operator performs floor division?",
     ["/", "%", "//", "**"], 2,
     "'//' divides and rounds down to the nearest whole number."),
    ("Python Basics", "What is the value of 3 ** 2?",
     ["6", "9", "8", "5"], 1,
     "'**' is the power operator, so 3 ** 2 = 9."),
    ("Python Basics", "Which statement block is used to handle exceptions?",
     ["try ... except", "catch ... throw", "handle ... error", "do ... rescue"], 0,
     "Python uses try/except (and optionally else/finally)."),
    # ---- Data Structures (7-12)
    ("Data Structures", "Which data structure follows the LIFO principle?",
     ["Queue", "Stack", "Array", "Graph"], 1,
     "A stack removes the most recently added element first (Last In, First Out)."),
    ("Data Structures", "What is the worst-case search time in an unbalanced binary search tree?",
     ["O(1)", "O(log n)", "O(n)", "O(n log n)"], 2,
     "A completely skewed tree behaves like a linked list, so search takes O(n)."),
    ("Data Structures", "Binary search can only be applied to a collection that is:",
     ["Sorted", "Empty", "Linked", "Hashed"], 0,
     "Binary search relies on the data being sorted so it can discard half each step."),
    ("Data Structures", "Which traversal of a binary search tree visits the keys in sorted order?",
     ["Preorder", "Postorder", "Inorder", "Level-order"], 2,
     "Inorder (left, node, right) gives ascending order for a BST."),
    ("Data Structures", "What is the operation that removes an element from a queue called?",
     ["Push", "Pop", "Peek", "Dequeue"], 3,
     "Elements are added with enqueue and removed with dequeue."),
    ("Data Structures", "What is the time complexity of reading an array element by its index?",
     ["O(1)", "O(n)", "O(log n)", "O(n^2)"], 0,
     "Array indexing uses direct address calculation, which is constant time."),
    # ---- DBMS (13-18)
    ("DBMS", "Which SQL clause is used to filter groups created by GROUP BY?",
     ["WHERE", "HAVING", "ORDER BY", "LIMIT"], 1,
     "WHERE filters rows before grouping; HAVING filters groups after aggregation."),
    ("DBMS", "What does a primary key do?",
     ["Allows duplicate rows", "Links two databases", "Uniquely identifies each row", "Encrypts the table"], 2,
     "A primary key is unique and not null, so it identifies every row."),
    ("DBMS", "Which normal form removes partial dependencies?",
     ["1NF", "2NF", "3NF", "BCNF"], 1,
     "Second Normal Form removes partial dependency on part of a composite key."),
    ("DBMS", "In ACID, what does the letter 'I' stand for?",
     ["Integrity", "Indexing", "Isolation", "Inheritance"], 2,
     "ACID = Atomicity, Consistency, Isolation, Durability."),
    ("DBMS", "Which join returns all rows from the left table even when there is no match on the right?",
     ["INNER JOIN", "LEFT JOIN", "CROSS JOIN", "SELF JOIN"], 1,
     "LEFT JOIN keeps every left-table row and fills unmatched right columns with NULL."),
    ("DBMS", "Which of these is a DDL command?",
     ["SELECT", "INSERT", "UPDATE", "CREATE"], 3,
     "CREATE defines structure (Data Definition Language); the others work with data."),
    # ---- Operating Systems (19-24)
    ("Operating Systems", "Which scheduling algorithm can cause starvation of low-priority processes?",
     ["Round robin", "Priority scheduling", "FCFS", "Time slicing"], 1,
     "If high-priority processes keep arriving, low-priority ones may never run."),
    ("Operating Systems", "Which of these is NOT a necessary condition for deadlock?",
     ["Mutual exclusion", "Hold and wait", "Circular wait", "Preemption"], 3,
     "Deadlock needs NO preemption; being able to preempt resources breaks deadlock."),
    ("Operating Systems", "Which technique divides memory into fixed-size blocks?",
     ["Paging", "Segmentation", "Spooling", "Swapping"], 0,
     "Paging splits memory into equal-sized frames and pages."),
    ("Operating Systems", "When does a running process move to the waiting state?",
     ["When it finishes", "When it requests I/O", "When it is created", "When it is killed"], 1,
     "A process waits when it needs an I/O operation or event to complete."),
    ("Operating Systems", "What is the smallest unit of CPU utilisation?",
     ["Process", "Program", "Thread", "File"], 2,
     "A thread is the basic unit of CPU use inside a process."),
    ("Operating Systems", "Which page replacement algorithm can suffer from Belady's anomaly?",
     ["LRU", "Optimal", "FIFO", "None of them"], 2,
     "With FIFO, giving a process more frames can sometimes cause more page faults."),
]

# How likely a typical student is to know each topic (makes DBMS the weak topic).
TOPIC_STRENGTH = {
    "Python Basics": 1.0,
    "Data Structures": 0.85,
    "DBMS": 0.5,
    "Operating Systems": 0.7,
}


class Command(BaseCommand):
    help = "Create demo users, questions, quizzes and sample attempts."

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(2024)
        now = timezone.now()

        admin = self._user(ADMIN[0], ADMIN[1], "Site", "Admin", is_superuser=True)
        teacher = self._user(TEACHER[0], TEACHER[1], "Priya", "Menon")
        group, _ = Group.objects.get_or_create(name=TEACHER_GROUP)
        teacher.groups.add(group)
        students = [
            self._user(f"student{i}", STUDENT_PASSWORD, first, last)
            for i, (first, last) in enumerate(STUDENT_NAMES, start=1)
        ]

        Quiz.objects.filter(teacher=teacher).delete()  # rebuild cleanly on re-run

        open_quiz = Quiz.objects.create(
            teacher=teacher, title="Computer Science Fundamentals (Open)",
            description="Mixed test on Python, data structures, DBMS and operating systems.",
            time_limit_minutes=20, pass_mark=50, max_attempts=2, negative_marking=Decimal("0.25"),
            shuffle_questions=True, shuffle_options=True,
            opens_at=now - timedelta(days=2), closes_at=now + timedelta(days=5), is_published=True,
        )
        closed_quiz = Quiz.objects.create(
            teacher=teacher, title="Mid-term Revision Test (Closed)",
            description="Last month's revision test. Results are available to review.",
            time_limit_minutes=15, pass_mark=40, max_attempts=2, negative_marking=Decimal("0.25"),
            shuffle_questions=True, shuffle_options=False,
            opens_at=now - timedelta(days=14), closes_at=now - timedelta(days=7), is_published=True,
        )
        upcoming_quiz = Quiz.objects.create(
            teacher=teacher, title="End-semester Practice Quiz (Upcoming)",
            description="Opens soon. Five quick questions.",
            time_limit_minutes=10, pass_mark=60, max_attempts=1, negative_marking=Decimal("0"),
            shuffle_questions=False, shuffle_options=True,
            opens_at=now + timedelta(days=3), closes_at=now + timedelta(days=10), is_published=True,
        )

        # 25 questions: positions 0,1 -> open quiz; 2,3 -> closed quiz; 4 -> upcoming quiz.
        targets = {0: open_quiz, 1: open_quiz, 2: closed_quiz, 3: closed_quiz, 4: upcoming_quiz}
        counters = {}
        for index, (topic, text, options, correct, explanation) in enumerate(QUESTIONS):
            quiz = targets[index % 5]
            counters[quiz.pk] = counters.get(quiz.pk, 0) + 1
            question = Question.objects.create(
                quiz=quiz, text=text, topic=topic, explanation=explanation, position=counters[quiz.pk]
            )
            for position, option_text in enumerate(options, start=1):
                Option.objects.create(
                    question=question, text=option_text,
                    is_correct=(position - 1 == correct), position=position,
                )

        skills = {s.pk: rng.uniform(0.55, 0.98) for s in students}

        # Open quiz: students 1-8 attempted; some used a second attempt and improved.
        for number, student in enumerate(students[:8], start=1):
            started = now - timedelta(hours=rng.randint(30, 46), minutes=rng.randint(0, 59))
            self._attempt(rng, open_quiz, student, started, 1, skills[student.pk])
            if number % 3 == 0:
                second = started + timedelta(hours=rng.randint(2, 20))
                self._attempt(rng, open_quiz, student, second, 2, min(1.0, skills[student.pk] + 0.2))

        # Closed quiz: every student attempted; a few made two attempts.
        for number, student in enumerate(students, start=1):
            started = now - timedelta(days=rng.randint(8, 13), hours=rng.randint(0, 20))
            self._attempt(rng, closed_quiz, student, started, 1, skills[student.pk])
            if number % 4 == 0:
                second = started + timedelta(hours=rng.randint(1, 5))
                self._attempt(rng, closed_quiz, student, second, 2, min(1.0, skills[student.pk] + 0.15))

        self.stdout.write(self.style.SUCCESS("Demo data created."))
        self.stdout.write("")
        self.stdout.write("Demo logins:")
        self.stdout.write(f"  Admin    : {ADMIN[0]} / {ADMIN[1]}   (http://127.0.0.1:8000/admin/)")
        self.stdout.write(f"  Teacher  : {TEACHER[0]} / {TEACHER[1]}")
        self.stdout.write(f"  Students : student1 ... student10 / {STUDENT_PASSWORD}")
        _ = admin  # created above; kept for clarity

    # ------------------------------------------------------------ helpers
    def _user(self, username, password, first, last, is_superuser=False):
        user, _ = User.objects.get_or_create(username=username)
        user.first_name = first
        user.last_name = last
        user.email = f"{username}@example.com"
        user.is_superuser = is_superuser
        user.is_staff = is_superuser
        user.set_password(password)
        user.save()
        return user

    def _attempt(self, rng, quiz, student, started_at, number, skill):
        attempt = services.build_attempt(quiz, student, started_at, number)
        questions = {
            q.pk: q for q in Question.objects.filter(pk__in=attempt.question_order).prefetch_related("options")
        }
        for question_id in attempt.question_order:
            question = questions[question_id]
            chance = max(0.05, min(0.98, skill * TOPIC_STRENGTH[question.topic]))
            roll = rng.random()
            if roll < 0.08:
                continue  # left unanswered
            options = list(question.options.all())
            correct = [o for o in options if o.is_correct][0]
            if rng.random() < chance:
                chosen = correct
            else:
                chosen = rng.choice([o for o in options if not o.is_correct])
            Answer.objects.create(attempt=attempt, question=question, selected_option=chosen)

        limit_seconds = quiz.time_limit_minutes * 60
        duration = rng.randint(int(limit_seconds * 0.3), int(limit_seconds * 0.9))
        services.finalize_attempt(attempt, submitted_at=started_at + timedelta(seconds=duration))
        return attempt
