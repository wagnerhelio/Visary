from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model

from system.models import ConsultancyClient, ConsultancyUser, DestinationCountry, Trip, VisaType

User = get_user_model()


class DestinationCountryForm(forms.ModelForm):
    class Meta:
        model = DestinationCountry
        fields = ("name", "iso_code", "is_active")
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Nome do país", "autocomplete": "country-name"}
            ),
            "iso_code": forms.TextInput(
                attrs={"placeholder": "Ex: BRA, USA, FRA", "maxlength": "3", "style": "text-transform: uppercase;"}
            ),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user

    def save(self, commit=True):
        country = super().save(commit=False)
        if commit:
            country.save()
        return country


class VisaTypeForm(forms.ModelForm):
    class Meta:
        model = VisaType
        fields = ("destination_country", "name", "description", "is_active")
        widgets = {
            "destination_country": forms.Select(attrs={"class": "input"}),
            "name": forms.TextInput(
                attrs={"placeholder": "Ex: Turismo, Negócios, Estudante"}
            ),
            "description": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Descrição do tipo de visto"}
            ),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user
        self.fields["destination_country"].queryset = (
            DestinationCountry.objects.filter(is_active=True).order_by("name")
        )

    def save(self, commit=True):
        visa_type = super().save(commit=False)
        if commit:
            visa_type.save()
        return visa_type


class TripForm(forms.ModelForm):
    class Meta:
        model = Trip
        fields = (
            "assigned_advisor",
            "destination_country",
            "visa_type",
            "planned_departure_date",
            "planned_return_date",
            "advisory_fee",
            "clients",
            "notes",
        )
        widgets = {
            "assigned_advisor": forms.Select(attrs={"class": "input"}),
            "destination_country": forms.Select(attrs={"class": "input"}),
            "visa_type": forms.Select(attrs={"class": "input"}),
            "planned_departure_date": forms.DateInput(
                attrs={"type": "date", "placeholder": "dd/mm/aaaa"}
            ),
            "planned_return_date": forms.DateInput(
                attrs={"type": "date", "placeholder": "dd/mm/aaaa"}
            ),
            "advisory_fee": forms.NumberInput(
                attrs={"placeholder": "0.00", "step": "0.01", "min": "0"}
            ),
            "clients": forms.SelectMultiple(attrs={"class": "input"}),
            "notes": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Informações adicionais sobre a viagem"}
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user
        self.fields["assigned_advisor"].queryset = (
            ConsultancyUser.objects.filter(is_active=True)
            .order_by("name")
            .select_related("profile")
        )
        self.fields["destination_country"].queryset = (
            DestinationCountry.objects.filter(is_active=True).order_by("name")
        )
        self.fields["visa_type"].queryset = (
            VisaType.objects.filter(is_active=True).select_related("destination_country")
        )
        self.fields["clients"].queryset = ConsultancyClient.objects.all().order_by("first_name")

        if user and not user.is_superuser and not user.is_staff:
            consultant = (
                ConsultancyUser.objects.filter(email__iexact=user.email, is_active=True)
                .order_by("-updated_at")
                .first()
            )
            if consultant:
                self.fields["assigned_advisor"].initial = consultant.pk

    def clean(self):
        cleaned_data = super().clean()
        departure = cleaned_data.get("planned_departure_date")
        return_date = cleaned_data.get("planned_return_date")
        if departure and return_date and return_date < departure:
            raise forms.ValidationError(
                "A data de retorno não pode ser anterior à data de viagem."
            )
        return cleaned_data

    def save(self, commit=True):
        trip = super().save(commit=False)
        if self._user and not trip.created_by_id:
            trip.created_by = self._user
        if commit:
            trip.save()
            self.save_m2m()
        return trip
