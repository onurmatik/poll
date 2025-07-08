from itertools import product, combinations, permutations
from typing import List, Dict

from django.db import models
from django.template import Template, Context


class Question(models.Model):
    template = models.CharField(max_length=500)  # Where would a {{ gender }} from {{ country }} prefer to move?
    context = models.JSONField(default=dict)  # {'country': ['Turkey', 'Mexico', ...], 'gender': ['man', 'woman']}
    choices = models.JSONField(default=list)  # ['Turkey', 'Mexico', 'Germany', 'Brasil', 'Japan', ...]

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.template

    def render_all_questions(self):
        """
        Materialise every concrete question implied by this instance.

        Returns
        -------
        list[tuple[str, dict]]
            [
                ("Where would a man from Turkey prefer to move?", {'gender': 'man', 'country': 'Turkey'}),
                ("Where would a man from Mexico prefer to move?", {'gender': 'man', 'country': 'Mexico'}),
                ...
            ]

        Notes
        -----
        * Keys in ``self.context`` that map to scalars are treated as single‑element
          lists so you can mix list and scalar values.
        * If ``self.context`` is empty the method simply returns the raw template.
        * Uses Django’s own template engine, so filters/tags in the template
          continue to work.
        """
        if not self.context:  # No dynamic parts; return as‑is
            return [(self.template, {})]

        # Normalise: every key maps to an iterable
        keys = list(self.context.keys())
        value_sequences = [
            v if isinstance(v, (list, tuple)) else [v]
            for v in (self.context[k] for k in keys)
        ]

        compiled_tmpl = Template(self.template)
        results = []

        for combination in product(*value_sequences):
            bound_ctx = dict(zip(keys, combination))
            rendered = compiled_tmpl.render(Context(bound_ctx))
            results.append((rendered, bound_ctx))

        return results

    def choice_pairs(self, *, ordered: bool = False, deduplicate: bool = True) -> List[Dict[str, str]]:
        """
        Return every pair of items that can be formed from ``self.choices``.

        Parameters
        ----------
        ordered : bool, default ``False``
            * ``False`` – treat the pair ('A', 'B') as identical to ('B', 'A')
              → uses *combinations* (n C 2).
            * ``True``  – order matters, so both ('A', 'B') and ('B', 'A') are
              produced → uses *permutations* (n P 2).

        deduplicate : bool, default ``True``
            If *True* the method first removes duplicate values found in
            ``self.choices`` (preserving the original order of first
            appearance). Set to *False* if you deliberately want duplicates
            to generate additional pairs.

        Returns
        -------
        list[dict[str, str]]
            A list of dictionaries mapping ``"A"`` and ``"B"`` to the paired
            items.

        Examples
        --------
        >>> q.choices
        ['Turkey', 'Mexico', 'Germany']
        >>> q.choice_pairs()
        [{'A': 'Turkey', 'B': 'Mexico'}, {'A': 'Turkey', 'B': 'Germany'}, {'A': 'Mexico', 'B': 'Germany'}]

        >>> q.choice_pairs(ordered=True)
        [{'A': 'Turkey', 'B': 'Mexico'}, {'A': 'Turkey', 'B': 'Germany'},
         {'A': 'Mexico', 'B': 'Turkey'}, {'A': 'Mexico', 'B': 'Germany'},
         {'A': 'Germany', 'B': 'Turkey'}, {'A': 'Germany', 'B': 'Mexico'}]
        """
        items = self.choices or []
        if deduplicate:
            seen = set()
            items = [x for x in items if not (x in seen or seen.add(x))]

        if len(items) < 2:
            return []

        pair_iter = permutations(items, 2) if ordered else combinations(items, 2)
        return [{"A": a, "B": b} for a, b in pair_iter]


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    context = models.JSONField(default=dict)  # {'country': 'Turkey', 'gender': 'man'}
    choices = models.JSONField(default=dict)  # {"A": "Turkey", "B": "Mexico"}
    choice = models.CharField(
        max_length=1,
        choices=[(c, c) for c in ["A", "B"]],
    )  # "A"
