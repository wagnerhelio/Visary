import logging

from django.conf import settings
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .permission_models import ConsultancyUser
from .travel_models import Trip

logger = logging.getLogger("visary.financial")


class FinancialStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    PAID = "paid", "Pago"
    CANCELLED = "cancelled", "Cancelado"


class FinancialRecord(models.Model):
    trip = models.ForeignKey(
        Trip,
        on_delete=models.CASCADE,
        related_name="financial_records",
        verbose_name="Viagem",
    )
    client = models.ForeignKey(
        "system.ConsultancyClient",
        on_delete=models.PROTECT,
        related_name="financial_records",
        verbose_name="Cliente",
        null=True,
        blank=True,
    )
    assigned_advisor = models.ForeignKey(
        ConsultancyUser,
        on_delete=models.PROTECT,
        related_name="financial_records",
        verbose_name="Assessor responsável",
    )
    amount = models.DecimalField(
        "Valor",
        max_digits=10,
        decimal_places=2,
        default=0.00,
    )
    payment_date = models.DateField(
        "Data do pagamento",
        null=True,
        blank=True,
    )
    status = models.CharField(
        "Status",
        max_length=20,
        choices=FinancialStatus.choices,
        default=FinancialStatus.PENDING,
    )
    notes = models.TextField("Observações", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_financial_records",
        verbose_name="Criado por",
    )
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Registro Financeiro"
        verbose_name_plural = "Registros Financeiros"
        unique_together = [("trip", "client")]

    def __str__(self):
        client_name = self.client.full_name if self.client else "N/A"
        return f"{client_name} - {self.amount} - {self.get_status_display()}"


@receiver(post_save, sender=FinancialRecord)
def propagate_payment_to_dependents(sender, instance, created, **kwargs):
    from .travel_models import TripClient

    if created or instance.status != FinancialStatus.PAID:
        return

    principal = instance.client
    if principal is None or instance.trip is None:
        return

    try:
        tc_principal = TripClient.objects.get(trip=instance.trip, client=principal)
    except TripClient.DoesNotExist:
        return

    if tc_principal.role != "primary":
        return

    dependent_tcs = TripClient.objects.filter(
        trip=instance.trip,
        trip_primary_client=principal,
        role="dependent",
    ).select_related("client")

    deps_list = list(dependent_tcs)
    if not deps_list:
        return

    logger.info(
        "Propagando PAGO do principal '%s' (pk=%s) para %d dependente(s), viagem pk=%s",
        principal.full_name, principal.pk, len(deps_list), instance.trip.pk,
    )

    with transaction.atomic():
        for tc_dep in deps_list:
            dep = tc_dep.client
            try:
                f_dep = FinancialRecord.objects.select_for_update().get(
                    client=dep, trip=instance.trip
                )
            except FinancialRecord.DoesNotExist:
                logger.warning(
                    "Registro financeiro não encontrado para dependente '%s' (pk=%s), viagem pk=%s",
                    dep.full_name, dep.pk, instance.trip.pk,
                )
                continue
            if f_dep.status != FinancialStatus.PAID:
                f_dep.status = FinancialStatus.PAID
                f_dep.updated_at = timezone.now()
                f_dep.save(update_fields=["status", "updated_at"])
                logger.info(
                    "Dependente '%s' (pk=%s) marcado como PAGO, viagem pk=%s",
                    dep.full_name, dep.pk, instance.trip.pk,
                )
