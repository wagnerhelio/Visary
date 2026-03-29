   
                                                 
   

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models

from .permission_models import UsuarioConsultoria


class ClienteConsultoria(models.Model):
    """Modelo principal de cliente da consultoria."""
       
                                                                 
       

    assessor_responsavel = models.ForeignKey(
        UsuarioConsultoria,
        on_delete=models.PROTECT,
        related_name="clientes_assessorados",
        verbose_name="Assessor responsável",
    )
    nome = models.CharField("Nome", max_length=100)
    sobrenome = models.CharField("Sobrenome", max_length=100)
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
        "system.Partner",
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

    @property
    def nome_completo(self) -> str:
        return f"{self.nome} {self.sobrenome}".strip()

    def __str__(self) -> str:
        return self.nome_completo

    def set_password(self, raw_password: str) -> None:
        self.senha = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        if not self.senha:
            return False

        try:
            if check_password(raw_password, self.senha):
                return True
        except ValueError:
            pass

        if self.senha == raw_password:
            self.set_password(raw_password)
            self.save(update_fields=["senha", "atualizado_em"])
            return True

        return False

    @property
    def is_principal(self) -> bool:
                                                                                   
        return self.cliente_principal is None

    @property
    def is_dependente(self) -> bool:
                                                        
        return self.cliente_principal is not None

    @property
    def total_dependentes(self) -> int:
                                                         
        return self.dependentes.count()

    def papel_na_viagem(self, viagem) -> str | None:
        """Retorna 'principal' ou 'dependente' para uma viagem específica, ou None se não vinculado."""
        from .travel_models import ClienteViagem

        try:
            cv = ClienteViagem.objects.get(viagem=viagem, cliente=self)
            return cv.papel
        except ClienteViagem.DoesNotExist:
            return None

    def is_principal_na_viagem(self, viagem) -> bool:
        return self.papel_na_viagem(viagem) == "principal"

    def dependentes_na_viagem(self, viagem):
        """QuerySet de clientes que são dependentes deste cliente numa viagem."""
        from .client_models import ClienteConsultoria

        return ClienteConsultoria.objects.filter(
            viagens_cliente__viagem=viagem,
            viagens_cliente__cliente_principal_viagem=self,
            viagens_cliente__papel="dependente",
        )

    def principal_na_viagem(self, viagem):
        """Retorna o cliente principal deste cliente numa viagem, ou None."""
        from .travel_models import ClienteViagem

        try:
            cv = ClienteViagem.objects.select_related("cliente_principal_viagem").get(
                viagem=viagem, cliente=self
            )
            return cv.cliente_principal_viagem
        except ClienteViagem.DoesNotExist:
            return None

    @property
    def progresso_etapas(self) -> int:
                                                           
        etapas = [
            self.etapa_dados_pessoais,
            self.etapa_endereco,
            self.etapa_passaporte,
            self.etapa_membros,
        ]
        concluidas = sum(etapas)
        return int((concluidas / len(etapas)) * 100) if etapas else 0


class Lembrete(models.Model):
    cliente = models.ForeignKey(
        ClienteConsultoria,
        on_delete=models.CASCADE,
        related_name="lembretes",
        verbose_name="Cliente",
    )
    texto = models.CharField("Lembrete", max_length=500)
    data_lembrete = models.DateField("Data do lembrete", null=True, blank=True)
    concluido = models.BooleanField("Concluído", default=False)
    criado_por = models.ForeignKey(
        UsuarioConsultoria,
        on_delete=models.PROTECT,
        related_name="lembretes_criados",
        verbose_name="Criado por",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        ordering = ("concluido", "-criado_em")
        verbose_name = "Lembrete"
        verbose_name_plural = "Lembretes"

    def __str__(self) -> str:
        return self.texto[:60]

