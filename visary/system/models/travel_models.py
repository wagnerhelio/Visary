from django.conf import settings
from django.db import models

from .permission_models import ConsultancyUser


class DestinationCountry(models.Model):
    name = models.CharField("Nome do país", max_length=100, unique=True)
    iso_code = models.CharField("Código ISO", max_length=3, blank=True)
    is_active = models.BooleanField("Ativo", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_destination_countries",
        verbose_name="Criado por",
    )
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "País de Destino"
        verbose_name_plural = "Países de Destino"

    def __str__(self):
        return self.name


class VisaType(models.Model):
    destination_country = models.ForeignKey(
        DestinationCountry,
        on_delete=models.CASCADE,
        related_name="visa_types",
        verbose_name="País de destino",
    )
    name = models.CharField("Nome do visto", max_length=100)
    description = models.TextField("Descrição", blank=True)
    is_active = models.BooleanField("Ativo", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_visa_types",
        verbose_name="Criado por",
    )
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("destination_country", "name")
        verbose_name = "Tipo de Visto"
        verbose_name_plural = "Tipos de Visto"
        unique_together = [("destination_country", "name")]

    def __str__(self):
        return f"{self.name} - {self.destination_country.name}"


class Trip(models.Model):
    assigned_advisor = models.ForeignKey(
        ConsultancyUser,
        on_delete=models.PROTECT,
        related_name="advised_trips",
        verbose_name="Assessor responsável",
    )
    destination_country = models.ForeignKey(
        DestinationCountry,
        on_delete=models.PROTECT,
        related_name="trips",
        verbose_name="País de destino",
    )
    visa_type = models.ForeignKey(
        VisaType,
        on_delete=models.PROTECT,
        related_name="trips",
        verbose_name="Tipo de visto",
    )
    planned_departure_date = models.DateField("Data prevista da viagem")
    planned_return_date = models.DateField("Data prevista de retorno")
    advisory_fee = models.DecimalField(
        "Valor assessoria Visary",
        max_digits=10,
        decimal_places=2,
        default=0.00,
    )
    clients = models.ManyToManyField(
        "system.ConsultancyClient",
        related_name="trips",
        verbose_name="Clientes vinculados",
        blank=True,
        through="TripClient",
        through_fields=("trip", "client"),
    )
    notes = models.TextField("Observações", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_trips",
        verbose_name="Criado por",
    )
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("-planned_departure_date", "-created_at")
        verbose_name = "Viagem"
        verbose_name_plural = "Viagens"

    def __str__(self):
        return f"{self.destination_country.name} - {self.planned_departure_date.strftime('%d/%m/%Y')}"


ROLE_CHOICES = [
    ("primary", "Principal"),
    ("dependent", "Dependente"),
]


class TripClient(models.Model):
    trip = models.ForeignKey(
        Trip,
        on_delete=models.CASCADE,
        related_name="trip_clients",
        verbose_name="Viagem",
    )
    client = models.ForeignKey(
        "system.ConsultancyClient",
        on_delete=models.CASCADE,
        related_name="client_trips",
        verbose_name="Cliente",
    )
    visa_type = models.ForeignKey(
        VisaType,
        on_delete=models.PROTECT,
        related_name="trip_client_visa_types",
        verbose_name="Tipo de visto",
        null=True,
        blank=True,
    )
    role = models.CharField(
        "Papel na viagem",
        max_length=20,
        choices=ROLE_CHOICES,
        default="dependent",
    )
    trip_primary_client = models.ForeignKey(
        "system.ConsultancyClient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trip_dependents",
        verbose_name="Cliente principal nesta viagem",
    )
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Cliente na Viagem"
        verbose_name_plural = "Clientes na Viagem"
        unique_together = [("trip", "client")]
        constraints = [
            models.UniqueConstraint(
                fields=["trip"],
                condition=models.Q(role="primary"),
                name="unique_primary_per_trip",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.role == "primary" and self.trip_primary_client is not None:
            raise ValidationError(
                {"trip_primary_client": "O cliente principal não pode ter um principal vinculado."}
            )
        if self.role == "dependent":
            if self.trip_primary_client is None:
                raise ValidationError(
                    {"trip_primary_client": "Dependente deve ter um cliente principal nesta viagem."}
                )
            if self.trip_primary_client_id == self.client_id:
                raise ValidationError(
                    {"trip_primary_client": "Um cliente não pode ser principal de si mesmo."}
                )

    @property
    def is_primary_in_trip(self):
        return self.role == "primary"

    @property
    def is_dependent_in_trip(self):
        return self.role == "dependent"

    def __str__(self):
        visa_str = f" - {self.visa_type}" if self.visa_type else ""
        role_str = f" ({self.get_role_display()})"
        return f"{self.client.full_name} em {self.trip}{visa_str}{role_str}"
