from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponse
import csv
import json

from .models import Question, Answer, OpenAIBatch


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["uuid", "text", "created_by", "tags", "created_at"]
    actions = [
        'submit_openai_batch',
    ]

    def submit_openai_batch(self, request, queryset):
        for question in queryset:
            question.submit_batches()
        messages.success(request, f"Batches submitted successfully")
    submit_openai_batch.short_description = "Submit OpenAI batches"


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ["question__text", "context", "choices", "choice", "confidence", "run_id"]
    search_fields = ["run_id", "question__text"]

    actions = [
        "download_csv",
    ]

    class ConfidenceFilter(admin.SimpleListFilter):
        title = "confidence"
        parameter_name = "min_confidence"

        def lookups(self, request, model_admin):
            return [
                ("0.75", ">= 0.75"),
                ("0.9", ">= 0.9"),
                ("0.95", ">= 0.95"),
            ]

        def queryset(self, request, queryset):
            if self.value():
                try:
                    return queryset.filter(confidence__gte=float(self.value()))
                except (TypeError, ValueError):
                    return queryset
            return queryset

    list_filter = [ConfidenceFilter]

    def download_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=answers.csv"
        writer = csv.writer(response)
        writer.writerow(["question", "context", "choices", "choice", "confidence", "run_id"])
        for answer in queryset:
            writer.writerow([
                answer.question.text,
                json.dumps(answer.context, ensure_ascii=False),
                json.dumps(answer.choices, ensure_ascii=False),
                answer.choice,
                answer.confidence,
                answer.run_id,
            ])
        return response
    download_csv.short_description = "Download selected answers as CSV"


@admin.register(OpenAIBatch)
class OpenAIBatchAdmin(admin.ModelAdmin):
    list_display = ["batch_id", "status", "run_id", "created_at", "updated_at"]
    actions = [
        'update_status',
        'retrieve_results'
    ]

    def update_status(self, request, queryset):
        for batch in queryset:
            batch.update_status()
        messages.success(request, f"Batch statuses updated successfully")
    update_status.short_description = "Update batch statuses"

    def retrieve_results(self, request, queryset):
        for batch in queryset:
            batch.retrieve_results()
        messages.success(request, f"Batch results retrieved successfully")
    retrieve_results.short_description = "Retrieve batch results"
