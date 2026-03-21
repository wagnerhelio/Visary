   
                                    
   

from django import forms

from system.models import Financeiro


class DarBaixaFinanceiroForm(forms.ModelForm):
                                                                           

    class Meta:
        model = Financeiro
        fields = ("data_pagamento", "status", "observacoes")
        widgets = {
            "data_pagamento": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "status": forms.Select(
                attrs={"class": "form-control"}
            ),
            "observacoes": forms.Textarea(
                attrs={"rows": 3, "class": "form-control", "placeholder": "Observações sobre o pagamento"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_pagamento"].required = True
        self.fields["status"].required = True

