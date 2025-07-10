from django.contrib import admin
from django.contrib import messages

from .models import Question, Answer, OpenAIBatch


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["uuid", "text", "created_at"]
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
