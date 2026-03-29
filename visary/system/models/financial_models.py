   
                                
   

from django.conf import settings
from django.db import models

from .permission_models import UsuarioConsultoria
from .travel_models import Viagem


class StatusFinanceiro(models.TextChoices):
                                                       

    PENDENTE = "pendente", "Pendente"
    PAGO = "pago", "Pago"
    CANCELADO = "cancelado", "Cancelado"


class Financeiro(models.Model):
                                                     

    viagem = models.ForeignKey(
        Viagem,
        on_delete=models.CASCADE,
        related_name="registros_financeiros",
        verbose_name="Viagem",
    )
    cliente = models.ForeignKey(
        "system.ClienteConsultoria",
        on_delete=models.PROTECT,
        related_name="registros_financeiros",
        verbose_name="Cliente",
        null=True,
        blank=True,
    )
    assessor_responsavel = models.ForeignKey(
        UsuarioConsultoria,
        on_delete=models.PROTECT,
        related_name="registros_financeiros",
        verbose_name="Assessor responsável",
    )
    valor = models.DecimalField(
        "Valor",
        max_digits=10,
        decimal_places=2,
        default=0.00,
    )
    data_pagamento = models.DateField(
        "Data do pagamento",
        null=True,
        blank=True,
        help_text="Data em que o pagamento foi recebido",
    )
    status = models.CharField(
        "Status",
        max_length=20,
        choices=StatusFinanceiro.choices,
        default=StatusFinanceiro.PENDENTE,
    )
    observacoes = models.TextField("Observações", blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="registros_financeiros_criados",
        verbose_name="Criado por",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("-criado_em",)
        verbose_name = "Registro Financeiro"
        verbose_name_plural = "Registros Financeiros"
        unique_together = [("viagem", "cliente")]

    def __str__(self) -> str:
        cliente_nome = self.cliente.nome_completo if self.cliente else "N/A"
        return f"{cliente_nome} - {self.valor} - {self.get_status_display()}"


import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger("visary.financial")


@receiver(post_save, sender=Financeiro)
def propagate_payment_to_dependents(sender, instance: Financeiro, created: bool, **kwargs):
    """Propaga status PAGO do cliente principal para dependentes na mesma viagem (viagem-scoped)."""
    from .travel_models import ClienteViagem

    if created:
        return
    if instance.status != StatusFinanceiro.PAGO:
        return

    principal = instance.cliente
    if principal is None:
        return

    viagem = instance.viagem
    if viagem is None:
        return

    try:
        cv_principal = ClienteViagem.objects.get(viagem=viagem, cliente=principal)
    except ClienteViagem.DoesNotExist:
        return
    if cv_principal.papel != "principal":
        return

    deps_cv = ClienteViagem.objects.filter(
        viagem=viagem,
        cliente_principal_viagem=principal,
        papel="dependente",
    ).select_related("cliente")

    deps_list = list(deps_cv)
    if not deps_list:
        return

    logger.info(
        "Propagando PAGO do principal '%s' (pk=%s) para %d dependente(s), viagem pk=%s",
        principal.nome_completo, principal.pk, len(deps_list), viagem.pk,
    )

    with transaction.atomic():
        for cv_dep in deps_list:
            dep = cv_dep.cliente
            try:
                f_dep = Financeiro.objects.select_for_update().get(
                    cliente=dep, viagem=viagem
                )
            except Financeiro.DoesNotExist:
                logger.warning(
                    "Registro financeiro não encontrado para dependente '%s' (pk=%s), viagem pk=%s",
                    dep.nome_completo, dep.pk, viagem.pk,
                )
                continue
            if f_dep.status != StatusFinanceiro.PAGO:
                f_dep.status = StatusFinanceiro.PAGO
                f_dep.atualizado_em = timezone.now()
                f_dep.save(update_fields=["status", "atualizado_em"])
                logger.info(
                    "Dependente '%s' (pk=%s) marcado como PAGO, viagem pk=%s",
                    dep.nome_completo, dep.pk, viagem.pk,
                )
