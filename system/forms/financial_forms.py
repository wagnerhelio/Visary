from django import forms

from system.models import FinancialRecord


class FinancialSettlementForm(forms.ModelForm):
    class Meta:
        model = FinancialRecord
        fields = ("payment_date", "status", "notes")
        widgets = {
            "payment_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "status": forms.Select(attrs={"class": "form-control"}),
            "notes": forms.Textarea(
                attrs={"rows": 3, "class": "form-control", "placeholder": "Observações sobre o pagamento"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_date"].required = True
        self.fields["status"].required = True
