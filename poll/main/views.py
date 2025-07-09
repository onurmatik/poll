from django.shortcuts import get_object_or_404, render

from .models import Question, Answer


def question_detail(request, uuid):
    question = get_object_or_404(Question, uuid=uuid)
    rendered_questions = question.render_all_questions()
    num_variations = len(rendered_questions)
    choice_pairs = question.choice_pairs()
    total_queries = len(rendered_questions) * len(choice_pairs)
    batches = question.openai_batches.all().order_by("-created_at")
    answers = Answer.objects.filter(question=question)

    context = {
        "question": question,
        "num_variations": num_variations,
        "total_queries": total_queries,
        "batches": batches,
        "answers": answers,
    }
    return render(request, "main/question_detail.html", context)
