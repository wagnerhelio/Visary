from django import forms
from django.contrib.auth.hashers import make_password

from system.models import Perfil, UsuarioConsultoria


class UsuarioConsultoriaForm(forms.ModelForm):
    senha = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(attrs={"placeholder": "Defina uma senha segura"}),
    )

    class Meta:
        model = UsuarioConsultoria
        fields = ["nome", "email", "senha", "perfil", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Ana Souza"}),
            "email": forms.EmailInput(attrs={"placeholder": "ana@empresa.com"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["perfil"].queryset = Perfil.objects.filter(ativo=True).order_by("nome")
        if self.instance.pk:
            self.fields["senha"].required = False
            self.fields["senha"].widget.attrs[
                "placeholder"
            ] = "Deixe em branco para manter a senha atual"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if UsuarioConsultoria.objects.exclude(pk=self.instance.pk).filter(email=email).exists():
            raise forms.ValidationError("Já existe um usuário com este e-mail.")
        return email

    def save(self, commit=True):
        usuario = super().save(commit=False)
        senha_plana = self.cleaned_data.get("senha")
        if senha_plana:
            usuario.senha = make_password(senha_plana)
        if commit:
            usuario.save()
            self.save_m2m()
        return usuario

