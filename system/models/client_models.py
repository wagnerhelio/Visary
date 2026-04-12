from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models

from .permission_models import ConsultancyUser


PASSPORT_TYPE_CHOICES = [
    ("regular", "Passaporte Comum/Regular"),
    ("diplomatic", "Passaporte Diplomático"),
    ("service", "Passaporte de Serviço"),
    ("other", "Outro"),
]


class ConsultancyClient(models.Model):
    assigned_advisor = models.ForeignKey(
        ConsultancyUser,
        on_delete=models.PROTECT,
        related_name="advised_clients",
        verbose_name="Assessor responsável",
    )
    first_name = models.CharField("Nome", max_length=100)
    last_name = models.CharField("Sobrenome", max_length=100)
    cpf = models.CharField(
        "CPF",
        max_length=14,
        unique=True,
        help_text="CPF utilizado para login. Formato: 000.000.000-00",
    )
    birth_date = models.DateField("Data de nascimento")
    nationality = models.CharField("Nacionalidade", max_length=100)
    phone = models.CharField("Telefone", max_length=20)
    secondary_phone = models.CharField(
        "Telefone secundário",
        max_length=20,
        blank=True,
    )
    email = models.EmailField("E-mail", blank=True, default="")
    password = models.CharField("Senha de acesso", max_length=128)
    zip_code = models.CharField("CEP", max_length=9, blank=True)
    street = models.CharField("Logradouro", max_length=200, blank=True)
    street_number = models.CharField("Número", max_length=20, blank=True)
    complement = models.CharField("Complemento", max_length=100, blank=True)
    district = models.CharField("Bairro", max_length=100, blank=True)
    city = models.CharField("Cidade", max_length=100, blank=True)
    state = models.CharField("UF", max_length=2, blank=True)
    notes = models.TextField("Observações", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_clients",
        verbose_name="Criado por",
    )
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)
    referring_partner = models.ForeignKey(
        "system.Partner",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referred_clients",
        verbose_name="Parceiro Indicador",
    )
    primary_client = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="dependents",
        verbose_name="Cliente Principal",
    )
    step_personal_data = models.BooleanField("Etapa: Dados Pessoais", default=False)
    step_address = models.BooleanField("Etapa: Endereço", default=False)
    step_members = models.BooleanField("Etapa: Membros", default=False)
    step_passport = models.BooleanField("Etapa: Passaporte", default=False)
    passport_type = models.CharField(
        "Tipo de Passaporte",
        max_length=20,
        choices=PASSPORT_TYPE_CHOICES,
        blank=True,
        null=True,
    )
    passport_type_other = models.CharField(
        "Outro tipo de passaporte",
        max_length=100,
        blank=True,
    )
    passport_number = models.CharField(
        "Número do passaporte válido",
        max_length=50,
        blank=True,
    )
    passport_issuing_country = models.CharField(
        "País que emitiu o passaporte",
        max_length=100,
        blank=True,
    )
    passport_issue_date = models.DateField(
        "Data de emissão",
        null=True,
        blank=True,
    )
    passport_expiry_date = models.DateField(
        "Válido até",
        null=True,
        blank=True,
    )
    passport_authority = models.CharField(
        "Autoridade",
        max_length=100,
        blank=True,
    )
    passport_issuing_city = models.CharField(
        "Cidade onde foi emitido",
        max_length=100,
        blank=True,
    )
    passport_stolen = models.BooleanField(
        "Já teve algum passaporte roubado?",
        default=False,
    )

    class Meta:
        ordering = ("-created_at", "first_name")
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.full_name

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        if not self.password:
            return False
        try:
            if check_password(raw_password, self.password):
                return True
        except ValueError:
            pass
        if self.password == raw_password:
            self.set_password(raw_password)
            self.save(update_fields=["password", "updated_at"])
            return True
        return False

    @property
    def is_primary(self):
        return self.primary_client is None

    @property
    def is_dependent(self):
        return self.primary_client is not None

    @property
    def total_dependents(self):
        return self.dependents.count()

    def role_in_trip(self, trip):
        from .travel_models import TripClient

        try:
            tc = TripClient.objects.get(trip=trip, client=self)
            return tc.role
        except TripClient.DoesNotExist:
            return None

    def is_primary_in_trip(self, trip):
        return self.role_in_trip(trip) == "primary"

    def dependents_in_trip(self, trip):
        return ConsultancyClient.objects.filter(
            client_trips__trip=trip,
            client_trips__trip_primary_client=self,
            client_trips__role="dependent",
        )

    def primary_in_trip(self, trip):
        from .travel_models import TripClient

        try:
            tc = TripClient.objects.select_related("trip_primary_client").get(
                trip=trip, client=self
            )
            return tc.trip_primary_client
        except TripClient.DoesNotExist:
            return None

    @property
    def step_progress(self):
        steps = [
            self.step_personal_data,
            self.step_address,
            self.step_passport,
            self.step_members,
        ]
        completed = sum(steps)
        return int((completed / len(steps)) * 100) if steps else 0


class Reminder(models.Model):
    client = models.ForeignKey(
        ConsultancyClient,
        on_delete=models.CASCADE,
        related_name="reminders",
        verbose_name="Cliente",
    )
    text = models.CharField("Lembrete", max_length=500)
    reminder_date = models.DateField("Data do lembrete", null=True, blank=True)
    completed = models.BooleanField("Concluído", default=False)
    created_by = models.ForeignKey(
        ConsultancyUser,
        on_delete=models.PROTECT,
        related_name="created_reminders",
        verbose_name="Criado por",
    )
    created_at = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        ordering = ("completed", "-created_at")
        verbose_name = "Lembrete"
        verbose_name_plural = "Lembretes"

    def __str__(self):
        return self.text[:60]
