# Generated by Django 5.2.4 on 2025-07-08 09:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="answer",
            name="choice",
            field=models.CharField(choices=[("A", "A"), ("B", "B")], max_length=1),
        ),
        migrations.AlterField(
            model_name="answer",
            name="choices",
            field=models.JSONField(default=dict),
        ),
    ]
