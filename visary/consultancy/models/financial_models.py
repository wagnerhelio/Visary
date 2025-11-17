"""
Modelos relacionados a finanças.
"""

from django.conf import settings
from django.db import models

from consultancy.models.travel_models import Viagem
from system.models import UsuarioConsultoria


class StatusFinanceiro(models.TextChoices):
    """Status possíveis para um registro financeiro."""

    PENDENTE = "pendente", "Pendente"
    PAGO = "pago", "Pago"
    CANCELADO = "cancelado", "Cancelado"


class Financeiro(models.Model):
    """Registro financeiro vinculado a uma viagem."""

    viagem = models.ForeignKey(
        Viagem,
        on_delete=models.CASCADE,
        related_name="registros_financeiros",
        verbose_name="Viagem",
    )
    cliente = models.ForeignKey(
        "consultancy.ClienteConsultoria",
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

    def __str__(self) -> str:
        cliente_nome = self.cliente.nome_usuario if self.cliente else "N/A"
        return f"{cliente_nome} - {self.valor} - {self.get_status_display()}"

