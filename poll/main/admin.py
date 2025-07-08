from django.contrib import admin
from django.http import HttpResponse
import csv
import json
import tempfile
import openai
from django.contrib import messages

from .models import Question, Answer, OpenAIBatch


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


@admin.action(description="Download OpenAI batch JSONL")
def download_openai_batch_jsonl(modeladmin, request, queryset):
    """Return a JSONL file compatible with the OpenAI Batch API."""
    response = HttpResponse(content_type="application/json")
    response["Content-Disposition"] = "attachment; filename=openai_batch.jsonl"

    for question in queryset:
        rendered_questions = question.render_all_questions()
        pairs = question.choice_pairs()
        for rendered, ctx in rendered_questions:
            for pair in pairs:
                prompt = (
                    f"{rendered} (A) {pair['A']} (B) {pair['B']}\n"
                    "Please answer with 'A' or 'B'."
                )
                body = {
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": prompt}],
                }
                batch_obj = {
                    "custom_id": f"q{question.pk}-{pair['A']}-{pair['B']}",
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": body,
                }
                response.write(json.dumps(batch_obj, ensure_ascii=False) + "\n")

    return response


@admin.action(description="Submit OpenAI batch")
def submit_openai_batch(modeladmin, request, queryset):
    """Upload JSONL batch to OpenAI and store batch ID."""
    client = openai.OpenAI()
    with tempfile.NamedTemporaryFile("w+", suffix=".jsonl") as tmp:
        for question in queryset:
            rendered_questions = question.render_all_questions()
            pairs = question.choice_pairs()
            for rendered, ctx in rendered_questions:
                for pair in pairs:
                    prompt = (
                        f"{rendered} (A) {pair['A']} (B) {pair['B']}\n"
                        "Please answer with 'A' or 'B'."
                    )
                    body = {
                        "model": "gpt-3.5-turbo",
                        "messages": [{"role": "user", "content": prompt}],
                    }
                    batch_obj = {
                        "custom_id": f"q{question.pk}-{pair['A']}-{pair['B']}",
                        "method": "POST",
                        "url": "/v1/chat/completions",
                        "body": body,
                    }
                    tmp.write(json.dumps(batch_obj, ensure_ascii=False) + "\n")

        tmp.flush()
        tmp.seek(0)
        file_obj = client.files.create(file=tmp, purpose="batch")
        batch = client.batches.create(
            completion_window="24h",
            endpoint="/v1/chat/completions",
            input_file_id=file_obj.id,
        )

    obatch = OpenAIBatch.objects.create(batch_id=batch.id)
    obatch.questions.set(queryset)
    messages.success(request, f"Created OpenAI batch {batch.id}")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["template", "created_at"]
    actions = [
        download_batch_prompt_csv,
        download_openai_batch_jsonl,
        submit_openai_batch,
    ]


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ["question", "choice"]


@admin.register(OpenAIBatch)
class OpenAIBatchAdmin(admin.ModelAdmin):
    list_display = ["batch_id", "created_at"]
    filter_horizontal = ["questions"]
