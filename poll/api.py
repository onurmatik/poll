from ninja import NinjaAPI, Router
from django.shortcuts import get_object_or_404

from .main.models import Question

api = NinjaAPI()

chart_router = Router()

@chart_router.get("questions/{uuid}/preference-counts")
def preference_counts(request, uuid: str):
    question = get_object_or_404(Question, uuid=uuid)
    answers = question.latest_answers()

    for key in question.context.keys():
        value = request.GET.get(key)
        if value:
            answers = answers.filter(**{f"context__{key}": value})

    counts: dict[str, int] = {}
    for ans in answers:
        chosen = ans.choices.get(ans.choice)
        if chosen:
            counts[chosen] = counts.get(chosen, 0) + 1

    return {"counts": counts}


@chart_router.get("questions/{uuid}/preference-heatmap")
def preference_heatmap(request, uuid: str):
    """Return head-to-head win counts for all choice pairs."""
    question = get_object_or_404(Question, uuid=uuid)
    answers = question.latest_answers()

    for key in question.context.keys():
        value = request.GET.get(key)
        if value:
            answers = answers.filter(**{f"context__{key}": value})

    choices = list(dict.fromkeys(question.choices or []))
    index = {c: i for i, c in enumerate(choices)}
    size = len(choices)
    matrix: list[list[int | None]] = [
        [None if i == j else 0 for j in range(size)] for i in range(size)
    ]

    for ans in answers:
        a = ans.choices.get("A")
        b = ans.choices.get("B")
        if a not in index or b not in index:
            continue
        if ans.choice == "A":
            matrix[index[a]][index[b]] += 1  # type: ignore[operator]
        elif ans.choice == "B":
            matrix[index[b]][index[a]] += 1  # type: ignore[operator]

    return {"choices": choices, "matrix": matrix}

api.add_router("/charts/", chart_router)
