from django.test import TestCase
import json

from unittest.mock import Mock, patch

from django.urls import reverse

from .models import Question, OpenAIBatch, Answer


class QuestionModelTests(TestCase):
    def test_render_all_questions(self):
        q = Question.objects.create(
            template="Where would a {{ gender }} move?",
            context={"gender": ["man", "woman"]},
        )
        expected = [
            ("Where would a man move?", {"gender": "man"}),
            ("Where would a woman move?", {"gender": "woman"}),
        ]
        self.assertEqual(q.render_all_questions(), expected)

    def test_choice_pairs_deduplicated(self):
        q = Question.objects.create(
            template="dummy",
            choices=["A", "A", "B"],
        )
        self.assertEqual(q.choice_pairs(), [{"A": "A", "B": "B"}])

    def test_get_openai_batches_contains_response_format(self):
        q = Question.objects.create(template="q", choices=["A", "B"])
        batches = q.get_openai_batches()
        self.assertEqual(len(batches), 1)
        line = batches[0].splitlines()[0]
        payload = json.loads(line)
        response_format = payload["body"]["response_format"]
        schema_props = response_format["json_schema"]["schema"]["properties"]
        self.assertEqual(schema_props["answer"]["enum"], ["A", "B"])
        self.assertIn("confidence", schema_props)
        self.assertEqual(schema_props["confidence"]["type"], "number")


class OpenAIBatchModelTests(TestCase):
    def test_retrieve_results(self):
        q = Question.objects.create(template="dummy", choices=["A", "B"])
        batch = OpenAIBatch.objects.create(
            question=q,
            data={"id": "batch_1", "status": "completed", "output_file_id": "file_123"},
        )

        fake_content = (
            '{"id": "batch_req_1", "custom_id": "c1"}\n'
            '{"id": "batch_req_2", "custom_id": "c2"}\n'
        )

        mock_client = Mock()
        mock_client.files.content.return_value = Mock(text=fake_content)

        with patch("poll.main.models.openai.OpenAI", return_value=mock_client):
            results = batch.retrieve_results()

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["custom_id"], "c1")


class QuestionDetailViewTests(TestCase):
    def test_question_detail_view(self):
        q = Question.objects.create(template="example", choices=["A", "B"])
        Answer.objects.create(
            question=q,
            context={},
            choices={"A": "A", "B": "B"},
            choice="A",
        )

        url = reverse("polls:question_detail", args=[q.uuid])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["question"], q)
        self.assertEqual(response.context["num_variations"], 1)
        self.assertEqual(response.context["total_queries"], 1)
