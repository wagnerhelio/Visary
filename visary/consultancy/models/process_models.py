"""
Modelos relacionados a processos de visto.
"""

from django.conf import settings
from django.db import models

from system.models import UsuarioConsultoria


class StatusProcesso(models.Model):
    """Status que um processo pode ter."""

    tipo_visto = models.ForeignKey(
        "consultancy.TipoVisto",
        on_delete=models.SET_NULL,
        related_name="status_processos",
        verbose_name="Tipo de Visto",
        help_text="Tipo de visto ao qual este status está vinculado (opcional - deixe em branco para usar em todos os tipos)",
        null=True,
        blank=True,
    )
    nome = models.CharField("Nome do Status", max_length=100)
    prazo_padrao_dias = models.PositiveIntegerField(
        "Prazo Padrão (dias)",
        default=0,
        help_text="Prazo padrão em dias para este status",
    )
    ordem = models.PositiveIntegerField(
        "Ordem",
        default=0,
        help_text="Ordem de exibição do status",
    )
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("ordem", "nome")
        verbose_name = "Status de Processo"
        verbose_name_plural = "Status de Processos"

    def __str__(self) -> str:
        if self.tipo_visto:
            return f"{self.tipo_visto.nome} - {self.nome}"
        return self.nome


class Processo(models.Model):
    """Processo de visto vinculado a uma viagem."""

    viagem = models.ForeignKey(
        "consultancy.Viagem",
        on_delete=models.CASCADE,
        related_name="processos",
        verbose_name="Viagem",
    )
    cliente = models.ForeignKey(
        "consultancy.ClienteConsultoria",
        on_delete=models.CASCADE,
        related_name="processos",
        verbose_name="Cliente",
    )
    status = models.ForeignKey(
        StatusProcesso,
        on_delete=models.PROTECT,
        related_name="processos",
        verbose_name="Status",
    )
    prazo_dias = models.PositiveIntegerField(
        "Prazo de dias para finalização",
        default=0,
        help_text="Número de dias previstos para finalização do processo",
    )
    observacoes = models.TextField("Observações", blank=True)
    assessor_responsavel = models.ForeignKey(
        UsuarioConsultoria,
        on_delete=models.PROTECT,
        related_name="processos_assessorados",
        verbose_name="Assessor responsável",
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="processos_criados",
        verbose_name="Criado por",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("-criado_em",)
        verbose_name = "Processo"
        verbose_name_plural = "Processos"
        unique_together = [("viagem", "cliente")]

    def __str__(self) -> str:
        return f"{self.cliente.nome} - {self.status.nome}"

