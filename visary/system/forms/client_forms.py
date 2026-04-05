from __future__ import annotations

import contextlib

from django import forms
from django.contrib.auth import get_user_model

from system.models import ConsultancyClient, ConsultancyUser, Partner

User = get_user_model()


class ConsultancyClientForm(forms.ModelForm):
    confirm_password = forms.CharField(
        label="Confirme a senha",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Repita a senha de acesso",
                "data-lpignore": "true",
                "data-1p-ignore": "true",
                "data-bwignore": "true",
                "data-form-type": "other",
            }
        ),
    )

    class Meta:
        model = ConsultancyClient
        fields = (
            "assigned_advisor",
            "first_name",
            "last_name",
            "cpf",
            "birth_date",
            "nationality",
            "phone",
            "secondary_phone",
            "email",
            "password",
            "referring_partner",
            "zip_code",
            "street",
            "street_number",
            "complement",
            "district",
            "city",
            "state",
            "passport_type",
            "passport_type_other",
            "passport_number",
            "passport_issuing_country",
            "passport_issue_date",
            "passport_expiry_date",
            "passport_authority",
            "passport_issuing_city",
            "passport_stolen",
            "notes",
        )
        widgets = {
            "assigned_advisor": forms.Select(attrs={"class": "input"}),
            "referring_partner": forms.Select(
                attrs={"class": "input", "data-partner-select": "true"}
            ),
            "first_name": forms.TextInput(
                attrs={"placeholder": "Nome", "autocomplete": "given-name"}
            ),
            "last_name": forms.TextInput(
                attrs={"placeholder": "Sobrenome", "autocomplete": "family-name"}
            ),
            "cpf": forms.TextInput(
                attrs={
                    "placeholder": "000.000.000-00",
                    "maxlength": "14",
                    "data-cpf-input": "true",
                    "autocomplete": "off",
                }
            ),
            "birth_date": forms.DateInput(
                attrs={"type": "date", "placeholder": "dd/mm/aaaa"},
                format="%Y-%m-%d",
            ),
            "nationality": forms.TextInput(
                attrs={"placeholder": "Nacionalidade", "autocomplete": "country-name"}
            ),
            "phone": forms.TextInput(
                attrs={"placeholder": "Telefone principal", "autocomplete": "tel"}
            ),
            "secondary_phone": forms.TextInput(
                attrs={"placeholder": "Telefone secundário", "autocomplete": "tel"}
            ),
            "email": forms.EmailInput(
                attrs={
                    "placeholder": "email@dominio.com",
                    "autocomplete": "email",
                    "data-lpignore": "true",
                    "data-1p-ignore": "true",
                    "data-bwignore": "true",
                }
            ),
            "password": forms.PasswordInput(
                attrs={
                    "autocomplete": "new-password",
                    "placeholder": "Senha de acesso do cliente",
                    "data-lpignore": "true",
                    "data-1p-ignore": "true",
                    "data-bwignore": "true",
                    "data-form-type": "other",
                }
            ),
            "zip_code": forms.TextInput(
                attrs={
                    "placeholder": "00000-000",
                    "maxlength": "9",
                    "class": "cep-input",
                    "autocomplete": "postal-code",
                }
            ),
            "street": forms.TextInput(
                attrs={"placeholder": "Rua, Avenida, etc.", "autocomplete": "street-address"}
            ),
            "street_number": forms.TextInput(
                attrs={"placeholder": "Número", "autocomplete": "off"}
            ),
            "complement": forms.TextInput(
                attrs={"placeholder": "Apto, Bloco, etc.", "autocomplete": "off"}
            ),
            "district": forms.TextInput(
                attrs={"placeholder": "Bairro", "autocomplete": "address-level2"}
            ),
            "city": forms.TextInput(
                attrs={"placeholder": "Cidade", "autocomplete": "address-level1"}
            ),
            "state": forms.TextInput(
                attrs={
                    "placeholder": "UF",
                    "maxlength": "2",
                    "style": "text-transform: uppercase;",
                    "autocomplete": "address-level1",
                }
            ),
            "passport_type": forms.Select(attrs={"class": "input"}),
            "passport_type_other": forms.TextInput(
                attrs={"placeholder": "Especifique o tipo de passaporte"}
            ),
            "passport_number": forms.TextInput(
                attrs={"placeholder": "Número do passaporte válido"}
            ),
            "passport_issuing_country": forms.TextInput(
                attrs={"placeholder": "País que emitiu o passaporte"}
            ),
            "passport_issue_date": forms.DateInput(
                attrs={"type": "date", "placeholder": "dd/mm/aaaa"},
                format="%Y-%m-%d",
            ),
            "passport_expiry_date": forms.DateInput(
                attrs={"type": "date", "placeholder": "dd/mm/aaaa"},
                format="%Y-%m-%d",
            ),
            "passport_authority": forms.TextInput(
                attrs={"placeholder": "Autoridade emissora"}
            ),
            "passport_issuing_city": forms.TextInput(
                attrs={"placeholder": "Cidade onde foi emitido"}
            ),
            "passport_stolen": forms.CheckboxInput(),
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Informações adicionais sobre o atendimento",
                }
            ),
        }

    def __init__(self, *args, user=None, primary_client=None, use_primary_data=False, **kwargs):
        initial_dict = kwargs.get("initial", {})
        initial_advisor = initial_dict.get("assigned_advisor") if initial_dict else None
        if initial_advisor:
            try:
                initial_advisor = int(initial_advisor) if isinstance(initial_advisor, str) else initial_advisor
            except (ValueError, TypeError):
                initial_advisor = None

        super().__init__(*args, **kwargs)
        self._user = user
        self._primary_client = primary_client
        self._use_primary_data = use_primary_data

        if use_primary_data:
            for field_name in ("password", "confirm_password"):
                if field_name in self.fields:
                    self.fields[field_name].required = False
                    self.fields[field_name].widget.attrs["data-use-primary-data"] = "true"

        self._setup_advisor_queryset(initial_advisor)
        self._setup_partner_queryset()
        self._setup_passport_fields()
        self.fields["email"].required = False

    def _setup_advisor_queryset(self, initial_advisor):
        self.fields["assigned_advisor"].queryset = (
            ConsultancyUser.objects.filter(is_active=True)
            .order_by("name")
            .select_related("profile")
        )
        if self._user and not self.instance.pk and not initial_advisor:
            consultant = (
                ConsultancyUser.objects.filter(email__iexact=self._user.email, is_active=True)
                .order_by("-updated_at")
                .first()
            )
            if consultant and self._primary_client is None:
                self.fields["assigned_advisor"].initial = consultant.pk
        elif initial_advisor:
            self.fields["assigned_advisor"].initial = initial_advisor

    def _setup_partner_queryset(self):
        self.fields["referring_partner"].queryset = (
            Partner.objects.filter(is_active=True).order_by("company_name", "contact_name")
        )
        self.fields["referring_partner"].required = False
        self.fields["referring_partner"].empty_label = "Nenhum parceiro"

    def _setup_passport_fields(self):
        self.fields["passport_type"].required = False
        self.fields["passport_type"].choices = [
            ("", "Selecione o tipo de passaporte"),
            ("regular", "Passaporte Comum/Regular"),
            ("diplomatic", "Passaporte Diplomático"),
            ("service", "Passaporte de Serviço"),
            ("other", "Outro"),
        ]
        self.fields["passport_type_other"].required = False

    def full_clean(self):
        if self._use_primary_data:
            for field_name in ("password", "confirm_password"):
                if field_name in self.fields:
                    self.fields[field_name].required = False
        super().full_clean()

    def clean_confirm_password(self):
        if self._use_primary_data:
            return ""
        password = self.cleaned_data.get("password", "")
        confirm = self.cleaned_data.get("confirm_password", "")
        if not password and not confirm and self.instance.pk:
            return confirm
        if password and confirm and password != confirm:
            raise forms.ValidationError("As senhas informadas não conferem.")
        return confirm

    def clean_password(self):
        if self._use_primary_data:
            return ""
        password = self.cleaned_data.get("password", "")
        if not password and not self.instance.pk:
            raise forms.ValidationError("A senha é obrigatória para novos clientes.")
        return password

    def clean_cpf(self):
        cpf = self.cleaned_data.get("cpf", "")
        digits = "".join(c for c in cpf if c.isdigit())
        if len(digits) != 11:
            raise forms.ValidationError("CPF deve conter 11 dígitos.")
        if len(set(digits)) == 1:
            raise forms.ValidationError("CPF inválido.")
        self._validate_cpf_digits(digits)
        formatted = f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
        queryset = ConsultancyClient.objects.filter(cpf__in=[digits, formatted])
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("Este CPF já está cadastrado.")
        return digits

    def _validate_cpf_digits(self, digits):
        def calc_digit(partial):
            weight = len(partial) + 1
            total = sum(int(d) * (weight - i) for i, d in enumerate(partial))
            remainder = total % 11
            return 0 if remainder < 2 else 11 - remainder

        if calc_digit(digits[:9]) != int(digits[9]):
            raise forms.ValidationError("CPF inválido.")
        if calc_digit(digits[:10]) != int(digits[10]):
            raise forms.ValidationError("CPF inválido.")

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if not email:
            return email
        queryset = ConsultancyClient.objects.filter(email=email)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            existing = queryset.first()
            raise forms.ValidationError(
                f"Este email já está em uso por outro cliente: {existing.full_name}."
            )
        return email

    def clean_passport_type_other(self):
        passport_type = self.cleaned_data.get("passport_type")
        passport_type_other = self.cleaned_data.get("passport_type_other")
        if passport_type == "other" and not passport_type_other:
            raise forms.ValidationError("Especifique o tipo de passaporte quando selecionar 'Outro'.")
        return passport_type_other

    def save(self, commit=True):
        client = super().save(commit=False)
        if password := self.cleaned_data.get("password"):
            client.set_password(password)
        elif client.pk:
            with contextlib.suppress(ConsultancyClient.DoesNotExist):
                current = ConsultancyClient.objects.get(pk=client.pk)
                client.password = current.password
        if self._user and not client.created_by_id:
            client.created_by = self._user
        if commit:
            client.save()
        return client
