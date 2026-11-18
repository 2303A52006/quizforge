# QuizForge

An online quiz platform for a college department. Teachers build timed quizzes, the site marks them automatically,
and analytics show which topics the class is weak at.

**Stack:** Python 3.12+, Django 5.2, SQLite, Django templates, Bootstrap 5, Chart.js, plain JavaScript.
Deployment: gunicorn + whitenoise + environment variables.

> Bootstrap and Chart.js are loaded from the jsDelivr CDN, so the browser needs internet access.

---

## Assumptions

1. **Teacher = a user in the "Teacher" group.** The admin creates the user in `/admin/` and ticks the *Teacher* group
   (the group is created automatically by `migrate`). Anyone who registers on the site is a student.
2. **Pass mark is a percentage** (0-100). Every question is worth exactly 1 mark, so total marks = number of questions.
3. **Questions are locked once a student has attempted the quiz** (editing would corrupt marking). Use *Duplicate* to get an editable copy.
4. **Times use the Asia/Kolkata time zone** (change with `DJANGO_TIME_ZONE`). Final "Submit" requests arriving up to 5 seconds
   after the deadline are accepted (network delay); anything later is marked using only the answers that were autosaved before the deadline.
5. **SQLite database file**, because the brief says SQLite. Free hosts with a temporary disk will lose it on restart (see Deployment).

---

## Project folder tree

```
quizforge/
├── manage.py
├── requirements.txt
├── README.md
├── .gitignore
├── .env.example
├── docs/VIVA_AND_PPT.md
├── config/                      settings, root urls, wsgi/asgi
├── accounts/                    login, logout, registration, profile, roles
│   ├── permissions.py           is_teacher / is_student + decorators
│   ├── forms.py  views.py  urls.py  admin.py  apps.py  context_processors.py
├── quizzes/
│   ├── models.py                Quiz, Question, Option, Attempt, Answer
│   ├── services.py              deadlines, shuffle, marking, leaderboard, analytics, duplicate
│   ├── forms.py                 QuizForm, QuestionForm
│   ├── views_teacher.py         builder, publish, duplicate, analytics, CSV, leaderboard
│   ├── views_student.py         home, quiz list, start, take, autosave, submit, result
│   ├── urls.py  admin.py  apps.py
│   ├── management/commands/seed_demo.py
│   └── tests/                   scoring, timing, attempts, shuffle, permissions, features
├── templates/                   base, home, 403, 404, registration/, accounts/, quizzes/
└── static/                      css/app.css, js/take_quiz.js, js/analytics.js
```

---

## Run it on Windows (PowerShell, VS Code terminal)

