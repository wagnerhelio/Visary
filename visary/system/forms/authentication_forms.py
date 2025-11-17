"""
Formulários relacionados à autenticação da consultoria.
"""

from django import forms


class ConsultancyAuthenticationForm(forms.Form):
    identifier = forms.CharField(
        label="E-mail ou usuário",
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "placeholder": "Seu e-mail corporativo ou usuário",
            }
        ),
    )
    password = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "Sua senha",
            }
        ),
    )
    remember_me = forms.BooleanField(
        label="Manter conectado",
        required=False,
        initial=False,
    )

