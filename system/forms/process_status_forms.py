from django import forms
from django.db.models import Max

from system.models import ProcessStatus, VisaType


class ProcessStatusForm(forms.ModelForm):
    class Meta:
        model = ProcessStatus
        fields = ("visa_type", "name", "default_deadline_days", "order", "is_active")
        widgets = {
            "visa_type": forms.Select(attrs={"class": "input"}),
            "name": forms.TextInput(
                attrs={"class": "input", "placeholder": "Ex: Preencher ficha cadastral"}
            ),
            "default_deadline_days": forms.NumberInput(
                attrs={"class": "input", "min": "0", "step": "1"}
            ),
            "order": forms.NumberInput(
                attrs={"class": "input", "min": "0", "step": "1"}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["visa_type"].queryset = VisaType.objects.filter(is_active=True).order_by(
            "destination_country__name", "name"
        )
        self.fields["visa_type"].required = False
        self.fields["visa_type"].empty_label = "Todos os tipos de visto (geral)"
        if not self.instance.pk and not self.initial.get("order"):
            last_order = ProcessStatus.objects.aggregate(max_order=Max("order"))["max_order"]
            self.fields["order"].initial = (last_order or 0) + 1
