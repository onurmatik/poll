# Generated by Django 5.2.4 on 2025-07-08 18:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0006_alter_openaibatch_errors'),
    ]

    operations = [
        migrations.AlterField(
            model_name='openaibatch',
            name='errors',
            field=models.TextField(blank=True, null=True),
        ),
    ]
