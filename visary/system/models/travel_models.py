   
                                          
   

from django.conf import settings
from django.db import models

from .permission_models import UsuarioConsultoria


class PaisDestino(models.Model):
                                       

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
        "system.ClienteConsultoria",
        related_name="viagens",
        verbose_name="Clientes vinculados",
        blank=True,
        through="ClienteViagem",
        through_fields=("viagem", "cliente"),
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


class ClienteViagem(models.Model):
    """Vínculo entre cliente e viagem, incluindo papel (principal/dependente) por viagem."""

    PAPEL_CHOICES = [
        ("principal", "Principal"),
        ("dependente", "Dependente"),
    ]

    viagem = models.ForeignKey(
        Viagem,
        on_delete=models.CASCADE,
        related_name="clientes_viagem",
        verbose_name="Viagem",
    )
    cliente = models.ForeignKey(
        "system.ClienteConsultoria",
        on_delete=models.CASCADE,
        related_name="viagens_cliente",
        verbose_name="Cliente",
    )
    tipo_visto = models.ForeignKey(
        TipoVisto,
        on_delete=models.PROTECT,
        related_name="clientes_viagem_tipo_visto",
        verbose_name="Tipo de visto",
        null=True,
        blank=True,
        help_text="Tipo de visto específico para este cliente. Se não informado, usa o tipo de visto da viagem.",
    )
    papel = models.CharField(
        "Papel na viagem",
        max_length=20,
        choices=PAPEL_CHOICES,
        default="dependente",
    )
    cliente_principal_viagem = models.ForeignKey(
        "system.ClienteConsultoria",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dependentes_viagem",
        verbose_name="Cliente principal nesta viagem",
        help_text="Se dependente, quem é o principal NESTA viagem.",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Cliente na Viagem"
        verbose_name_plural = "Clientes na Viagem"
        unique_together = [("viagem", "cliente")]
        constraints = [
            models.UniqueConstraint(
                fields=["viagem"],
                condition=models.Q(papel="principal"),
                name="unique_principal_per_viagem",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.papel == "principal" and self.cliente_principal_viagem is not None:
            raise ValidationError(
                {"cliente_principal_viagem": "O cliente principal não pode ter um principal vinculado."}
            )
        if self.papel == "dependente":
            if self.cliente_principal_viagem is None:
                raise ValidationError(
                    {"cliente_principal_viagem": "Dependente deve ter um cliente principal nesta viagem."}
                )
            if self.cliente_principal_viagem_id == self.cliente_id:
                raise ValidationError(
                    {"cliente_principal_viagem": "Um cliente não pode ser principal de si mesmo."}
                )

    @property
    def is_principal_na_viagem(self) -> bool:
        return self.papel == "principal"

    @property
    def is_dependente_na_viagem(self) -> bool:
        return self.papel == "dependente"

    def __str__(self) -> str:
        tipo_visto_str = f" - {self.tipo_visto}" if self.tipo_visto else ""
        papel_str = f" ({self.get_papel_display()})"
        return f"{self.cliente.nome_completo} em {self.viagem}{tipo_visto_str}{papel_str}"
