from django import forms
from django.db.models import Max

from system.models import SelectOption


class SelectOptionForm(forms.ModelForm):
    class Meta:
        model = SelectOption
        fields = ("text", "order", "is_active")
        widgets = {
            "text": forms.TextInput(
                attrs={"placeholder": "Digite o texto da opção", "class": "input"}
            ),
            "order": forms.NumberInput(
                attrs={"min": "0", "step": "1", "class": "input"}
            ),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, question=None, **kwargs):
        super().__init__(*args, **kwargs)
        if question:
            self.instance.question = question
            if not self.instance.pk:
                last_order = SelectOption.objects.filter(
                    question=question
                ).aggregate(Max("order"))["order__max"]
                self.fields["order"].initial = (last_order or 0) + 1
