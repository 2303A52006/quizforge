from django import forms
from django.db import transaction
from django.db.models import Max

from accounts.forms import BootstrapMixin
from quizzes.models import Option, Question, Quiz

DATETIME_WIDGET_FORMAT = "%Y-%m-%dT%H:%M"


def _datetime_widget():
    return forms.DateTimeInput(format=DATETIME_WIDGET_FORMAT, attrs={"type": "datetime-local"})


class QuizForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Quiz
        fields = [
            "title",
            "description",
            "time_limit_minutes",
            "pass_mark",
            "max_attempts",
            "negative_marking",
            "shuffle_questions",
            "shuffle_options",
            "opens_at",
            "closes_at",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "opens_at": _datetime_widget(),
            "closes_at": _datetime_widget(),
        }
        labels = {
            "time_limit_minutes": "Time limit (minutes)",
            "pass_mark": "Pass mark (%)",
            "max_attempts": "Maximum attempts per student",
            "negative_marking": "Penalty per wrong answer (marks)",
            "shuffle_questions": "Shuffle the order of questions",
            "shuffle_options": "Shuffle the order of options",
            "opens_at": "Opens at",
            "closes_at": "Closes at",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("opens_at", "closes_at"):
            self.fields[name].input_formats = [DATETIME_WIDGET_FORMAT, "%Y-%m-%d %H:%M"]

    def clean(self):
        cleaned = super().clean()
        opens, closes = cleaned.get("opens_at"), cleaned.get("closes_at")
        if opens and closes and closes <= opens:
            self.add_error("closes_at", "The close date must be after the open date.")
        return cleaned


class QuestionForm(BootstrapMixin, forms.Form):
    """One question with exactly four options and one correct answer."""

    text = forms.CharField(label="Question", widget=forms.Textarea(attrs={"rows": 3}))
    topic = forms.CharField(max_length=100, help_text="For example: Python Basics")
    option_1 = forms.CharField(label="Option A", max_length=500)
    option_2 = forms.CharField(label="Option B", max_length=500)
    option_3 = forms.CharField(label="Option C", max_length=500)
    option_4 = forms.CharField(label="Option D", max_length=500)
    correct = forms.ChoiceField(
        label="Correct answer",
        choices=[("1", "A"), ("2", "B"), ("3", "C"), ("4", "D")],
        widget=forms.RadioSelect,
        error_messages={"required": "Choose which option is correct."},
    )
    explanation = forms.CharField(
        required=False,
        label="Explanation (shown after submission)",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, question=None, **kwargs):
        self.question = question
        if question is not None:
            initial = {
                "text": question.text,
                "topic": question.topic,
                "explanation": question.explanation,
            }
            for index, option in enumerate(question.options.all(), start=1):
                initial[f"option_{index}"] = option.text
                if option.is_correct:
                    initial["correct"] = str(index)
            kwargs.setdefault("initial", initial)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        texts = [cleaned.get(f"option_{i}", "").strip().lower() for i in range(1, 5)]
        texts = [t for t in texts if t]
        if len(texts) == 4 and len(set(texts)) < 4:
            raise forms.ValidationError("The four options must all be different.")
        return cleaned

    @transaction.atomic
    def save(self, quiz):
        data = self.cleaned_data
        if self.question is None:
            position = (quiz.questions.aggregate(m=Max("position"))["m"] or 0) + 1
            question = Question.objects.create(
                quiz=quiz,
                text=data["text"],
                topic=data["topic"].strip(),
                explanation=data["explanation"],
                position=position,
            )
        else:
            question = self.question
            question.text = data["text"]
            question.topic = data["topic"].strip()
            question.explanation = data["explanation"]
            question.save()

        existing = list(question.options.all())
        for index in range(1, 5):
            text = data[f"option_{index}"].strip()
            if index <= len(existing):
                option = existing[index - 1]
                option.text = text
                option.is_correct = False  # clear first; the correct one is set below
                option.position = index
                option.save()
            else:
                Option.objects.create(question=question, text=text, is_correct=False, position=index)

        chosen = question.options.order_by("position", "id")[int(data["correct"]) - 1]
        question.options.filter(pk=chosen.pk).update(is_correct=True)
        return question
