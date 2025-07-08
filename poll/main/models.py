import json
from io import BytesIO
from itertools import product, combinations
from typing import List, Dict

import openai
from django.db import models
from django.template import Template, Context


class Question(models.Model):
    template = models.CharField(max_length=500)  # Where would a {{ gender }} from {{ country }} prefer to move?
    context = models.JSONField(default=dict)  # {"country": ["Turkey", "Mexico", ...], "gender": ["man", "woman"]}
    choices = models.JSONField(default=list)  # ["Turkey", "Mexico", "Germany", "Brasil", "Japan", ...]

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
                ("Where would a man from Turkey prefer to move?", {"gender": "man", "country": "Turkey"}),
                ("Where would a man from Mexico prefer to move?", {"gender": "man", "country": "Mexico"}),
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

    def choice_pairs(self) -> List[Dict[str, str]]:
        """
        Return every pair of items that can be formed from ``self.choices``.

        Returns
        -------
        list[dict[str, str]]
            A list of dictionaries mapping ``"A"`` and ``"B"`` to the paired
            items.

        Examples
        --------
        >>> q.choices
        ["Turkey", "Mexico", "Germany"]
        >>> q.choice_pairs()
        [{"A": "Turkey", "B": "Mexico"}, {"A": "Turkey", "B": "Germany"}, {"A": "Mexico", "B": "Germany"}]
        """
        items = list(dict.fromkeys(self.choices or []))

        if len(items) < 2:
            return []

        pair_iter = combinations(items, 2)
        return [{"A": a, "B": b} for a, b in pair_iter]

    def get_openai_batches(self, max_lines: int = 50_000) -> List[str]:
        """
        Produce newline-delimited-JSON payloads for the OpenAI batch endpoint.

        Parameters
        ----------
        max_lines : int, optional
            Maximum number of JSON lines per batch (default 50 000).

        Returns
        -------
        List[str]
            Each item is the raw text of a .jsonl batch containing ≤ ``max_lines`` lines.
        """
        rendered_questions = self.render_all_questions()
        pairs = self.choice_pairs()

        json_lines: List[str] = []

        for rendered, _ctx in rendered_questions:
            for pair in pairs:
                prompt = (
                    f"{rendered} (A) {pair['A']} (B) {pair['B']}\n"
                    "Please answer with 'A' or 'B'."
                )

                body = {
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": prompt}],
                }

                ctx_key_order = sorted(_ctx)
                ctx_part = "-".join(str(_ctx[k]) for k in ctx_key_order)
                custom_id = f"q{self.pk}-{ctx_part}-{pair['A']}-{pair['B']}"

                json_lines.append(
                    json.dumps(
                        {
                            "custom_id": custom_id,
                            "method": "POST",
                            "url": "/v1/chat/completions",
                            "body": body,
                        },
                        separators=(",", ":")  # compact JSON
                    )
                )

        # Split into batches of at most `max_lines` JSON objects
        return [
            "\n".join(json_lines[i : i + max_lines])
            for i in range(0, len(json_lines), max_lines)
        ]

    def submit_batches(self):
        client = openai.OpenAI()

        for i, payload in enumerate(self.get_openai_batches()):
            buf = BytesIO()

            buf.write(payload.encode("utf-8"))
            buf.write(b"\n")
            buf.seek(0)

            # upload the buffer
            file_obj = client.files.create(
                file=(f"batch_{self.pk}_{i:02d}.jsonl", buf),
                purpose="batch",
            )

            # create the batch job
            batch = client.batches.create(
                completion_window="24h",
                endpoint="/v1/chat/completions",
                input_file_id=file_obj.id,
            )

            # bookkeeping
            OpenAIBatch.objects.create(
                question=self,
                batch_id=batch.id,
                status=batch.status,
            )


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    context = models.JSONField(default=dict)  # {"country": "Turkey", "gender": "man"}
    choices = models.JSONField(default=dict)  # {"A": "Turkey", "B": "Mexico"}
    choice = models.CharField(
        max_length=1,
        choices=[(c, c) for c in ["A", "B"]],
    )


class OpenAIBatch(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="openai_batches")
    batch_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, db_index=True)
    errors = models.TextField(blank=True, null=True)
    output_file_id = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    def __str__(self) -> str:
        return self.batch_id

    def update_status(self):
        client = openai.OpenAI()

        batch = client.batches.retrieve(self.batch_id)

        self.status = batch.status
        self.errors = batch.errors
        self.output_file_id = batch.output_file_id
        self.save()

    def retrieve_results(self) -> List[dict]:
        """Download and parse the batch output file.

        Returns
        -------
        list[dict]
            Parsed JSON entries from the output file. An empty list is
            returned if ``output_file_id`` is not available.
        """
        if not self.output_file_id:
            return []

        client = openai.OpenAI()
        file_response = client.files.content(self.output_file_id)

        results = []
        for line in file_response.text.splitlines():
            line = line.strip()
            if line:
                results.append(json.loads(line))

        return results
