"""
Formulários relacionados a formulários dinâmicos de visto.
"""

from django import forms
from django.db.models import Max, Q

from consultancy.models import FormularioVisto, PerguntaFormulario, TipoVisto


class FormularioVistoForm(forms.ModelForm):
    """Formulário para criar/editar formulário de visto."""

    class Meta:
        model = FormularioVisto
        fields = ("tipo_visto", "ativo")
        widgets = {
            "tipo_visto": forms.Select(attrs={"class": "input"}),
            "ativo": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar apenas tipos de visto que ainda não têm formulário
        if self.instance.pk:
            # Ao editar, permitir o tipo de visto atual
            self.fields["tipo_visto"].queryset = TipoVisto.objects.filter(
                Q(pk=self.instance.tipo_visto_id) | Q(formulario__isnull=True)
            )
        else:
            # Ao criar, apenas tipos sem formulário
            self.fields["tipo_visto"].queryset = TipoVisto.objects.filter(formulario__isnull=True)


class PerguntaFormularioForm(forms.ModelForm):
    """Formulário para criar/editar pergunta de formulário."""

    class Meta:
        model = PerguntaFormulario
        fields = ("pergunta", "tipo_campo", "obrigatorio", "ordem", "ativo")
        widgets = {
            "pergunta": forms.TextInput(
                attrs={
                    "placeholder": "Digite a pergunta",
                    "class": "input",
                }
            ),
            "tipo_campo": forms.Select(attrs={"class": "input"}),
            "obrigatorio": forms.CheckboxInput(),
            "ordem": forms.NumberInput(
                attrs={
                    "min": "0",
                    "step": "1",
                    "class": "input",
                }
            ),
            "ativo": forms.CheckboxInput(),
        }

    def __init__(self, *args, formulario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if formulario:
            self.instance.formulario = formulario
            # Definir ordem padrão como próxima disponível
            if not self.instance.pk:
                ultima_ordem = PerguntaFormulario.objects.filter(
                    formulario=formulario
                ).aggregate(Max("ordem"))["ordem__max"]
                self.fields["ordem"].initial = (ultima_ordem or 0) + 1

