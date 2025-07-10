from django.shortcuts import get_object_or_404, render
from django.http import HttpResponse
import csv
import json

from .models import Question


def question_detail(request, uuid):
    question = get_object_or_404(Question, uuid=uuid)
    rendered_questions = question.render_all_questions()
    num_variations = len(rendered_questions)
    choice_pairs = question.choice_pairs()
    total_queries = len(rendered_questions) * len(choice_pairs)
    batches = question.openai_batches.all().order_by("-created_at")

    answers = question.latest_answers()
    has_answers = answers.exists()

    preference_counts: dict[str, int] = {}
    for ans in answers:
        chosen = ans.choices.get(ans.choice)
        if chosen:
            preference_counts[chosen] = preference_counts.get(chosen, 0) + 1

    context = {
        "question": question,
        "num_variations": num_variations,
        "total_queries": total_queries,
        "batches": batches,
        "has_answers": has_answers,
        "preference_counts": preference_counts,
        "preference_counts_json": json.dumps(preference_counts),
    }
    return render(request, "main/question_detail.html", context)


def question_answers_csv(request, uuid):
    question = get_object_or_404(Question, uuid=uuid)

    answers = question.latest_answers()

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=answers.csv"
    writer = csv.writer(response)
    writer.writerow(["question", "context", "choices", "choice", "confidence", "run_id"])
    for ans in answers:
        writer.writerow([
            ans.question.text,
            json.dumps(ans.context, ensure_ascii=False),
            json.dumps(ans.choices, ensure_ascii=False),
            ans.choice,
            ans.confidence,
            ans.run_id,
        ])

    return response
