from django.core.management.base import BaseCommand
from poll.main.models import OpenAIBatch, Answer


class Command(BaseCommand):
    """Update OpenAI batch statuses and retrieve results if completed."""

    help = "Update OpenAI batch statuses and fetch results if completed"

    def handle(self, *args, **options):
        for batch in OpenAIBatch.objects.all():
            self.stdout.write(f"Updating batch {batch.batch_id}...")
            batch.update_status()

            if batch.status == "completed":
                if not Answer.objects.filter(run_id=batch.run_id, question=batch.question).exists():
                    self.stdout.write(f"Retrieving results for batch {batch.batch_id}...")
                    batch.retrieve_results()
        self.stdout.write(self.style.SUCCESS("Batch update complete"))
