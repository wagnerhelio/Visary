from django.conf import settings
from django.db import models

from .permission_models import ConsultancyUser


class ProcessStatus(models.Model):
    visa_type = models.ForeignKey(
        "system.VisaType",
        on_delete=models.SET_NULL,
        related_name="process_statuses",
        verbose_name="Tipo de Visto",
        null=True,
        blank=True,
    )
    name = models.CharField("Nome do Status", max_length=100)
    default_deadline_days = models.PositiveIntegerField(
        "Prazo Padrão (dias)",
        default=0,
    )
    order = models.PositiveIntegerField("Ordem", default=0)
    is_active = models.BooleanField("Ativo", default=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("order", "name")
        verbose_name = "Status de Processo"
        verbose_name_plural = "Status de Processos"

    def __str__(self):
        if self.visa_type:
            return f"{self.visa_type.name} - {self.name}"
        return self.name


class Process(models.Model):
    trip = models.ForeignKey(
        "system.Trip",
        on_delete=models.CASCADE,
        related_name="processes",
        verbose_name="Viagem",
    )
    client = models.ForeignKey(
        "system.ConsultancyClient",
        on_delete=models.CASCADE,
        related_name="processes",
        verbose_name="Cliente",
    )
    notes = models.TextField("Observações", blank=True)
    assigned_advisor = models.ForeignKey(
        ConsultancyUser,
        on_delete=models.PROTECT,
        related_name="advised_processes",
        verbose_name="Assessor responsável",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_processes",
        verbose_name="Criado por",
    )
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Processo"
        verbose_name_plural = "Processos"
        unique_together = [("trip", "client")]

    def __str__(self):
        return f"{self.client.full_name} - {self.trip}"

    @property
    def completed_stages(self):
        return self.stages.filter(completed=True).count()

    @property
    def total_stages(self):
        return self.stages.count()

    @property
    def progress_percentage(self):
        if self.total_stages == 0:
            return 0
        if self.stages.filter(status__name__iexact="Processo finalizado", completed=True).exists():
            return 100
        if self.stages.filter(status__name__iexact="Processo cancelado", completed=True).exists():
            return 100
        return int((self.completed_stages / self.total_stages) * 100)


class TripProcessStatus(models.Model):
    trip = models.ForeignKey(
        "system.Trip",
        on_delete=models.CASCADE,
        related_name="available_statuses",
        verbose_name="Viagem",
    )
    status = models.ForeignKey(
        ProcessStatus,
        on_delete=models.CASCADE,
        related_name="related_trips",
        verbose_name="Status (Etapa)",
    )
    is_active = models.BooleanField("Ativo", default=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        unique_together = ("trip", "status")
        ordering = ("status__order", "status__name")
        verbose_name = "Etapa de Viagem"
        verbose_name_plural = "Etapas de Viagem"

    def __str__(self):
        return f"{self.trip} - {self.status}"


class ProcessStage(models.Model):
    process = models.ForeignKey(
        Process,
        on_delete=models.CASCADE,
        related_name="stages",
        verbose_name="Processo",
    )
    status = models.ForeignKey(
        ProcessStatus,
        on_delete=models.PROTECT,
        related_name="process_stages",
        verbose_name="Status (Etapa)",
    )
    completed = models.BooleanField("Concluída", default=False)
    deadline_days = models.PositiveIntegerField("Prazo (dias)", default=0)
    completion_date = models.DateField(
        "Data de Conclusão",
        null=True,
        blank=True,
    )
    notes = models.TextField("Observações", blank=True)
    order = models.PositiveIntegerField("Ordem", default=0)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("order", "status__name")
        verbose_name = "Etapa do Processo"
        verbose_name_plural = "Etapas do Processo"
        unique_together = [("process", "status")]

    def __str__(self):
        icon = "✓" if self.completed else "○"
        return f"{icon} {self.status.name} - {self.process}"

    def calculate_deadline_date(self):
        if not self.deadline_days:
            return None
        from datetime import timedelta
        base_date = self.process.client.created_at.date()
        return base_date + timedelta(days=self.deadline_days)
