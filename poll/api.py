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


@chart_router.get("questions/{uuid}/elo-ratings")
def elo_ratings(request, uuid: str):
    """Return Elo-style rankings for all choices."""
    question = get_object_or_404(Question, uuid=uuid)
    answers = question.latest_answers().order_by("pk")

    for key in question.context.keys():
        value = request.GET.get(key)
        if value:
            answers = answers.filter(**{f"context__{key}": value})

    choices = list(dict.fromkeys(question.choices or []))
    ratings: dict[str, float] = {c: 1000.0 for c in choices}
    K = 32

    for ans in answers:
        a = ans.choices.get("A")
        b = ans.choices.get("B")
        if a not in ratings or b not in ratings:
            continue
        ra = ratings[a]
        rb = ratings[b]
        expected_a = 1 / (1 + 10 ** ((rb - ra) / 400))
        expected_b = 1 - expected_a
        if ans.choice == "A":
            sa, sb = 1, 0
        elif ans.choice == "B":
            sa, sb = 0, 1
        else:
            continue
        ratings[a] = ra + K * (sa - expected_a)
        ratings[b] = rb + K * (sb - expected_b)

    ranking = sorted(
        ({"choice": c, "rating": round(r, 2)} for c, r in ratings.items()),
        key=lambda x: x["rating"],
        reverse=True,
    )

    return {"rankings": ranking}

api.add_router("/charts/", chart_router)
