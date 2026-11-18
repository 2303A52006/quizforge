from django.urls import path

from quizzes import views_student, views_teacher

app_name = "quizzes"

urlpatterns = [
    # ----- teacher pages
    path("teach/", views_teacher.teacher_list, name="teacher_list"),
    path("teach/new/", views_teacher.quiz_create, name="create"),
    path("teach/<int:pk>/", views_teacher.quiz_manage, name="manage"),
    path("teach/<int:pk>/edit/", views_teacher.quiz_edit, name="edit"),
    path("teach/<int:pk>/publish/", views_teacher.quiz_publish, name="publish"),
    path("teach/<int:pk>/duplicate/", views_teacher.quiz_duplicate, name="duplicate"),
    path("teach/<int:pk>/questions/add/", views_teacher.question_add, name="question_add"),
    path(
        "teach/<int:pk>/questions/<int:question_id>/edit/",
        views_teacher.question_edit,
        name="question_edit",
    ),
    path(
        "teach/<int:pk>/questions/<int:question_id>/delete/",
        views_teacher.question_delete,
        name="question_delete",
    ),
    path("teach/<int:pk>/analytics/", views_teacher.quiz_analytics, name="analytics"),
    path("teach/<int:pk>/export.csv", views_teacher.export_csv, name="export_csv"),
    # ----- shared (teacher owner or student who finished an attempt)
    path("quiz/<int:pk>/leaderboard/", views_teacher.leaderboard, name="leaderboard"),
    # ----- student pages
    path("quizzes/", views_student.student_list, name="student_list"),
    path("quiz/<int:pk>/", views_student.quiz_detail, name="detail"),
    path("quiz/<int:pk>/start/", views_student.start_quiz, name="start"),
    path("attempt/<int:attempt_id>/", views_student.take_quiz, name="take"),
    path("attempt/<int:attempt_id>/answer/", views_student.save_answer, name="save_answer"),
    path("attempt/<int:attempt_id>/submit/", views_student.submit_quiz, name="submit"),
    path("attempt/<int:attempt_id>/result/", views_student.result, name="result"),
]
