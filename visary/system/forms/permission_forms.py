from django import forms

from system.models import Modulo, Perfil


class ModuloForm(forms.ModelForm):
    class Meta:
        model = Modulo
        fields = ["nome", "descricao", "ordem", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Clientes"}),
            "descricao": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Opcional: detalhe a finalidade do módulo."}
            ),
        }


class PerfilForm(forms.ModelForm):
    class Meta:
        model = Perfil
        fields = [
            "nome",
            "descricao",
            "modulos",
            "pode_criar",
            "pode_visualizar",
            "pode_atualizar",
            "pode_excluir",
            "ativo",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Assessor Pleno"}),
            "descricao": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Detalhe a responsabilidade e escopo deste perfil.",
                }
            ),
            "modulos": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["modulos"].queryset = Modulo.objects.filter(ativo=True).order_by(
            "ordem", "nome"
        )