Open the `quizforge` folder in VS Code, open a terminal (Ctrl + `) and run these in order:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py makemigrations quizzes
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Then open http://127.0.0.1:8000/

* If PowerShell says "running scripts is disabled", run
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` once in that terminal and activate again.
* The app label in `makemigrations quizzes` is required the first time, because the app has no migrations folder yet.
* If `python` is not found, try `py -3.12` instead of `python` for the first command only.
* Next time you only need: `.\venv\Scripts\Activate.ps1` then `python manage.py runserver`.

### Demo logins

| Role | Username | Password |
|---|---|---|
| Admin (`/admin/`) | `admin` | `Admin@12345` |
| Teacher | `teacher1` | `Teacher@12345` |
| Students | `student1` ... `student10` | `Student@12345` |

The seed creates 25 questions in 4 topics (Python Basics, Data Structures, DBMS, Operating Systems) split over 3 quizzes:
**Open** (10 questions, 2 attempts, shuffle on, -0.25 penalty), **Closed** (10 questions), **Upcoming** (5 questions),
with attempts from the students. `student10` has not attempted the open quiz, so use that login to take it live.
Running `seed_demo` again rebuilds the teacher's quizzes.

---

## Checklist: how to test each of the 13 features

| # | Feature | What to do | What you should see |
|---|---|---|---|
| 1 | Login, logout, registration | Click **Register**, create a student, log out (navbar button), log back in. | New student lands on the Quizzes page. Wrong password shows an error. |
| 2 | Quiz builder, draft/publish | Log in as `teacher1` > **New quiz**. Fill in the settings, save, **Add question** (4 options, tick the correct one, topic, explanation). Press **Publish**. | Quiz shows *Draft* until published. Publishing without questions or dates shows an error; with both it turns *Open/Upcoming*. |
| 3 | Open/close dates | As student open the **Upcoming** quiz and try to start it. Also see the three groups on the Quizzes page. | Cards are grouped Open / Upcoming / Closed. Upcoming and Closed quizzes show "has not opened yet" / "is closed" and no Start button (the server also refuses direct POSTs). |
| 4 | Timed quiz, autosave, auto-submit | As `student10` start the open quiz. Pick answers, press F5. Create a quiz with a 1-minute limit and wait. | Timer counts down; answers are still ticked after refresh; at 00:00 the quiz submits itself and the result page opens. |
| 5 | Multiple attempts | Finish the open quiz as `student10`, press **Try again**. After attempt 2 try again. | Attempt history lists #1, #2 with the best one badged; a 3rd attempt is refused ("used all 2 attempts"). |
| 6 | Shuffle | Open quiz has shuffle on. Start it, note the order, refresh. | Order differs between different attempts/students but never changes when you refresh the same attempt. |
| 7 | Negative marking | In the open quiz answer 2 right, 1 wrong, leave the rest blank. | Score = 2 - 0.25 = **1.75**; unanswered questions cost nothing; score never below 0. |
| 8 | Auto-marking and result page | Submit any attempt. | Score, percentage, PASSED/FAILED badge, each question reviewed with the correct answer highlighted and the explanation. |
| 9 | Analytics (Chart.js) | `teacher1` > quiz > **Analytics**. | Average, highest, lowest, pass rate, score distribution chart, % correct per question, topic chart. DBMS shows as a **weak topic** (red). |
| 10 | Leaderboard | Click **Leaderboard** on the quiz (teacher or a student who has finished it). | One row per student with their best attempt; ties ordered by shorter time. |
| 11 | CSV export | Quiz page > **Export results (CSV)**. Open in Excel. | One row per attempt with an "Attempt number" column. |
| 12 | Duplicate | Quiz page > **Duplicate**. | New draft "Copy of ..." with the same questions/options/settings and empty dates. |
| 13 | Profile | Click your name in the navbar. Change name/email, then change password. | Success messages; you stay logged in after the password change. |

Permission checks to try: log in as a student and open `/teach/` (403 page); log in as a teacher and open `/quizzes/` (403);
log out and open `/teach/` (redirect to login).

---

## Run the automated tests

```powershell
python manage.py test
```

Run one area only, for example `python manage.py test quizzes.tests.test_scoring`.
The tests cover scoring (including negative marking and the floor at 0), timer and close-date enforcement,
the attempt limit, shuffled-order stability, permissions, CSRF, duplicate, CSV export, registration and profile.

---

## Deployment (free hosts, limits checked in 2026 - verify on the host's pricing page before you rely on them)

Set these environment variables on any host (see `.env.example`):
`DJANGO_SECRET_KEY` (long random string), `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`.

Before deploying, commit the migrations you generated (`quizzes/migrations/`) and push the project to GitHub.
Generate a secret key with:
`python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"`

### Option A (recommended for a college demo): PythonAnywhere free "Beginner" account

Free tier: 1 web app at `yourname.pythonanywhere.com`, no custom domain, limited CPU, small disk,
and the app must be re-activated from the dashboard every few months. The disk is **persistent**, so SQLite works.

1. Sign up at pythonanywhere.com (free account) and open a **Bash console**.
2. `git clone <your-github-url> quizforge && cd quizforge`
3. `mkvirtualenv quizforge --python=python3.12` (use the newest 3.x they offer, at least 3.12) then `pip install -r requirements.txt`
4. `python manage.py migrate` and `python manage.py createsuperuser` (optional: `python manage.py seed_demo` for demo data)
5. `python manage.py collectstatic --noinput`
6. **Web** tab > *Add a new web app* > *Manual configuration* > same Python version.
7. Set **Virtualenv** to `/home/yourname/.virtualenvs/quizforge`.
8. Click the **WSGI configuration file** link, replace its content with:
   ```python
   import os, sys
   path = "/home/yourname/quizforge"
   if path not in sys.path:
       sys.path.insert(0, path)
   os.environ["DJANGO_SECRET_KEY"] = "paste-your-long-random-key"
   os.environ["DJANGO_DEBUG"] = "False"
   os.environ["DJANGO_ALLOWED_HOSTS"] = "yourname.pythonanywhere.com"
   os.environ["DJANGO_CSRF_TRUSTED_ORIGINS"] = "https://yourname.pythonanywhere.com"
   os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```
9. **Static files** section: URL `/static/` > directory `/home/yourname/quizforge/staticfiles`.
10. Press **Reload**. Visit your URL. Create teachers in `/admin/` (add the user to the *Teacher* group).

### Option B: Render free web service (demo only)

Free web services sleep after about 15 minutes without traffic (about a minute to wake) and the free disk is **temporary**:
the SQLite file is wiped on every restart/redeploy. Use it only for a short demo with seeded data.

1. Push to GitHub, create a Render account, **New > Web Service**, pick the repo, runtime **Python**.
2. Build command: `pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput && python manage.py seed_demo`
3. Start command: `gunicorn config.wsgi:application`
4. Environment: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://<your-service>.onrender.com`,
   `PYTHON_VERSION=3.12.8`. (`RENDER_EXTERNAL_HOSTNAME` is added to the allowed hosts automatically.)
5. The demo passwords are public in this README, so never keep `seed_demo` in a real deployment.

For anything real (data that must survive), use a paid persistent disk or switch `DATABASES` to PostgreSQL.

---

## Security notes

* Passwords use Django's built-in PBKDF2 hashing; CSRF protection is on for every POST (including the autosave request).
* Correct answers and explanations are only sent after submission (the quiz page uses id + text only).
* The server stores the start time and the deadline; the browser timer is cosmetic.
* Every teacher view checks the teacher role and ownership (other teachers' quizzes return 404); every student view checks the student role and attempt ownership.
* No secrets in code: `DJANGO_SECRET_KEY` comes from the environment (a local-only key file `.dev_secret_key` is generated for development and git-ignored).
* CSV export neutralises spreadsheet formula injection.

More: see `docs/VIVA_AND_PPT.md` for the 7-slide presentation outline and 12 viva questions.
