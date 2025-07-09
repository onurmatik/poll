from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0012_alter_question_uuid"),
    ]

    operations = [
        migrations.AddField(
            model_name="openaibatch",
            name="data",
            field=models.JSONField(default=dict),
        ),
        migrations.RemoveField(
            model_name="openaibatch",
            name="batch_id",
        ),
        migrations.RemoveField(
            model_name="openaibatch",
            name="status",
        ),
        migrations.RemoveField(
            model_name="openaibatch",
            name="errors",
        ),
        migrations.RemoveField(
            model_name="openaibatch",
            name="error_file_id",
        ),
        migrations.RemoveField(
            model_name="openaibatch",
            name="output_file_id",
        ),
    ]
