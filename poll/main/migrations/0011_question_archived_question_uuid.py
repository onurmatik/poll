# Generated by Django 5.2.4 on 2025-07-09 06:59

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0010_answer_confidence'),
    ]

    operations = [
        migrations.AddField(
            model_name='question',
            name='archived',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='question',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
    ]
