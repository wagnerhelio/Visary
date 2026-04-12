from django import forms

from system.models import ClientRegistrationStep, ClientStepField


class ClientRegistrationStepForm(forms.ModelForm):
    class Meta:
        model = ClientRegistrationStep
        fields = ("name", "description", "order", "is_active", "boolean_field")
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Ex: Dados Pessoais", "autocomplete": "off"}
            ),
            "description": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Descrição da etapa"}
            ),
            "order": forms.NumberInput(attrs={"min": 0, "step": 1}),
            "boolean_field": forms.TextInput(
                attrs={"placeholder": "Ex: step_personal_data"}
            ),
        }


class ClientStepFieldForm(forms.ModelForm):
    class Meta:
        model = ClientStepField
        fields = ("step", "field_name", "field_type", "order", "is_required", "is_active", "display_rule")
        widgets = {
            "step": forms.Select(attrs={"class": "input"}),
            "field_name": forms.TextInput(
                attrs={"placeholder": "Ex: first_name, email, zip_code", "autocomplete": "off"}
            ),
            "field_type": forms.Select(attrs={"class": "input"}),
            "order": forms.NumberInput(attrs={"min": 0, "step": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["step"].queryset = (
            ClientRegistrationStep.objects.filter(is_active=True).order_by("order", "name")
        )


class ClientStepFieldInlineForm(forms.ModelForm):
    class Meta:
        model = ClientStepField
        fields = ("field_name", "field_type", "order", "is_required", "is_active", "display_rule")
        widgets = {
            "field_name": forms.TextInput(
                attrs={"placeholder": "Ex: first_name, email, zip_code", "autocomplete": "off"}
            ),
            "field_type": forms.Select(attrs={"class": "input"}),
            "order": forms.NumberInput(attrs={"min": 0, "step": 1}),
        }
