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

api.add_router("/charts/", chart_router)
