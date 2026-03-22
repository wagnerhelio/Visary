   
                                                          
   

from django import forms
from django.db.models import Max, Q

from system.models import EtapaFormularioVisto, FormularioVisto, PerguntaFormulario, TipoVisto


class FormularioVistoForm(forms.ModelForm):
                                                           

    class Meta:
        model = FormularioVisto
        fields = ("tipo_visto", "ativo")
        widgets = {
            "tipo_visto": forms.Select(attrs={"class": "input"}),
            "ativo": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
                                                                    
        if self.instance.pk:
                                                       
            self.fields["tipo_visto"].queryset = TipoVisto.objects.filter(
                Q(pk=self.instance.tipo_visto_id) | Q(formulario__isnull=True)
            )
        else:
                                                   
            self.fields["tipo_visto"].queryset = TipoVisto.objects.filter(formulario__isnull=True)


class PerguntaFormularioForm(forms.ModelForm):
                                                              

    class Meta:
        model = PerguntaFormulario
        fields = ("pergunta", "etapa", "tipo_campo", "obrigatorio", "ordem", "ativo")
        widgets = {
            "pergunta": forms.TextInput(
                attrs={
                    "placeholder": "Digite a pergunta",
                    "class": "input",
                }
            ),
            "etapa": forms.Select(attrs={"class": "input"}),
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
            self.fields["etapa"].queryset = EtapaFormularioVisto.objects.filter(
                formulario=formulario,
                ativo=True,
            ).order_by("ordem", "nome")
            
            if not self.instance.pk:
                ultima_ordem = PerguntaFormulario.objects.filter(
                    formulario=formulario
                ).aggregate(Max("ordem"))["ordem__max"]
                self.fields["ordem"].initial = (ultima_ordem or 0) + 1


class FormularioEtapaForm(forms.ModelForm):
    class Meta:
        model = EtapaFormularioVisto
        fields = ("nome", "ordem", "ativo")
        widgets = {
            "nome": forms.TextInput(attrs={"class": "input", "placeholder": "Nome da etapa"}),
            "ordem": forms.NumberInput(attrs={"class": "input", "min": "0", "step": "1"}),
            "ativo": forms.CheckboxInput(),
        }

    def __init__(self, *args, formulario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if formulario:
            max_ordem = (
                EtapaFormularioVisto.objects.filter(formulario=formulario)
                .aggregate(Max("ordem"))["ordem__max"]
                or 0
            )
            self.fields["ordem"].help_text = f"Próxima ordem disponível: {max_ordem + 1}"


