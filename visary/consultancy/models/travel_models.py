"""
Modelos relacionados a viagens e destinos.
"""

from django.conf import settings
from django.db import models

from system.models import UsuarioConsultoria


class PaisDestino(models.Model):
    """País de destino para viagens."""

    nome = models.CharField("Nome do país", max_length=100, unique=True)
    codigo_iso = models.CharField("Código ISO", max_length=3, blank=True)
    ativo = models.BooleanField("Ativo", default=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="paises_destino_criados",
        verbose_name="Criado por",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("nome",)
        verbose_name = "País de Destino"
        verbose_name_plural = "Países de Destino"

    def __str__(self) -> str:
        return self.nome


class TipoVisto(models.Model):
    """Tipo de visto vinculado a um país de destino."""

    pais_destino = models.ForeignKey(
        PaisDestino,
        on_delete=models.CASCADE,
        related_name="tipos_visto",
        verbose_name="País de destino",
    )
    nome = models.CharField("Nome do visto", max_length=100)
    descricao = models.TextField("Descrição", blank=True)
    ativo = models.BooleanField("Ativo", default=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tipos_visto_criados",
        verbose_name="Criado por",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("pais_destino", "nome")
        verbose_name = "Tipo de Visto"
        verbose_name_plural = "Tipos de Visto"
        unique_together = [("pais_destino", "nome")]

    def __str__(self) -> str:
        return f"{self.nome} - {self.pais_destino.nome}"


class Viagem(models.Model):
    """Viagem organizada pela consultoria."""

    assessor_responsavel = models.ForeignKey(
        UsuarioConsultoria,
        on_delete=models.PROTECT,
        related_name="viagens_assessoradas",
        verbose_name="Assessor responsável",
    )
    pais_destino = models.ForeignKey(
        PaisDestino,
        on_delete=models.PROTECT,
        related_name="viagens",
        verbose_name="País de destino",
    )
    tipo_visto = models.ForeignKey(
        TipoVisto,
        on_delete=models.PROTECT,
        related_name="viagens",
        verbose_name="Tipo de visto",
    )
    data_prevista_viagem = models.DateField("Data prevista da viagem")
    data_prevista_retorno = models.DateField("Data prevista de retorno")
    valor_assessoria = models.DecimalField(
        "Valor assessoria Visary",
        max_digits=10,
        decimal_places=2,
        default=0.00,
    )
    clientes = models.ManyToManyField(
        "consultancy.ClienteConsultoria",
        related_name="viagens",
        verbose_name="Clientes vinculados",
        blank=True,
    )
    observacoes = models.TextField("Observações", blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="viagens_criadas",
        verbose_name="Criado por",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("-data_prevista_viagem", "-criado_em")
        verbose_name = "Viagem"
        verbose_name_plural = "Viagens"

    def __str__(self) -> str:
        return f"{self.pais_destino.nome} - {self.data_prevista_viagem.strftime('%d/%m/%Y')}"

