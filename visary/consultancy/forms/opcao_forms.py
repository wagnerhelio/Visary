"""
Formulários relacionados a opções de seleção.
"""

from django import forms

from consultancy.models import OpcaoSelecao


class OpcaoSelecaoForm(forms.ModelForm):
    """Formulário para criar/editar opção de seleção."""

    class Meta:
        model = OpcaoSelecao
        fields = ("texto", "ordem", "ativo")
        widgets = {
            "texto": forms.TextInput(
                attrs={
                    "placeholder": "Digite o texto da opção",
                    "class": "input",
                }
            ),
            "ordem": forms.NumberInput(
                attrs={
                    "min": "0",
                    "step": "1",
                    "class": "input",
                }
            ),
            "ativo": forms.CheckboxInput(),
        }

    def __init__(self, *args, pergunta=None, **kwargs):
        super().__init__(*args, **kwargs)
        if pergunta:
            self.instance.pergunta = pergunta
            # Definir ordem padrão como próxima disponível
            if not self.instance.pk:
                from django.db.models import Max
                ultima_ordem = OpcaoSelecao.objects.filter(
                    pergunta=pergunta
                ).aggregate(Max("ordem"))["ordem__max"]
                self.fields["ordem"].initial = (ultima_ordem or 0) + 1

