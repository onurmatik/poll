from django.shortcuts import render

from .models import Example


def home(request):
    """Display example use cases with sample questions."""
    examples = Example.objects.prefetch_related('questions')
    return render(request, 'examples/home.html', {'examples': examples})
