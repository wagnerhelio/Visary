"""
Modelos para gerenciar etapas configuráveis do cadastro de clientes.
"""

from django.db import models


class EtapaCadastroCliente(models.Model):
    """Etapa configurável do cadastro de cliente."""

    nome = models.CharField("Nome da Etapa", max_length=100)
    descricao = models.TextField("Descrição", blank=True)
    ordem = models.PositiveIntegerField(
        "Ordem",
        default=0,
        help_text="Ordem de exibição da etapa",
    )
    ativo = models.BooleanField("Ativo", default=True)
    campo_booleano = models.CharField(
        "Campo Booleano",
        max_length=50,
        blank=True,
        help_text="Nome do campo booleano do ClienteConsultoria que será marcado quando esta etapa for concluída (ex: etapa_dados_pessoais)",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("ordem", "nome")
        verbose_name = "Etapa de Cadastro"
        verbose_name_plural = "Etapas de Cadastro"

    def __str__(self) -> str:
        return f"{self.ordem}. {self.nome}"


class CampoEtapaCliente(models.Model):
    """Campo configurável vinculado a uma etapa do cadastro."""

    TIPO_CAMPO_CHOICES = [
        ("texto", "Texto"),
        ("data", "Data"),
        ("numero", "Número"),
        ("booleano", "Sim/Não"),
        ("selecao", "Seleção"),
    ]

    etapa = models.ForeignKey(
        EtapaCadastroCliente,
        on_delete=models.CASCADE,
        related_name="campos",
        verbose_name="Etapa",
    )
    nome_campo = models.CharField(
        "Nome do Campo",
        max_length=100,
        help_text="Nome do campo do modelo ClienteConsultoria ou do formulário (ex: nome, email, confirmar_senha)",
    )
    tipo_campo = models.CharField(
        "Tipo de Campo",
        max_length=20,
        choices=TIPO_CAMPO_CHOICES,
        default="texto",
        help_text="Tipo de campo: Texto, Data, Número, Sim/Não ou Seleção",
    )
    ordem = models.PositiveIntegerField(
        "Ordem",
        default=0,
        help_text="Ordem de exibição do campo dentro da etapa",
    )
    obrigatorio = models.BooleanField(
        "Obrigatório",
        default=True,
        help_text="Se o campo é obrigatório nesta etapa",
    )
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("etapa", "ordem", "nome_campo")
        verbose_name = "Campo da Etapa"
        verbose_name_plural = "Campos das Etapas"
        unique_together = [("etapa", "nome_campo")]

    def __str__(self) -> str:
        return f"{self.etapa.nome} - {self.nome_campo}"

