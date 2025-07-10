import json
from io import BytesIO
from itertools import product, combinations
from typing import List, Dict, Literal

import uuid
import openai
from pydantic import BaseModel, confloat
from openai.lib._pydantic import to_strict_json_schema
from django.db import models



class ABResponse(BaseModel):
    """Response model indicating a binary choice with confidence level.

    Attributes:
        answer (Literal["A", "B"]): The selected answer, either "A" or "B".
        confidence (float): Confidence score for the selected answer, ranging from 0 to 1.
    """

    answer: Literal["A", "B"]
    confidence: confloat(ge=0, le=1)


AB_RESPONSE_SCHEMA = to_strict_json_schema(ABResponse)


class Question(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    text = models.CharField(max_length=500)  # Where would you like to move for living?
    context = models.JSONField(default=dict)  # {"country": ["Turkey", "Mexico", ...], "gender": ["man", "woman"]}
    choices = models.JSONField(default=list)  # ["Turkey", "Mexico", "Germany", "Brasil", "Japan", ...]

    created_at = models.DateTimeField(auto_now_add=True)

    archived = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.text

    def context_combinations(self) -> List[dict]:
        """Return all possible context dictionaries for this question."""
        if not self.context:
            return [{}]

        keys = list(self.context.keys())
        value_sequences = [
            v if isinstance(v, (list, tuple)) else [v]
            for v in (self.context[k] for k in keys)
        ]

        return [dict(zip(keys, combo)) for combo in product(*value_sequences)]

    def render_all_questions(self) -> List[tuple[str, dict]]:
        """Return question text with every context combination."""
        return [(self.text, ctx) for ctx in self.context_combinations()]

    def render_question(self, context: dict) -> str:
        """Return the question text (context is ignored)."""
        return self.text


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
        contexts = self.context_combinations()
        pairs = self.choice_pairs()

        json_lines: List[str] = []

        for _ctx in contexts:
            ctx_lines = "\n".join(f"{k}: {v}" for k, v in _ctx.items())
            dev_msg = "You are the average person defined by these demographics:"
            if ctx_lines:
                dev_msg += "\n" + ctx_lines
            for pair in pairs:
                user_msg = f"{self.text}\nA: {pair['A']}\nB: {pair['B']}"

                body = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "developer", "content": dev_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "ab_response_schema",
                            "strict": True,
                            "schema": AB_RESPONSE_SCHEMA,
                        }
                    },
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

        run_id = uuid.uuid4()

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

            # bookkeeping - store the full response object as JSON
            OpenAIBatch.objects.create(
                question=self,
                run_id=run_id,
                data=batch.model_dump(),
            )


class OpenAIBatch(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="openai_batches"
    )
    run_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    data = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    @property
    def batch_id(self) -> str | None:
        return self.data.get("id")

    @property
    def status(self) -> str | None:
        return self.data.get("status")

    @property
    def output_file_id(self) -> str | None:
        return self.data.get("output_file_id")

    @property
    def error_file_id(self) -> str | None:
        return self.data.get("error_file_id")

    class Meta:
        verbose_name_plural = "OpenAI Batches"

    def __str__(self) -> str:
        return self.batch_id or "unknown"

    def update_status(self):
        client = openai.OpenAI()

        batch = client.batches.retrieve(self.batch_id)
        self.data = batch.model_dump()
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
                entry = json.loads(line)
                results.append(entry)

                custom_id = entry.get("custom_id", "")
                parts = custom_id.split("-")

                # Expect: q<id>-<ctx values...>-<A>-<B>
                if not parts or not parts[0].startswith("q"):
                    continue

                try:
                    question_id = int(parts[0][1:])
                except ValueError:
                    continue

                try:
                    question = Question.objects.get(pk=question_id)
                except Question.DoesNotExist:
                    continue

                ctx_keys = sorted(question.context.keys())
                ctx_values = parts[1 : 1 + len(ctx_keys)]
                context = dict(zip(ctx_keys, ctx_values))

                try:
                    choice_a = parts[1 + len(ctx_keys)]
                    choice_b = parts[2 + len(ctx_keys)]
                except IndexError:
                    continue

                choices = {"A": choice_a, "B": choice_b}

                # Extract answer and confidence from response body
                body = (
                    entry.get("response", {})
                    .get("body", {})
                )
                message = None
                if body:
                    choices_resp = body.get("choices", [])
                    if choices_resp:
                        message = choices_resp[0].get("message", {})

                try:
                    content = message.get("content", "") if message else ""
                    parsed = json.loads(content) if content else {}
                except json.JSONDecodeError:
                    parsed = {}

                Answer.objects.create(
                    question=question,
                    run_id=self.run_id,
                    context=context,
                    choices=choices,
                    choice=parsed.get("answer"),
                    confidence=parsed.get("confidence"),
                )

        return results


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    run_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    context = models.JSONField(default=dict)  # {"country": "Turkey", "gender": "man"}
    choices = models.JSONField(default=dict)  # {"A": "Turkey", "B": "Mexico"}
    choice = models.CharField(
        max_length=1,
        choices=[(c, c) for c in ["A", "B"]],
    )
    confidence = models.FloatField(null=True, blank=True)

    @property
    def rendered_question(self) -> str:
        return self.question.render_question(self.context)

    @property
    def choice_a(self) -> str:
        return self.choices.get("A", "")

    @property
    def choice_b(self) -> str:
        return self.choices.get("B", "")
