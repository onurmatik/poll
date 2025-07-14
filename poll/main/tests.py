from django.test import TestCase
from django.contrib.auth.models import User
import json

from unittest.mock import Mock, patch

from django.urls import reverse
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
import csv
import uuid
from django.core.management import call_command

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


class QuestionResultsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("user", password="pass")
        self.client.force_login(self.user)

    def test_question_results_view(self):
        q = Question.objects.create(text="example", choices=["A", "B"], user=self.user)
        batch = OpenAIBatch.objects.create(question=q, run_id=uuid.uuid4(), data={"id": "b1"})
        a = Answer.objects.create(
            question=q,
            run_id=batch.run_id,
            context={},
            choices={"A": "A", "B": "B"},
            choice="A",
        )

        q.status = "completed"
        q.save()
        url = reverse("polls:question_results", args=[q.uuid])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["question"], q)
        self.assertEqual(response.context["num_variations"], 1)
        self.assertEqual(response.context["total_queries"], 1)
        self.assertTrue(response.context["has_answers"])
        self.assertContains(response, "Download CSV")
        self.assertContains(response, "preferenceChart")
        self.assertContains(response, "eloChart")
        self.assertContains(response, "confidenceChart")
        self.assertContains(response, "sankeyChart")

    def test_question_answers_csv_view(self):
        q = Question.objects.create(text="q", choices=["A", "B"], user=self.user)
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


class QuestionListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("user", password="pass")
        self.client.force_login(self.user)

    def test_question_list_view(self):
        q1 = Question.objects.create(text="Where?", choices=["A", "B"], user=self.user)
        q2 = Question.objects.create(text="Archived?", choices=["A", "B"], archived=True, user=self.user)

        url = reverse("polls:question_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, q1.text)
        self.assertContains(response, q2.text)

    def test_question_list_view_shows_status(self):
        q1 = Question.objects.create(text="Where?", choices=["A", "B"], user=self.user)
        OpenAIBatch.objects.create(question=q1, data={"id": "b1", "status": "running"})
        q1.status = "running"
        q1.save()
        q2 = Question.objects.create(text="Another?", choices=["A", "B"], user=self.user)

        url = reverse("polls:question_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Running")
        self.assertContains(response, "Draft")

    def test_draft_question_links_to_edit(self):
        q = Question.objects.create(text="Edit?", choices=["A", "B"], user=self.user)
        url = reverse("polls:question_list")
        response = self.client.get(url)
        edit_url = f"{reverse('polls:question_create')}?uuid={q.uuid}"
        self.assertContains(response, f'href="{edit_url}"')


class QuestionCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("user", password="pass")
        self.client.force_login(self.user)

    def test_get_create_view(self):
        url = reverse("polls:question_create")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_post_create_view(self):
        url = reverse("polls:question_create")
        data = {
            "text": "Where to go?",
            "context": json.dumps({"gender": ["man", "woman"]}),
            "choices": "Turkey\nMexico",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/review/", response["Location"])
        q = Question.objects.first()
        self.assertIsNotNone(q)
        self.assertEqual(q.text, "Where to go?")
        self.assertEqual(q.status, "draft")

    def test_post_review_submits_batches(self):
        q = Question.objects.create(text="T?", choices=["A", "B"], user=self.user)
        url = reverse("polls:question_review", args=[q.uuid])
        with patch.object(Question, "submit_batches") as sb:
            response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("polls:question_list"))
        sb.assert_called_once()
        q.refresh_from_db()
        self.assertEqual(q.status, "queued")


class QuestionCloneViewTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user("u1", password="pass")
        self.user2 = User.objects.create_user("u2", password="pass")
        self.client.force_login(self.user2)

    def test_clone_creates_new_question_for_user(self):
        original = Question.objects.create(text="q", choices=["A", "B"], user=self.user1)
        url = reverse("polls:question_clone", args=[original.uuid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        new_q = Question.objects.exclude(pk=original.pk).first()
        self.assertIsNotNone(new_q)
        self.assertEqual(new_q.text, original.text)
        self.assertEqual(new_q.user, self.user2)
        self.assertIn(str(new_q.uuid), response["Location"])


class QuestionDeleteViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("user", password="pass")
        self.client.force_login(self.user)

    def test_delete_draft_question(self):
        q = Question.objects.create(text="q", choices=["A", "B"], user=self.user)
        url = reverse("polls:question_delete", args=[q.uuid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Question.objects.count(), 0)


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
            confidence=0.8,
        )
        Answer.objects.create(
            question=self.question,
            run_id=self.batch.run_id,
            context={"gender": "woman"},
            choices={"A": "X", "B": "Y"},
            choice="B",
            confidence=0.6,
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

    def test_confidence_distribution_endpoint(self):
        url = f"/api/charts/questions/{self.question.uuid}/confidence-distribution"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["counts"][8], 1)
        self.assertEqual(data["counts"][6], 1)

    def test_preference_flows_endpoint(self):
        url = f"/api/charts/questions/{self.question.uuid}/preference-flows"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        labels = data["labels"]
        links = data["links"]
        self.assertIn("X", labels)
        self.assertIn("Y", labels)
        self.assertEqual(len(links), 2)


class QuestionAPITests(TestCase):
    def test_create_question(self):
        payload = {
            "text": "Where to travel?",
            "context": {"gender": ["man", "woman"]},
            "choices": ["Turkey", "Mexico"],
        }

        response = self.client.post(
            "/api/questions/",
            json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("uuid", data)
        q = Question.objects.get(uuid=data["uuid"])
        self.assertEqual(q.text, payload["text"])
        self.assertEqual(q.context, payload["context"])
        self.assertEqual(q.choices, payload["choices"])


class BatchAPITests(TestCase):
    def test_update_status_endpoint(self):
        q = Question.objects.create(text="q", choices=["A", "B"])
        batch = OpenAIBatch.objects.create(question=q, data={"id": "b1", "status": "running"})

        mock_client = Mock()
        mock_client.batches.retrieve.return_value = Mock(
            model_dump=Mock(return_value={"id": "b1", "status": "completed"})
        )

        with patch("poll.main.models.openai.OpenAI", return_value=mock_client):
            url = f"/api/batches/{batch.batch_id}/update-status"
            response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "completed")

        batch.refresh_from_db()
        self.assertEqual(batch.status, "completed")


class ManagementCommandTests(TestCase):
    def test_update_openai_batches_command(self):
        q = Question.objects.create(text="q", choices=["A", "B"])
        batch = OpenAIBatch.objects.create(
            question=q,
            data={"id": "batch_1", "status": "running"},
        )

        result_line = json.dumps({
            "id": "batch_req_1",
            "custom_id": f"q{q.pk}-A-B",
            "response": {
                "status_code": 200,
                "body": {
                    "choices": [
                        {"message": {"content": "{\"answer\":\"A\",\"confidence\":0.9}"}}
                    ]
                },
            },
        })

        mock_client = Mock()
        mock_client.batches.retrieve.return_value = Mock(
            model_dump=Mock(return_value={"id": batch.batch_id, "status": "completed", "output_file_id": "file_1"})
        )
        mock_client.files.content.return_value = Mock(text=result_line + "\n")

        with patch("poll.main.models.openai.OpenAI", return_value=mock_client):
            call_command("update_openai_batches")

        batch.refresh_from_db()
        self.assertEqual(batch.status, "completed")
        self.assertEqual(Answer.objects.count(), 1)
