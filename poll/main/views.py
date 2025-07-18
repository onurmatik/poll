from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.urls import reverse
import csv
import json

from .models import Question
from .forms import QuestionForm


@login_required
def question_list(request):
    """List questions grouped by status."""
    active = (
        Question.objects.filter(
            archived=False,
            status__in=["draft", "queued", "running", "completed", "importing"],
            created_by__isnull=False,
        )
        .order_by("-created_at")
        .prefetch_related("openai_batches")
    )
    examples = (
        Question.objects.filter(
            archived=False,
            created_by__isnull=True,
        )
        .order_by("-created_at")
        .prefetch_related("openai_batches")
    )
    failed = (
        Question.objects.filter(archived=False, status="failed")
        .order_by("-created_at")
        .prefetch_related("openai_batches")
    )
    archived = (
        Question.objects.filter(archived=True)
        .order_by("-created_at")
        .prefetch_related("openai_batches")
    )
    context = {
        "active": active,
        "examples": examples,
        "failed": failed,
        "archived": archived,
    }
    return render(request, "main/question_list.html", context)


@login_required
def question_results(request, uuid):
    question = get_object_or_404(Question, uuid=uuid)
    rendered_questions = question.render_all_questions()
    num_variations = len(rendered_questions)
    choice_pairs = question.choice_pairs()
    total_queries = len(rendered_questions) * len(choice_pairs)
    batches = question.openai_batches.all().order_by("-created_at")
    latest_batch = batches.first()
    batch_total_queries = latest_batch.request_count_total if latest_batch else None
    batch_duration = latest_batch.duration_seconds if latest_batch else None

    answers = question.latest_answers()
    has_answers = answers.exists()

    context = {
        "question": question,
        "num_variations": num_variations,
        "total_queries": total_queries,
        "batches": batches,
        "batch_total_queries": batch_total_queries,
        "batch_duration": batch_duration,
        "has_answers": has_answers,
    }
    return render(request, "main/question_results.html", context)


@login_required
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


@login_required
def question_create(request):
    """Create a new question or edit an existing one."""
    uuid_param = request.GET.get("uuid")
    instance = None
    if uuid_param:
        instance = get_object_or_404(Question, uuid=uuid_param)

    if request.method == "POST":
        form = QuestionForm(request.POST, instance=instance)
        if form.is_valid():
            question = form.save(commit=False)
            if not question.created_by_id:
                question.created_by = request.user
            question.save()
            return redirect("polls:question_review", uuid=question.uuid)
    else:
        form = QuestionForm(instance=instance)

    return render(request, "main/question_form.html", {"form": form})


@login_required
def question_review(request, uuid):
    """Display a read-only summary of the question and submit batches."""
    question = get_object_or_404(Question, uuid=uuid)

    rendered = question.render_all_questions()
    num_variations = len(rendered)
    choice_pairs = question.choice_pairs()
    total_queries = num_variations * len(choice_pairs)

    if request.method == "POST":
        question.status = "queued"
        question.save(update_fields=["status"])
        question.submit_batches()
        return redirect("polls:question_list")

    return render(
        request,
        "main/question_review.html",
        {
            "question": question,
            "num_variations": num_variations,
            "num_choice_pairs": len(choice_pairs),
            "total_queries": total_queries,
        },
    )


@login_required
def question_toggle_archive(request, uuid):
    """Toggle the archived state of a question."""
    question = get_object_or_404(Question, uuid=uuid)
    if request.method == "POST":
        question.archived = not question.archived
        question.save(update_fields=["archived"])
    return redirect("polls:question_list")


@login_required
def question_clone(request, uuid):
    """Duplicate an existing question for the current user."""
    original = get_object_or_404(Question, uuid=uuid)
    if request.method == "POST":
        clone = Question.objects.create(
            text=original.text,
            context=original.context,
            choices=original.choices,
            created_by=request.user,
        )
        edit_url = f"{reverse('polls:question_create')}?uuid={clone.uuid}"
        return redirect(edit_url)
    return redirect("polls:question_list")


@login_required
def question_delete(request, uuid):
    """Delete a question draft."""
    question = get_object_or_404(Question, uuid=uuid)
    if request.method == "POST":
        question.delete()
    return redirect("polls:question_list")
