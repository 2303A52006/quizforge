# QuizForge: presentation outline and viva preparation

## 7-slide PPT outline

1. **Title and problem**: QuizForge, your name, guide, department. Problem: paper tests and Google Forms are marked by hand,
   results are slow, and teachers cannot see which topics students are weak at.
2. **Solution and roles**: build a timed quiz, auto-mark it, show weak topics. Teacher (created by admin) vs student (self-registers).
   Screenshot of the home page and the quiz list (Open / Upcoming / Closed).
3. **Features (the 13)**: grouped as Accounts, Quiz builder (draft/publish, dates, shuffle, negative marking, attempts, duplicate),
   Taking a quiz (timer, autosave), Results (marking, review, leaderboard), Teacher tools (analytics, CSV).
4. **Architecture and tech stack**: Django MVT, SQLite, Bootstrap 5, Chart.js, plain JavaScript, gunicorn + whitenoise.
   Diagram: Browser > Django views > services.py (business logic) > models/SQLite. Five models: Quiz, Question, Option, Attempt, Answer.
5. **Key design decisions**: server-side clock and deadline (browser timer only for display), correct answers never sent before submit,
   shuffle order stored per attempt as option IDs, best-attempt rule, permissions checked in every view, CSRF and password hashing.
6. **Demo**: teacher builds and publishes a quiz; student takes it (timer, refresh keeps answers, auto-submit); result review;
   analytics chart showing DBMS as the weak topic; CSV export.
7. **Testing, deployment, future work**: 80+ automated tests (scoring, timer, attempts, shuffle, permissions);
   deployed on PythonAnywhere. Future work: question bank, classes, multi-select questions, email password reset, PostgreSQL.

## 12 likely viva questions with short answers

1. **Why Django?**
   It includes authentication, an ORM, forms, CSRF protection, an admin panel and a test framework, so a small team can build a secure app quickly.

2. **How do you stop a student cheating the timer by changing the browser clock?**
   The server saves `started_at` and a `deadline` in the Attempt. The JavaScript countdown is only for display.
   Autosave and submit are checked against the server deadline (plus a 5-second network grace), and late answers are ignored.

3. **How does auto-submit work?**
   When the countdown reaches zero the JavaScript submits the form. If the browser is closed, the server still finalises the attempt the next time it is
   touched (`finalize_expired`) using the answers that were autosaved, marking it at its deadline.

4. **How do answers survive a refresh?**
   Each click sends the answer to the server with `fetch`, which stores it in the Answer table. When the page is loaded again the server pre-ticks the saved options.

5. **How do you keep correct answers secret?**
   The quiz page is built from dictionaries that contain only the option id and text. `is_correct` and the explanation are only read when
   building the result page after the attempt is submitted.

6. **How does shuffling work and why is it stable?**
   When an attempt starts, the shuffled list of question IDs and a dictionary of option IDs per question are generated once and stored as JSON on the Attempt.
   Every page load reads that stored order. Marking compares option IDs, never positions.

7. **How is negative marking calculated?**
   `score = correct - wrong x penalty`, unanswered questions are ignored, and the result is never below 0 (`max(0, score)`). Decimals are used to avoid float errors.

8. **How is the "best attempt" chosen?**
   Highest score wins; ties go to the shorter time taken, then the earlier attempt. The leaderboard and analytics use only each student's best attempt.

9. **How do you enforce open and close dates and the attempt limit?**
   In `check_can_start` on the server: the quiz must be published, now must be between `opens_at` and `closes_at`, and the number of existing attempts
   must be below `max_attempts`. The deadline is `min(start + time limit, closes_at)`. Hiding the button is not relied on.

10. **How are roles and permissions handled?**
    A teacher is a user in the "Teacher" group; students are other non-superusers. Decorators `teacher_required` and `student_required` guard every view
    (login redirect or 403). Teachers fetch quizzes with `get_object_or_404(Quiz, pk=..., teacher=request.user)`, so other teachers' quizzes give 404.

11. **How are the analytics calculated?**
    From each student's best attempt: average, highest, lowest and pass rate from stored scores; score bands in 10 buckets; per-question percentage correct
    by counting correct Answer rows; topics by summing correct answers per topic tag. Topics below 50% are flagged weak. Chart.js draws the charts from JSON.

12. **What security measures did you use and how did you test?**
    PBKDF2 password hashing, CSRF tokens on every POST, secrets from environment variables, role/ownership checks, CSV formula-injection protection,
    and `ALLOWED_HOSTS` with secure cookies in production. Automated tests cover scoring, timing, attempt limits, shuffle stability and permissions (`python manage.py test`).
