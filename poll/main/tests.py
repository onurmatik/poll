from django.test import TestCase

from .models import Question


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
        self.assertEqual(q.choice_pairs(), [("A", "B")])
