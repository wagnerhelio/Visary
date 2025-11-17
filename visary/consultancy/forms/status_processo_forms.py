"""
Formulários relacionados a status de processos.
"""

from django import forms

from consultancy.models import StatusProcesso


class StatusProcessoForm(forms.ModelForm):
    """Formulário para cadastro de status de processo."""

    class Meta:
        model = StatusProcesso
        fields = ("tipo_visto", "nome", "prazo_padrao_dias", "ordem", "ativo")
        widgets = {
            "tipo_visto": forms.Select(attrs={"class": "input"}),
            "nome": forms.TextInput(
                attrs={
                    "class": "input",
                    "placeholder": "Ex: Preencher ficha cadastral",
                }
            ),
            "prazo_padrao_dias": forms.NumberInput(
                attrs={
                    "class": "input",
                    "min": "0",
                    "step": "1",
                }
            ),
            "ordem": forms.NumberInput(
                attrs={
                    "class": "input",
                    "min": "0",
                    "step": "1",
                }
            ),
            "ativo": forms.CheckboxInput(
                attrs={
                    "class": "checkbox",
                }
            ),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Filtrar tipos de visto ativos
        from consultancy.models import TipoVisto
        self.fields["tipo_visto"].queryset = TipoVisto.objects.filter(ativo=True).order_by(
            "pais_destino__nome", "nome"
        )
        # Tornar tipo_visto opcional no formulário
        self.fields["tipo_visto"].required = False
        self.fields["tipo_visto"].empty_label = "Todos os tipos de visto (geral)"
        
        # Se não tiver ordem definida, usar o próximo número disponível
        if not self.instance.pk and not self.initial.get("ordem"):
            from django.db.models import Max
            ultima_ordem = StatusProcesso.objects.aggregate(max_ordem=Max("ordem"))["max_ordem"]
            self.fields["ordem"].initial = (ultima_ordem or 0) + 1

