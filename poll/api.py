from ninja import NinjaAPI, Router, Schema
from django.shortcuts import get_object_or_404

from .main.models import Question, OpenAIBatch

api = NinjaAPI()

chart_router = Router()
question_router = Router()
batch_router = Router()


class QuestionCreateSchema(Schema):
    text: str
    context: dict | None = None
    choices: list[str]


@question_router.post("")
def create_question(request, payload: QuestionCreateSchema):
    question = Question.objects.create(
        text=payload.text,
        context=payload.context or {},
        choices=payload.choices,
    )
    return api.create_response(request, {"uuid": str(question.uuid)}, status=201)

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


@chart_router.get("questions/{uuid}/confidence-distribution")
def confidence_distribution(request, uuid: str):
    """Return histogram counts for answer confidences (0-1)."""
    question = get_object_or_404(Question, uuid=uuid)
    answers = question.latest_answers()

    for key in question.context.keys():
        value = request.GET.get(key)
        if value:
            answers = answers.filter(**{f"context__{key}": value})

    bins = [0] * 10
    for ans in answers:
        if ans.confidence is None:
            continue
        idx = int(min(max(ans.confidence, 0), 0.999) * 10)
        bins[idx] += 1

    labels = [f"{i/10:.1f}-{(i+1)/10:.1f}" for i in range(10)]
    return {"labels": labels, "counts": bins}


@chart_router.get("questions/{uuid}/preference-flows")
def preference_flows(request, uuid: str):
    """Return directed win counts for Sankey diagrams."""
    question = get_object_or_404(Question, uuid=uuid)
    answers = question.latest_answers()

    for key in question.context.keys():
        value = request.GET.get(key)
        if value:
            answers = answers.filter(**{f"context__{key}": value})

    flows: dict[tuple[str, str], int] = {}
    order: list[str] = []
    for ans in answers:
        a = ans.choices.get("A")
        b = ans.choices.get("B")
        if not a or not b:
            continue
        if ans.choice == "A":
            pair = (a, b)
        elif ans.choice == "B":
            pair = (b, a)
        else:
            continue
        flows[pair] = flows.get(pair, 0) + 1
        order.extend([a, b])

    labels = list(dict.fromkeys(order))
    links = [
        {"from": src, "to": dst, "flow": cnt} for (src, dst), cnt in flows.items()
    ]
    return {"labels": labels, "links": links}


@batch_router.post("{batch_id}/update-status")
def update_batch_status(request, batch_id: str):
    """Refresh and return status info for an OpenAI batch."""
    batch = get_object_or_404(OpenAIBatch, data__id=batch_id)
    batch.update_status()
    return {
        "batch_id": batch.batch_id,
        "status": batch.status,
        "updated_at": batch.updated_at.isoformat(),
    }

api.add_router("/charts/", chart_router)
api.add_router("/questions/", question_router)
api.add_router("/batches/", batch_router)
