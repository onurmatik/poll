# Generated by Django 5.2.4 on 2025-07-08 08:06

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Question',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('template', models.CharField(max_length=500)),
                ('context', models.JSONField(default=dict)),
                ('choices', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='Answer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('context', models.JSONField(default=dict)),
                ('choices', models.JSONField(default=list)),
                ('choice', models.CharField(max_length=500)),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.question')),
            ],
        ),
    ]
