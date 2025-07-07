from django.test import TestCase
from django.urls import reverse

from .models import Question, Choice


class PollsIndexViewTests(TestCase):
    def test_no_questions(self):
        response = self.client.get(reverse('polls:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No polls are available.')
        self.assertQuerySetEqual(response.context['latest_question_list'], [])

    def test_question_display(self):
        question = Question.objects.create(question_text='Who?', pub_date='2024-01-01T00:00')
        response = self.client.get(reverse('polls:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, question.question_text)
        self.assertQuerySetEqual(
            response.context['latest_question_list'],
            [question],
            transform=lambda x: x,
        )
