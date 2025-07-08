from django.contrib import admin
from django.http import HttpResponse
import csv
import json

from .models import Question, Answer


@admin.action(description="Download batch prompt CSV")
def download_batch_prompt_csv(modeladmin, request, queryset):
    """Return a CSV with all question/answer combinations."""
    fieldnames = ["question_id", "question", "choice_a", "choice_b", "context"]
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=batch_prompts.csv"
    writer = csv.DictWriter(response, fieldnames=fieldnames)
    writer.writeheader()

    for question in queryset:
        rendered_questions = question.render_all_questions()
        pairs = question.choice_pairs()
        for rendered, ctx in rendered_questions:
            for pair in pairs:
                writer.writerow(
                    {
                        "question_id": question.pk,
                        "question": rendered,
                        "choice_a": pair["A"],
                        "choice_b": pair["B"],
                        "context": json.dumps(ctx, ensure_ascii=False),
                    }
                )

    return response


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["template", "created_at"]
    actions = [download_batch_prompt_csv]


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ["question", "choice"]
