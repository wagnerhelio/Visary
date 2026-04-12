from django import forms

from system.models import Module, Profile


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ["name", "description", "order", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex.: Clientes"}),
            "description": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Opcional: detalhe a finalidade do módulo."}
            ),
        }


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "name",
            "description",
            "modules",
            "can_create",
            "can_view",
            "can_update",
            "can_delete",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex.: Assessor Pleno"}),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Detalhe a responsabilidade e escopo deste perfil.",
                }
            ),
            "modules": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["modules"].queryset = Module.objects.filter(is_active=True).order_by(
            "order", "name"
        )
