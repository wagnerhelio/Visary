"""
Formulários para gerenciar etapas de cadastro de clientes.
"""

from django import forms

from consultancy.models import CampoEtapaCliente, EtapaCadastroCliente


class EtapaCadastroClienteForm(forms.ModelForm):
    """Formulário para criar/editar etapas de cadastro."""

    class Meta:
        model = EtapaCadastroCliente
        fields = ("nome", "descricao", "ordem", "ativo", "campo_booleano")
        widgets = {
            "nome": forms.TextInput(
                attrs={
                    "placeholder": "Ex: Dados Pessoais",
                    "autocomplete": "off",
                }
            ),
            "descricao": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Descrição da etapa",
                }
            ),
            "ordem": forms.NumberInput(
                attrs={
                    "min": 0,
                    "step": 1,
                }
            ),
            "campo_booleano": forms.TextInput(
                attrs={
                    "placeholder": "Ex: etapa_dados_pessoais",
                    "help_text": "Nome do campo booleano do ClienteConsultoria",
                }
            ),
        }


class CampoEtapaClienteForm(forms.ModelForm):
    """Formulário para criar/editar campos de uma etapa."""

    class Meta:
        model = CampoEtapaCliente
        fields = ("etapa", "nome_campo", "tipo_campo", "ordem", "obrigatorio", "ativo")
        widgets = {
            "etapa": forms.Select(
                attrs={
                    "class": "input",
                }
            ),
            "nome_campo": forms.TextInput(
                attrs={
                    "placeholder": "Ex: nome, email, cep",
                    "autocomplete": "off",
                }
            ),
            "tipo_campo": forms.Select(
                attrs={
                    "class": "input",
                }
            ),
            "ordem": forms.NumberInput(
                attrs={
                    "min": 0,
                    "step": 1,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["etapa"].queryset = EtapaCadastroCliente.objects.filter(ativo=True).order_by("ordem", "nome")


class CampoEtapaClienteInlineForm(forms.ModelForm):
    """Formulário inline para campos de etapa (sem campo etapa)."""

    class Meta:
        model = CampoEtapaCliente
        fields = ("nome_campo", "tipo_campo", "ordem", "obrigatorio", "ativo")
        widgets = {
            "nome_campo": forms.TextInput(
                attrs={
                    "placeholder": "Ex: nome, email, cep",
                    "autocomplete": "off",
                }
            ),
            "tipo_campo": forms.Select(
                attrs={
                    "class": "input",
                }
            ),
            "ordem": forms.NumberInput(
                attrs={
                    "min": 0,
                    "step": 1,
                }
            ),
        }

