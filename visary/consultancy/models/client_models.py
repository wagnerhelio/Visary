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
    cpf = models.CharField(
        "CPF",
        max_length=14,
        unique=True,
        help_text="CPF utilizado para login. Formato: 000.000.000-00",
    )
    data_nascimento = models.DateField("Data de nascimento")
    nacionalidade = models.CharField("Nacionalidade", max_length=100)
    telefone = models.CharField("Telefone", max_length=20)
    telefone_secundario = models.CharField(
        "Telefone secundário",
        max_length=20,
        blank=True,
    )
    email = models.EmailField("E-mail", blank=True, default="")
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
    cliente_principal = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="dependentes",
        verbose_name="Cliente Principal",
        help_text="Se este cliente é dependente, vincule ao cliente principal.",
    )
    etapa_dados_pessoais = models.BooleanField(
        "Etapa: Dados Pessoais",
        default=False,
        help_text="Dados pessoais preenchidos",
    )
    etapa_endereco = models.BooleanField(
        "Etapa: Endereço",
        default=False,
        help_text="Endereço preenchido",
    )
    etapa_membros = models.BooleanField(
        "Etapa: Membros",
        default=False,
        help_text="Membros/dependentes adicionados",
    )
    etapa_passaporte = models.BooleanField(
        "Etapa: Passaporte",
        default=False,
        help_text="Dados do passaporte preenchidos",
    )
    # Campos de Passaporte
    TIPO_PASSAPORTE_CHOICES = [
        ("comum", "Passaporte Comum/Regular"),
        ("diplomatico", "Passaporte Diplomático"),
        ("servico", "Passaporte de Serviço"),
        ("outro", "Outro"),
    ]
    tipo_passaporte = models.CharField(
        "Tipo de Passaporte",
        max_length=20,
        choices=TIPO_PASSAPORTE_CHOICES,
        blank=True,
        null=True,
    )
    tipo_passaporte_outro = models.CharField(
        "Outro tipo de passaporte",
        max_length=100,
        blank=True,
        help_text="Especifique o tipo de passaporte se selecionou 'Outro'",
    )
    numero_passaporte = models.CharField(
        "Número do passaporte válido",
        max_length=50,
        blank=True,
    )
    pais_emissor_passaporte = models.CharField(
        "País que emitiu o passaporte",
        max_length=100,
        blank=True,
    )
    data_emissao_passaporte = models.DateField(
        "Data de emissão",
        null=True,
        blank=True,
    )
    valido_ate_passaporte = models.DateField(
        "Válido até",
        null=True,
        blank=True,
    )
    autoridade_passaporte = models.CharField(
        "Autoridade",
        max_length=100,
        blank=True,
    )
    cidade_emissao_passaporte = models.CharField(
        "Cidade onde foi emitido",
        max_length=100,
        blank=True,
    )
    passaporte_roubado = models.BooleanField(
        "Já teve algum passaporte roubado?",
        default=False,
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

    @property
    def is_principal(self) -> bool:
        """Retorna True se este cliente é principal (não tem cliente_principal)."""
        return self.cliente_principal is None

    @property
    def is_dependente(self) -> bool:
        """Retorna True se este cliente é dependente."""
        return self.cliente_principal is not None

    @property
    def total_dependentes(self) -> int:
        """Retorna o número de dependentes vinculados."""
        return self.dependentes.count()

    @property
    def progresso_etapas(self) -> int:
        """Retorna o percentual de conclusão das etapas."""
        etapas = [
            self.etapa_dados_pessoais,
            self.etapa_endereco,
            self.etapa_passaporte,
            self.etapa_membros,
        ]
        concluidas = sum(etapas)
        return int((concluidas / len(etapas)) * 100) if etapas else 0

