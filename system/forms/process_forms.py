import logging

from django import forms
from django.contrib.auth.models import User
from django.db.models import Q

from system.models import (
    ConsultancyClient,
    ConsultancyUser,
    Process,
    ProcessStage,
    ProcessStatus,
    Trip,
    TripClient,
    TripProcessStatus,
)

logger = logging.getLogger(__name__)


def get_available_statuses_for_trip(trip_id):
    if not trip_id:
        return []

    try:
        trip = Trip.objects.only("id", "visa_type_id").get(pk=trip_id)
    except (Trip.DoesNotExist, ValueError, TypeError):
        return []

    trip_statuses = list(
        TripProcessStatus.objects.filter(trip=trip, is_active=True)
        .select_related("status")
        .order_by("status__order", "status__name")
    )
    if trip_statuses:
        return [trip_status.status for trip_status in trip_statuses]

    status_filter = Q(visa_type__isnull=True)
    if trip.visa_type_id:
        status_filter |= Q(visa_type_id=trip.visa_type_id)

    return list(
        ProcessStatus.objects.filter(status_filter, is_active=True)
        .order_by("order", "name")
    )


class ProcessForm(forms.ModelForm):
    class Meta:
        model = Process
        fields = ("trip", "client", "notes", "assigned_advisor")
        widgets = {
            "trip": forms.Select(attrs={"class": "input"}),
            "client": forms.Select(attrs={"class": "input"}),
            "notes": forms.Textarea(attrs={"class": "input", "rows": 3}),
            "assigned_advisor": forms.Select(attrs={"class": "input"}),
        }

    selected_stages = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Etapas do Processo",
    )

    def __init__(self, *args, user=None, client_id=None, trip_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user
        self._trip_id = trip_id

        trip_id_for_stages = self._resolve_trip_id(trip_id)
        self._setup_stage_choices(trip_id_for_stages)
        self._setup_trip_queryset(client_id)
        self._setup_client_queryset(client_id, trip_id)
        self._setup_advisor_queryset(user)

    def _resolve_trip_id(self, trip_id):
        if trip_id:
            return trip_id
        if self.data:
            raw = self.data.get("trip") or self.data.get("trip_hidden")
            if raw:
                try:
                    return int(raw)
                except (ValueError, TypeError):
                    logger.warning("trip_hidden/trip inválido: %r", raw)
        return None

    def _setup_stage_choices(self, trip_id):
        if not trip_id:
            self.fields["selected_stages"].widget = forms.HiddenInput()
            self.fields["selected_stages"].choices = []
            return
        statuses = get_available_statuses_for_trip(trip_id)
        choices = [(status.pk, status.name) for status in statuses]
        self.fields["selected_stages"].widget = forms.CheckboxSelectMultiple()
        self.fields["selected_stages"].choices = choices
        if not self.instance.pk and not self.data:
            self.fields["selected_stages"].initial = [str(pk) for pk, _ in choices]

    def _setup_trip_queryset(self, client_id):
        trips_qs = Trip.objects.select_related(
            "destination_country", "visa_type"
        ).order_by("-planned_departure_date")

        if client_id:
            try:
                client = ConsultancyClient.objects.get(pk=client_id)
                trips_qs = trips_qs.filter(clients=client).distinct()
            except ConsultancyClient.DoesNotExist:
                logger.warning("ConsultancyClient não encontrado: client_id=%r", client_id)

        self.fields["trip"].queryset = trips_qs
        self.fields["trip"].label_from_instance = self._trip_label

        if self._trip_id and not self.instance.pk:
            try:
                trip_id_int = int(self._trip_id)
                self.fields["trip"].initial = trip_id_int
                self.fields["trip"].widget.attrs.update(
                    {"disabled": True, "style": "opacity: 0.6; cursor: not-allowed;"}
                )
                self.fields["trip_hidden"] = forms.IntegerField(
                    widget=forms.HiddenInput(), initial=trip_id_int, required=False
                )
            except (ValueError, TypeError):
                logger.warning("Falha ao converter trip_id=%r", self._trip_id)

    @staticmethod
    def _trip_label(obj):
        country = obj.destination_country.name if obj.destination_country else "N/A"
        visa = obj.visa_type.name if obj.visa_type else "N/A"
        date = obj.planned_departure_date.strftime("%d/%m/%Y") if obj.planned_departure_date else "N/A"
        return f"{country} - {visa} - {date}"

    def _setup_client_queryset(self, client_id, trip_id):
        clients_qs = ConsultancyClient.objects.all().order_by("first_name")

        if trip_id:
            try:
                trip_obj = Trip.objects.get(pk=trip_id)
                client_ids = set(trip_obj.clients.values_list("pk", flat=True))
                related_trip_ids = TripClient.objects.filter(
                    client_id__in=client_ids
                ).values_list("trip_id", flat=True).distinct()
                related_client_ids = TripClient.objects.filter(
                    trip_id__in=related_trip_ids
                ).values_list("client_id", flat=True)
                client_ids.update(related_client_ids)
                clients_qs = clients_qs.filter(pk__in=client_ids).distinct()
            except Trip.DoesNotExist:
                logger.warning("Trip não encontrada: trip_id=%r", trip_id)

        self.fields["client"].queryset = clients_qs

        if client_id and not self.instance.pk:
            try:
                self.fields["client"].initial = int(client_id)
            except (ValueError, TypeError):
                logger.warning("Falha ao converter client_id=%r", client_id)

    def _setup_advisor_queryset(self, user):
        self.fields["assigned_advisor"].queryset = (
            ConsultancyUser.objects.filter(is_active=True)
            .order_by("name")
            .select_related("profile")
        )
        if user and not user.is_superuser and not user.is_staff:
            consultant = (
                ConsultancyUser.objects.filter(email__iexact=user.email, is_active=True)
                .order_by("-updated_at")
                .first()
            )
            if consultant:
                self.fields["assigned_advisor"].initial = consultant.pk

    def full_clean(self):
        if self.data and hasattr(self, "fields"):
            self._inject_hidden_field("trip_hidden", "trip")
            self._inject_hidden_field("client_hidden", "client")
        super().full_clean()

    def _inject_hidden_field(self, hidden_name, target_name):
        if hidden_name not in self.fields or not self.data.get(hidden_name):
            return
        try:
            value = int(self.data.get(hidden_name))
            if target_name in self.fields and not self.data.get(target_name):
                self.data = self.data.copy()
                self.data[target_name] = str(value)
        except (ValueError, TypeError):
            pass

    def clean(self):
        cleaned_data = super().clean()
        self._resolve_hidden_value(cleaned_data, "trip_hidden", "trip", Trip)
        self._resolve_hidden_value(cleaned_data, "client_hidden", "client", ConsultancyClient)
        self._validate_client_trip_link(cleaned_data)
        self._validate_unique_process(cleaned_data)
        return cleaned_data

    def _resolve_hidden_value(self, cleaned_data, hidden_name, target_name, model_class):
        if cleaned_data.get(target_name):
            return
        if hidden_name not in self.fields:
            return
        hidden_val = self.data.get(hidden_name)
        obj_id = cleaned_data.get(hidden_name)
        if not obj_id:
            if hidden_val not in (None, ""):
                self.add_error(target_name, f"{target_name.capitalize()} inválido(a).")
                return
            field = self.fields.get(hidden_name)
            obj_id = field.initial if field else None
        if obj_id:
            try:
                cleaned_data[target_name] = model_class.objects.get(pk=obj_id)
            except (model_class.DoesNotExist, ValueError, TypeError):
                self.add_error(target_name, f"{target_name.capitalize()} inválido(a).")

    def _validate_client_trip_link(self, cleaned_data):
        trip = cleaned_data.get("trip")
        client = cleaned_data.get("client")
        if not trip or not client:
            return
        is_linked = (
            client in trip.clients.all()
            or TripClient.objects.filter(trip=trip, trip_primary_client=client).exists()
            or TripClient.objects.filter(trip=trip, client=client).exists()
        )
        if not is_linked:
            self.add_error(
                "client",
                "O cliente selecionado não está vinculado à viagem escolhida. "
                "Por favor, vincule o cliente à viagem antes de criar o processo.",
            )

    def _validate_unique_process(self, cleaned_data):
        trip = cleaned_data.get("trip")
        client = cleaned_data.get("client")
        if not trip or not client:
            return
        qs = Process.objects.filter(trip=trip, client=client)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            self.add_error(
                "client",
                "Já existe um processo cadastrado para este cliente nesta viagem.",
            )

    def save(self, commit=True):
        process = super().save(commit=False)
        if self._user and not process.created_by_id:
            process.created_by = self._user
        if commit:
            process.save()
            self._create_stages(process)
        return process

    def _create_stages(self, process):
        selected = self.cleaned_data.get("selected_stages", [])
        if selected:
            statuses = ProcessStatus.objects.filter(pk__in=[int(s) for s in selected])
        else:
            statuses = get_available_statuses_for_trip(process.trip_id)

        for status in statuses:
            ProcessStage.objects.get_or_create(
                process=process,
                status=status,
                defaults={
                    "deadline_days": status.default_deadline_days or 0,
                    "order": status.order,
                },
            )


class ProcessStageForm(forms.ModelForm):
    class Meta:
        model = ProcessStage
        fields = ("completed", "deadline_days", "completion_date", "notes")
        widgets = {
            "completed": forms.CheckboxInput(attrs={"class": "input"}),
            "deadline_days": forms.NumberInput(
                attrs={"class": "input", "min": "0", "step": "1"}
            ),
            "completion_date": forms.DateInput(
                attrs={"class": "input", "type": "date"}
            ),
            "notes": forms.Textarea(attrs={"class": "input", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["deadline_days"].required = False
