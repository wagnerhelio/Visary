from django import forms
from django.db.models import Max, Q

from system.models import FormQuestion, VisaForm, VisaFormStage, VisaType


class VisaFormForm(forms.ModelForm):
    class Meta:
        model = VisaForm
        fields = ("visa_type", "is_active")
        widgets = {
            "visa_type": forms.Select(attrs={"class": "input"}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["visa_type"].queryset = VisaType.objects.filter(
                Q(pk=self.instance.visa_type_id) | Q(form__isnull=True)
            )
        else:
            self.fields["visa_type"].queryset = VisaType.objects.filter(form__isnull=True)


class FormQuestionForm(forms.ModelForm):
    class Meta:
        model = FormQuestion
        fields = ("question", "stage", "field_type", "is_required", "order", "is_active")
        widgets = {
            "question": forms.TextInput(
                attrs={"placeholder": "Digite a pergunta", "class": "input"}
            ),
            "stage": forms.Select(attrs={"class": "input"}),
            "field_type": forms.Select(attrs={"class": "input"}),
            "is_required": forms.CheckboxInput(),
            "order": forms.NumberInput(
                attrs={"min": "0", "step": "1", "class": "input"}
            ),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, visa_form=None, **kwargs):
        super().__init__(*args, **kwargs)
        if visa_form:
            self.instance.form = visa_form
            self.fields["stage"].queryset = VisaFormStage.objects.filter(
                form=visa_form, is_active=True
            ).order_by("order", "name")
            if not self.instance.pk:
                last_order = FormQuestion.objects.filter(
                    form=visa_form
                ).aggregate(Max("order"))["order__max"]
                self.fields["order"].initial = (last_order or 0) + 1


class VisaFormStageForm(forms.ModelForm):
    class Meta:
        model = VisaFormStage
        fields = ("name", "order", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"class": "input", "placeholder": "Nome da etapa"}),
            "order": forms.NumberInput(attrs={"class": "input", "min": "0", "step": "1"}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, visa_form=None, **kwargs):
        super().__init__(*args, **kwargs)
        if visa_form:
            max_order = (
                VisaFormStage.objects.filter(form=visa_form)
                .aggregate(Max("order"))["order__max"]
                or 0
            )
            self.fields["order"].help_text = f"Próxima ordem disponível: {max_order + 1}"
