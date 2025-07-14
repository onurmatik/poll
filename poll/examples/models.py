from django.db import models


class Example(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField()
    questions = models.ManyToManyField('main.Question', related_name='examples')

    def __str__(self):
        return self.title
