"""
Formulários relacionados a viagens e destinos.
"""

from __future__ import annotations

from typing import Optional

from django import forms
from django.contrib.auth import get_user_model

from consultancy.models import ClienteConsultoria, PaisDestino, TipoVisto, Viagem
from system.models import UsuarioConsultoria

User = get_user_model()


class PaisDestinoForm(forms.ModelForm):
    """Formulário para cadastro de país de destino."""

    class Meta:
        model = PaisDestino
        fields = ("nome", "codigo_iso", "ativo")
        widgets = {
            "nome": forms.TextInput(
                attrs={"placeholder": "Nome do país", "autocomplete": "country-name"}
            ),
            "codigo_iso": forms.TextInput(
                attrs={"placeholder": "Ex: BRA, USA, FRA", "maxlength": "3", "style": "text-transform: uppercase;"}
            ),
            "ativo": forms.CheckboxInput(),
        }

    def __init__(self, *args, user: Optional[User] = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._user = user

    def save(self, commit: bool = True) -> PaisDestino:
        pais = super().save(commit=False)
        if commit:
            pais.save()
        return pais


class TipoVistoForm(forms.ModelForm):
    """Formulário para cadastro de tipo de visto."""

    class Meta:
        model = TipoVisto
        fields = ("pais_destino", "nome", "descricao", "ativo")
        widgets = {
            "pais_destino": forms.Select(attrs={"class": "input"}),
            "nome": forms.TextInput(
                attrs={"placeholder": "Ex: Turismo, Negócios, Estudante"}
            ),
            "descricao": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Descrição do tipo de visto",
                }
            ),
            "ativo": forms.CheckboxInput(),
        }

    def __init__(self, *args, user: Optional[User] = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._user = user
        self.fields["pais_destino"].queryset = PaisDestino.objects.filter(ativo=True).order_by("nome")

    def save(self, commit: bool = True) -> TipoVisto:
        tipo_visto = super().save(commit=False)
        if commit:
            tipo_visto.save()
        return tipo_visto


class ViagemForm(forms.ModelForm):
    """Formulário para cadastro de viagem."""

    class Meta:
        model = Viagem
        fields = (
            "assessor_responsavel",
            "pais_destino",
            "tipo_visto",
            "data_prevista_viagem",
            "data_prevista_retorno",
            "valor_assessoria",
            "clientes",
            "observacoes",
        )
        widgets = {
            "assessor_responsavel": forms.Select(attrs={"class": "input"}),
            "pais_destino": forms.Select(attrs={"class": "input"}),
            "tipo_visto": forms.Select(attrs={"class": "input"}),
            "data_prevista_viagem": forms.DateInput(
                attrs={"type": "date", "placeholder": "dd/mm/aaaa"}
            ),
            "data_prevista_retorno": forms.DateInput(
                attrs={"type": "date", "placeholder": "dd/mm/aaaa"}
            ),
            "valor_assessoria": forms.NumberInput(
                attrs={
                    "placeholder": "0.00",
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "clientes": forms.SelectMultiple(attrs={"class": "input"}),
            "observacoes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Informações adicionais sobre a viagem",
                }
            ),
        }

    def __init__(self, *args, user: Optional[User] = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._user = user
        self.fields["assessor_responsavel"].queryset = (
            UsuarioConsultoria.objects.filter(ativo=True)
            .order_by("nome")
            .select_related("perfil")
        )
        self.fields["pais_destino"].queryset = PaisDestino.objects.filter(ativo=True).order_by("nome")
        self.fields["tipo_visto"].queryset = TipoVisto.objects.filter(ativo=True).select_related("pais_destino")
        self.fields["clientes"].queryset = ClienteConsultoria.objects.all().order_by("nome")

        if user is not None and not user.is_superuser and not user.is_staff:
            consultor = (
                UsuarioConsultoria.objects.filter(email__iexact=user.email, ativo=True)
                .order_by("-atualizado_em")
                .first()
            )
            if consultor:
                self.fields["assessor_responsavel"].initial = consultor.pk

    def clean(self):
        cleaned_data = super().clean()
        data_viagem = cleaned_data.get("data_prevista_viagem")
        data_retorno = cleaned_data.get("data_prevista_retorno")

        if data_viagem and data_retorno:
            if data_retorno < data_viagem:
                raise forms.ValidationError(
                    "A data de retorno não pode ser anterior à data de viagem."
                )

        return cleaned_data

    def save(self, commit: bool = True) -> Viagem:
        viagem = super().save(commit=False)
        if self._user and not viagem.criado_por_id:
            viagem.criado_por = self._user

        if commit:
            viagem.save()
            self.save_m2m()

        return viagem

