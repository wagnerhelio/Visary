from django import forms
from django.contrib.auth.hashers import make_password

from system.models import ConsultancyUser, Profile


class ConsultancyUserForm(forms.ModelForm):
    raw_password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(attrs={"placeholder": "Defina uma senha segura"}),
    )

    class Meta:
        model = ConsultancyUser
        fields = ["name", "email", "raw_password", "profile", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex.: Ana Souza"}),
            "email": forms.EmailInput(attrs={"placeholder": "ana@empresa.com"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["profile"].queryset = Profile.objects.filter(is_active=True).order_by("name")
        if self.instance.pk:
            self.fields["raw_password"].required = False
            self.fields["raw_password"].widget.attrs["placeholder"] = (
                "Deixe em branco para manter a senha atual"
            )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if ConsultancyUser.objects.exclude(pk=self.instance.pk).filter(email=email).exists():
            raise forms.ValidationError("Já existe um usuário com este e-mail.")
        return email

    def save(self, commit=True):
        user_obj = super().save(commit=False)
        raw = self.cleaned_data.get("raw_password")
        if raw:
            user_obj.password = make_password(raw)
        if commit:
            user_obj.save()
            self.save_m2m()
        return user_obj
