from django import forms
from django.core.exceptions import ValidationError

from system.models import Partner


class PartnerForm(forms.ModelForm):
    confirm_password = forms.CharField(
        label="Confirmar Senha",
        widget=forms.PasswordInput(attrs={"placeholder": "Digite a senha novamente"}),
        required=False,
    )

    class Meta:
        model = Partner
        fields = (
            "contact_name",
            "company_name",
            "cpf",
            "cnpj",
            "email",
            "password",
            "phone",
            "segment",
            "city",
            "state",
            "is_active",
        )
        widgets = {
            "contact_name": forms.TextInput(
                attrs={"placeholder": "Nome completo do responsável"}
            ),
            "company_name": forms.TextInput(
                attrs={"placeholder": "Nome da empresa (opcional)"}
            ),
            "cpf": forms.TextInput(
                attrs={"placeholder": "000.000.000-00", "maxlength": "14", "class": "cpf-input"}
            ),
            "cnpj": forms.TextInput(
                attrs={"placeholder": "00.000.000/0000-00", "maxlength": "18", "class": "cnpj-input"}
            ),
            "email": forms.EmailInput(attrs={"placeholder": "email@exemplo.com"}),
            "password": forms.PasswordInput(
                attrs={"placeholder": "Digite a senha", "autocomplete": "new-password"}
            ),
            "phone": forms.TextInput(
                attrs={"placeholder": "(00) 00000-0000", "maxlength": "15", "class": "telefone-input"}
            ),
            "segment": forms.Select(attrs={"class": "input"}),
            "city": forms.TextInput(attrs={"placeholder": "Cidade"}),
            "state": forms.TextInput(
                attrs={"placeholder": "UF", "maxlength": "2", "style": "text-transform: uppercase;"}
            ),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        for field in ("company_name", "cpf", "cnpj", "phone", "segment", "city", "state", "password", "confirm_password"):
            self.fields[field].required = False
        if self.instance.pk:
            self.fields["password"].widget.attrs["placeholder"] = "Deixe em branco para manter a senha atual"
            self.fields["confirm_password"].widget.attrs["placeholder"] = "Deixe em branco para manter a senha atual"

    def clean(self):
        cleaned_data = super().clean()
        pwd = cleaned_data.get("password")
        confirm = cleaned_data.get("confirm_password")
        if self.instance.pk:
            if (pwd or confirm) and pwd != confirm:
                raise ValidationError({"confirm_password": "As senhas não coincidem."})
        else:
            if not pwd:
                raise ValidationError({"password": "A senha é obrigatória."})
            if pwd != confirm:
                raise ValidationError({"confirm_password": "As senhas não coincidem."})
        return cleaned_data

    def save(self, commit=True):
        partner = super().save(commit=False)
        pwd = self.cleaned_data.get("password")
        if pwd:
            partner.set_password(pwd)
        elif partner.pk:
            partner.password = Partner.objects.get(pk=partner.pk).password
        if self.user and not partner.created_by_id:
            partner.created_by = self.user
        if commit:
            partner.save()
        return partner
