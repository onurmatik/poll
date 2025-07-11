from django.test import TestCase
import json

from unittest.mock import Mock, patch

from django.urls import reverse
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
import csv
import uuid

from .models import Question, OpenAIBatch, Answer
from .admin import AnswerAdmin


class QuestionModelTests(TestCase):
    def test_render_all_questions(self):
        q = Question.objects.create(
            text="Where would a person move?",
            context={"gender": ["man", "woman"]},
        )
        expected = [
            ("Where would a person move?", {"gender": "man"}),
            ("Where would a person move?", {"gender": "woman"}),
        ]
        self.assertEqual(q.render_all_questions(), expected)

    def test_choice_pairs_deduplicated(self):
        q = Question.objects.create(
            text="dummy",
            choices=["A", "A", "B"],
        )
        self.assertEqual(q.choice_pairs(), [{"A": "A", "B": "B"}])

    def test_get_openai_batches_contains_response_format(self):
        q = Question.objects.create(text="q", choices=["A", "B"])
        batches = q.get_openai_batches()
        self.assertEqual(len(batches), 1)
        line = batches[0].splitlines()[0]
        payload = json.loads(line)
        response_format = payload["body"]["response_format"]
        schema_props = response_format["json_schema"]["schema"]["properties"]
        self.assertEqual(schema_props["answer"]["enum"], ["A", "B"])
        self.assertIn("confidence", schema_props)
        self.assertEqual(schema_props["confidence"]["type"], "number")

    def test_submit_batches_assigns_single_run_id(self):
        q = Question.objects.create(text="q", choices=["A", "B"])
        mock_client = Mock()
        mock_client.files.create.return_value = Mock(id="file_1")
        mock_client.batches.create.return_value = Mock(model_dump=Mock(return_value={"id": "batch_1"}))

        with patch("poll.main.models.openai.OpenAI", return_value=mock_client):
            with patch.object(Question, "get_openai_batches", return_value=["d1", "d2"]):
                q.submit_batches()

        batches = list(OpenAIBatch.objects.filter(question=q))
        self.assertEqual(len(batches), 2)
        run_ids = {b.run_id for b in batches}
        self.assertEqual(len(run_ids), 1)

    def test_latest_answers_returns_most_recent_batch(self):
        q = Question.objects.create(text="q", choices=["A", "B"])
        older = OpenAIBatch.objects.create(question=q, run_id=uuid.uuid4(), data={"id": "b1"})
        Answer.objects.create(question=q, run_id=older.run_id, context={}, choices={"A": "A", "B": "B"}, choice="A")

        newer = OpenAIBatch.objects.create(question=q, run_id=uuid.uuid4(), data={"id": "b2"})
        latest_answer = Answer.objects.create(question=q, run_id=newer.run_id, context={}, choices={"A": "A", "B": "B"}, choice="B")

        answers = list(q.latest_answers())
        self.assertEqual(answers, [latest_answer])



class OpenAIBatchModelTests(TestCase):
    def test_retrieve_results_creates_answers(self):
        q = Question.objects.create(
            text="Where would a person prefer to move?",
            context={"country": ["Turkey"], "gender": ["man"]},
            choices=["Turkey", "Mexico"],
        )

        batch = OpenAIBatch.objects.create(
            question=q,
            data={"id": "batch_1", "status": "completed", "output_file_id": "file_123"},
        )

        result_line = json.dumps({
            "id": "batch_req_1",
            "custom_id": "q1-Turkey-man-Turkey-Mexico",
            "response": {
                "status_code": 200,
                "body": {
                    "choices": [{
                        "message": {"content": "{\"answer\":\"A\",\"confidence\":0.75}"}
                    }]
                }
            },
        })

        mock_client = Mock()
        mock_client.files.content.return_value = Mock(text=result_line + "\n")

        with patch("poll.main.models.openai.OpenAI", return_value=mock_client):
            results = batch.retrieve_results()

        self.assertEqual(len(results), 1)
        self.assertEqual(Answer.objects.count(), 1)
        answer = Answer.objects.first()
        self.assertEqual(answer.question, q)
        self.assertEqual(answer.run_id, batch.run_id)
        self.assertEqual(answer.context, {"country": "Turkey", "gender": "man"})
        self.assertEqual(answer.choices, {"A": "Turkey", "B": "Mexico"})
        self.assertEqual(answer.choice, "A")
        self.assertAlmostEqual(answer.confidence, 0.75)


