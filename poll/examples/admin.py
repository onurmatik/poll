from django.contrib import admin

from .models import Example


@admin.register(Example)
class ExampleAdmin(admin.ModelAdmin):
    """Admin interface for Example objects."""

    list_display = ["title", "short_description", "question_count"]
    search_fields = ["title", "description"]
    filter_horizontal = ["questions"]

    def short_description(self, obj):
        """Return a shortened preview of the description."""
        return obj.description[:50]

    short_description.short_description = "Description"

    def question_count(self, obj):
        """Return the number of questions linked to this example."""
        return obj.questions.count()

    question_count.short_description = "# Questions"

