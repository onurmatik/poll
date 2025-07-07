import hashlib
import itertools
import json
from django.db import models
from django.template import Template, Context


class Question(models.Model):
    template = models.CharField(max_length=200)
    choices = models.JSONField(default=dict)  # {'country': ['TR', 'MX', 'GB']}
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.template

    def render_question(self, who):
        """Question.template'i, Who.desc ile (ve gerekiyorsa Choice listesinden seçilen 'what') birleştirip dön."""
        ctx = {**who.desc}  # {'country': 'TR', 'gender': 'F'}
        # Ek bağlam gerekiyorsa buraya ekle: ctx.update(extra_data)
        tpl = Template(self.template)
        return tpl.render(Context(ctx))

    def possible_who_objects(self):
        """choices içindeki tüm permütasyonlara göre Who listesi döndürür (oluşturur veya getirir)."""
        keys = self.choices.keys()  # ['country']
        value_lists = self.choices.values()  # [['TR','GB','MX']]
        for combo in itertools.product(*value_lists):
            desc = dict(zip(keys, combo))  # {'country': 'TR'}
            who, _ = Who.objects.get_or_create(
                hash=hashlib.sha256(
                    json.dumps(desc, sort_keys=True).encode()
                ).hexdigest(),
                defaults={'desc': desc}
            )
            yield who


class Who(models.Model):
    desc = models.JSONField(default=dict)

    def __str__(self) -> str:
        return self.desc


class What(models.Model):
    desc = models.JSONField(default=dict)

    def __str__(self) -> str:
        return self.desc


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    who = models.ForeignKey(Who, on_delete=models.CASCADE)
    what = models.ForeignKey(What, on_delete=models.CASCADE)

    def __str__(self) -> str:
        return f"{self.who} - {self.what}"
