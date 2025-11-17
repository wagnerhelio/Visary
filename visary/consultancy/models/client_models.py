"""
Modelos relacionados aos clientes da consultoria.
"""

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import models

from system.models import UsuarioConsultoria


class ClienteConsultoria(models.Model):
    """
    Entidade que representa um cliente atendido pela consultoria.
    """

    assessor_responsavel = models.ForeignKey(
        UsuarioConsultoria,
        on_delete=models.PROTECT,
        related_name="clientes_assessorados",
        verbose_name="Assessor responsável",
    )
    nome = models.CharField("Nome completo", max_length=160)
    data_nascimento = models.DateField("Data de nascimento")
    nacionalidade = models.CharField("Nacionalidade", max_length=100)
    telefone = models.CharField("Telefone", max_length=20)
    telefone_secundario = models.CharField(
        "Telefone secundário",
        max_length=20,
        blank=True,
    )
    email = models.EmailField("E-mail", unique=True)
    senha = models.CharField(
        "Senha de acesso",
        max_length=128,
        help_text="Senha do cliente, armazenada utilizando hash.",
    )
    cep = models.CharField("CEP", max_length=9, blank=True)
    logradouro = models.CharField("Logradouro", max_length=200, blank=True)
    numero = models.CharField("Número", max_length=20, blank=True)
    complemento = models.CharField("Complemento", max_length=100, blank=True)
    bairro = models.CharField("Bairro", max_length=100, blank=True)
    cidade = models.CharField("Cidade", max_length=100, blank=True)
    uf = models.CharField("UF", max_length=2, blank=True)
    observacoes = models.TextField("Observações", blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="clientes_criados",
        verbose_name="Criado por",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)
    parceiro_indicador = models.ForeignKey(
        "consultancy.Partner",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clientes_indicados",
        verbose_name="Parceiro Indicador",
        help_text="Parceiro que indicou este cliente. O parceiro só acompanhará o processo se indicado aqui.",
    )

    class Meta:
        ordering = ("-criado_em", "nome")
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

    def __str__(self) -> str:
        return self.nome

    def set_password(self, raw_password: str) -> None:
        self.senha = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Verifica se a senha fornecida corresponde à senha do cliente."""
        from django.contrib.auth.hashers import check_password
        return check_password(raw_password, self.senha)

