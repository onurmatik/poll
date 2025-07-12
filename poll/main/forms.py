from django import forms
import json

from .models import Question

class QuestionForm(forms.ModelForm):
    context = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'})
    )
    choices = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'})
    )

    class Meta:
        model = Question
        fields = ['text', 'context', 'choices']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # When editing (not bound), convert JSON fields to user-friendly strings
        if not self.is_bound:
            if isinstance(self.initial.get('context'), dict):
                self.initial['context'] = json.dumps(self.initial['context'])
            if isinstance(self.initial.get('choices'), (list, tuple)):
                self.initial['choices'] = "\n".join(self.initial['choices'])

    def clean_context(self):
        data = self.cleaned_data.get('context')
        if not data:
            return {}
        if isinstance(data, dict):
            return data
        try:
            return json.loads(data)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError('Enter valid JSON') from exc

    def clean_choices(self):
        data = self.cleaned_data.get('choices')
        if not data:
            return []
        if isinstance(data, list):
            return data
        # split by newlines
        return [line.strip() for line in str(data).splitlines() if line.strip()]

