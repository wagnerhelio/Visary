   
                                     
   

from django import forms
from django.core.exceptions import ValidationError

from consultancy.models import Partner


class PartnerForm(forms.ModelForm):
                                                         

    confirmar_senha = forms.CharField(
        label="Confirmar Senha",
        widget=forms.PasswordInput(attrs={"placeholder": "Digite a senha novamente"}),
        required=False,
        help_text="Deixe em branco para manter a senha atual ao editar.",
    )

    class Meta:
        model = Partner
        fields = (
            "nome_responsavel",
            "nome_empresa",
            "cpf",
            "cnpj",
            "email",
            "senha",
            "telefone",
            "segmento",
            "cidade",
            "estado",
            "ativo",
        )
        widgets = {
            "nome_responsavel": forms.TextInput(
                attrs={"placeholder": "Nome completo do responsável"}
            ),
            "nome_empresa": forms.TextInput(
                attrs={"placeholder": "Nome da empresa (opcional)"}
            ),
            "cpf": forms.TextInput(
                attrs={
                    "placeholder": "000.000.000-00",
                    "maxlength": "14",
                    "class": "cpf-input",
                }
            ),
            "cnpj": forms.TextInput(
                attrs={
                    "placeholder": "00.000.000/0000-00",
                    "maxlength": "18",
                    "class": "cnpj-input",
                }
            ),
            "email": forms.EmailInput(attrs={"placeholder": "email@exemplo.com"}),
            "senha": forms.PasswordInput(
                attrs={
                    "placeholder": "Digite a senha",
                    "autocomplete": "new-password",
                }
            ),
            "telefone": forms.TextInput(
                attrs={
                    "placeholder": "(00) 00000-0000",
                    "maxlength": "15",
                    "class": "telefone-input",
                }
            ),
            "segmento": forms.Select(attrs={"class": "input"}),
            "cidade": forms.TextInput(attrs={"placeholder": "Cidade"}),
            "estado": forms.TextInput(
                attrs={
                    "placeholder": "UF",
                    "maxlength": "2",
                    "style": "text-transform: uppercase;",
                }
            ),
            "ativo": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        
                                                                 
                                                 
        self.fields["nome_empresa"].required = False
        self.fields["cpf"].required = False
        self.fields["cnpj"].required = False
        self.fields["telefone"].required = False
        self.fields["segmento"].required = False
        self.fields["cidade"].required = False
        self.fields["estado"].required = False
        self.fields["senha"].required = False
        self.fields["confirmar_senha"].required = False

        if self.instance.pk:
                                                
            self.fields["senha"].widget.attrs["placeholder"] = (
                "Deixe em branco para manter a senha atual"
            )
            self.fields["confirmar_senha"].widget.attrs["placeholder"] = (
                "Deixe em branco para manter a senha atual"
            )

    def clean(self):
        cleaned_data = super().clean()
        senha = cleaned_data.get("senha")
        confirmar_senha = cleaned_data.get("confirmar_senha")
        cpf = cleaned_data.get("cpf", "").replace(".", "").replace("-", "")
        cnpj = cleaned_data.get("cnpj", "").replace(".", "").replace("/", "").replace("-", "")

                       
        if self.instance.pk:
                                                             
            if senha or confirmar_senha:
                if senha != confirmar_senha:
                    raise ValidationError({"confirmar_senha": "As senhas não coincidem."})
        else:
                                          
            if not senha:
                raise ValidationError({"senha": "A senha é obrigatória."})
            if senha != confirmar_senha:
                raise ValidationError({"confirmar_senha": "As senhas não coincidem."})

                                                                   

        return cleaned_data

    def save(self, commit=True):
        partner = super().save(commit=False)
        senha = self.cleaned_data.get("senha")

        if senha:
            partner.set_password(senha)
        elif not partner.pk:
                                                                             
            partner.set_password("parceiro123")                                   
        elif partner.pk and not senha:
                                                                            
            partner_original = Partner.objects.get(pk=partner.pk)
            partner.senha = partner_original.senha

        if self.user and not partner.criado_por_id:
            partner.criado_por = self.user

        if commit:
            partner.save()

        return partner

