"""
Formulário para cadastro de clientes da consultoria.
"""

from __future__ import annotations

from typing import Optional

from django import forms
from django.contrib.auth import get_user_model

from consultancy.models import ClienteConsultoria, Partner
from system.models import UsuarioConsultoria

User = get_user_model()


class ClienteConsultoriaForm(forms.ModelForm):
    confirmar_senha = forms.CharField(
        label="Confirme a senha",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Repita a senha de acesso",
            }
        ),
    )

    class Meta:
        model = ClienteConsultoria
        fields = (
            "assessor_responsavel",
            "nome",
            "data_nascimento",
            "nacionalidade",
            "telefone",
            "telefone_secundario",
            "email",
            "senha",
            "parceiro_indicador",
            "cep",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "uf",
            "observacoes",
        )
        widgets = {
            "assessor_responsavel": forms.Select(attrs={"class": "input"}),
            "parceiro_indicador": forms.Select(
                attrs={
                    "class": "input",
                    "data-partner-select": "true",
                }
            ),
            "nome": forms.TextInput(
                attrs={"placeholder": "Nome completo", "autocomplete": "name"}
            ),
            "data_nascimento": forms.DateInput(
                attrs={"type": "date", "placeholder": "dd/mm/aaaa"}
            ),
            "nacionalidade": forms.TextInput(
                attrs={"placeholder": "Nacionalidade", "autocomplete": "country-name"}
            ),
            "telefone": forms.TextInput(
                attrs={"placeholder": "Telefone principal", "autocomplete": "tel"}
            ),
            "telefone_secundario": forms.TextInput(
                attrs={"placeholder": "Telefone secundário", "autocomplete": "tel"}
            ),
            "email": forms.EmailInput(
                attrs={"placeholder": "email@dominio.com", "autocomplete": "email"}
            ),
            "senha": forms.PasswordInput(
                attrs={
                    "autocomplete": "new-password",
                    "placeholder": "Senha de acesso do cliente",
                }
            ),
            "cep": forms.TextInput(
                attrs={
                    "placeholder": "00000-000",
                    "maxlength": "9",
                    "class": "cep-input",
                    "autocomplete": "postal-code",
                }
            ),
            "logradouro": forms.TextInput(
                attrs={"placeholder": "Rua, Avenida, etc.", "autocomplete": "street-address"}
            ),
            "numero": forms.TextInput(
                attrs={"placeholder": "Número", "autocomplete": "off"}
            ),
            "complemento": forms.TextInput(
                attrs={"placeholder": "Apto, Bloco, etc.", "autocomplete": "off"}
            ),
            "bairro": forms.TextInput(
                attrs={"placeholder": "Bairro", "autocomplete": "address-level2"}
            ),
            "cidade": forms.TextInput(
                attrs={"placeholder": "Cidade", "autocomplete": "address-level1"}
            ),
            "uf": forms.TextInput(
                attrs={
                    "placeholder": "UF",
                    "maxlength": "2",
                    "style": "text-transform: uppercase;",
                    "autocomplete": "address-level1",
                }
            ),
            "observacoes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Informações adicionais sobre o atendimento",
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
        
        # Campo de parceiro opcional
        self.fields["parceiro_indicador"].queryset = Partner.objects.filter(ativo=True).order_by("nome_empresa", "nome_responsavel")
        self.fields["parceiro_indicador"].required = False
        self.fields["parceiro_indicador"].empty_label = "Nenhum parceiro"

        if user is not None and not user.is_superuser and not user.is_staff:
            consultor = (
                UsuarioConsultoria.objects.filter(email__iexact=user.email, ativo=True)
                .order_by("-atualizado_em")
                .first()
            )
            if consultor:
                self.fields["assessor_responsavel"].initial = consultor.pk

    def clean_confirmar_senha(self):
        senha = self.cleaned_data.get("senha")
        confirmar = self.cleaned_data.get("confirmar_senha")

        if senha and confirmar and senha != confirmar:
            raise forms.ValidationError("As senhas informadas não conferem.")

        return confirmar

    def clean_senha(self):
        senha = self.cleaned_data.get("senha")
        # Se for um novo cliente (sem pk), a senha é obrigatória
        if not self.instance.pk and not senha:
            raise forms.ValidationError("A senha é obrigatória para novos clientes.")
        return senha

    def save(self, commit: bool = True) -> ClienteConsultoria:
        cliente = super().save(commit=False)
        
        # Só atualizar senha se foi fornecida (não vazia)
        senha = self.cleaned_data.get("senha")
        if senha:
            # Sempre fazer hash da senha
            cliente.set_password(senha)
        # Se estiver editando e senha vazia, manter a senha atual
        elif cliente.pk:
            # Manter a senha atual do banco (já está em hash)
            cliente_atual = ClienteConsultoria.objects.get(pk=cliente.pk)
            cliente.senha = cliente_atual.senha
        # Se for novo cliente e não tem senha, isso é um erro
        # Mas deixamos o Django validar isso no modelo

        if self._user and not cliente.criado_por_id:
            cliente.criado_por = self._user

        if commit:
            cliente.save()

        return cliente