class QuestionDetailViewTests(TestCase):
    def test_question_detail_view(self):
        q = Question.objects.create(text="example", choices=["A", "B"])
        batch = OpenAIBatch.objects.create(question=q, run_id=uuid.uuid4(), data={"id": "b1"})
        a = Answer.objects.create(
            question=q,
            run_id=batch.run_id,
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
        self.assertTrue(response.context["has_answers"])
        self.assertContains(response, "Download CSV")
        self.assertContains(response, "preferenceChart")
        self.assertContains(response, "eloChart")

    def test_question_answers_csv_view(self):
        q = Question.objects.create(text="q", choices=["A", "B"])
        batch = OpenAIBatch.objects.create(question=q, run_id=uuid.uuid4(), data={"id": "b1"})
        a = Answer.objects.create(
            question=q,
            run_id=batch.run_id,
            context={},
            choices={"A": "A", "B": "B"},
            choice="A",
            confidence=0.9,
        )

        url = reverse("polls:question_answers_csv", args=[q.uuid])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        rows = list(csv.reader(content.splitlines()))
        self.assertEqual(rows[0], ["question", "context", "choices", "choice", "confidence", "run_id"])
        self.assertEqual(rows[1][0], q.text)


class AnswerAdminTests(TestCase):
    def setUp(self):
        self.admin_site = AdminSite()
        self.factory = RequestFactory()

    def test_download_csv_action(self):
        q = Question.objects.create(text="q", choices=["A", "B"])
        a = Answer.objects.create(
            question=q,
            context={},
            choices={"A": "A", "B": "B"},
            choice="A",
            confidence=0.8,
        )

        ma = AnswerAdmin(Answer, self.admin_site)
        response = ma.download_csv(None, Answer.objects.filter(pk=a.pk))
        content = response.content.decode()
        rows = list(csv.reader(content.splitlines()))
        self.assertEqual(rows[0], ["question", "context", "choices", "choice", "confidence", "run_id"])
        self.assertEqual(rows[1][0], q.text)
        self.assertEqual(float(rows[1][4]), 0.8)

    def test_confidence_filter_queryset(self):
        q = Question.objects.create(text="q", choices=["A", "B"])
        high = Answer.objects.create(question=q, context={}, choices={"A": "A", "B": "B"}, choice="A", confidence=0.8)
        low = Answer.objects.create(question=q, context={}, choices={"A": "A", "B": "B"}, choice="A", confidence=0.5)

        ma = AnswerAdmin(Answer, self.admin_site)
        request = self.factory.get("/", {"min_confidence": "0.75"})
        filt = ma.ConfidenceFilter(request, request.GET.copy(), Answer, ma)
        qs = filt.queryset(request, Answer.objects.all())
        self.assertIn(high, list(qs))
        self.assertNotIn(low, list(qs))

class ChartAPITests(TestCase):
    def setUp(self):
        self.question = Question.objects.create(
            text="q", choices=["X", "Y"], context={"gender": ["man", "woman"]}
        )
        self.batch = OpenAIBatch.objects.create(question=self.question, data={"id": "b1"})
        Answer.objects.create(
            question=self.question,
            run_id=self.batch.run_id,
            context={"gender": "man"},
            choices={"A": "X", "B": "Y"},
            choice="A",
        )
        Answer.objects.create(
            question=self.question,
            run_id=self.batch.run_id,
            context={"gender": "woman"},
            choices={"A": "X", "B": "Y"},
            choice="B",
        )

    def test_preference_counts_endpoint(self):
        url = f"/api/charts/questions/{self.question.uuid}/preference-counts"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["counts"], {"X": 1, "Y": 1})

    def test_preference_counts_endpoint_filter(self):
        url = f"/api/charts/questions/{self.question.uuid}/preference-counts?gender=man"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["counts"], {"X": 1})

    def test_preference_heatmap_endpoint(self):
        url = f"/api/charts/questions/{self.question.uuid}/preference-heatmap"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["choices"], ["X", "Y"])
        self.assertEqual(data["matrix"][0][1], 1)
        self.assertEqual(data["matrix"][1][0], 1)

    def test_preference_heatmap_endpoint_filter(self):
        url = f"/api/charts/questions/{self.question.uuid}/preference-heatmap?gender=man"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["matrix"][0][1], 1)
        self.assertEqual(data["matrix"][1][0], 0)

    def test_elo_ratings_endpoint(self):
        url = f"/api/charts/questions/{self.question.uuid}/elo-ratings"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        rankings = data["rankings"]
        self.assertEqual(len(rankings), 2)
        # Winner order may depend on algorithm; just check keys
        self.assertEqual({r["choice"] for r in rankings}, {"X", "Y"})
