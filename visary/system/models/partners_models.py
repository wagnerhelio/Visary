   
                                                      
   

from django.conf import settings
from django.db import models

from system.services.passwords import check_password_with_legacy_fallback


class Partner(models.Model):
                                                            

    SEGMENTO_CHOICES = [
        ("agencia_viagem", "Agência de Viagem"),
        ("consultoria_imigracao", "Consultoria de Imigração"),
        ("advocacia", "Advocacia"),
        ("educacao", "Educação"),
        ("outros", "Outros"),
    ]

    nome_responsavel = models.CharField("Nome do Responsável", max_length=200)
    nome_empresa = models.CharField("Nome da Empresa", max_length=200, blank=True, null=True)
    cpf = models.CharField("CPF", max_length=14, blank=True, null=True)
    cnpj = models.CharField("CNPJ", max_length=18, blank=True, null=True)
    email = models.EmailField("E-mail", unique=True)
    senha = models.CharField("Senha", max_length=128)
    telefone = models.CharField("Telefone", max_length=20, blank=True, null=True)
    segmento = models.CharField(
        "Segmento",
        max_length=50,
        choices=SEGMENTO_CHOICES,
        default="outros",
    )
    cidade = models.CharField("Cidade", max_length=100, blank=True, null=True)
    estado = models.CharField("Estado", max_length=2, blank=True, null=True)
    ativo = models.BooleanField("Ativo", default=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="partners_criados",
        verbose_name="Criado por",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Parceiro"
        verbose_name_plural = "Parceiros"
        ordering = ("nome_empresa", "nome_responsavel")

    def __str__(self):
        if self.nome_empresa:
            return f"{self.nome_empresa} - {self.nome_responsavel}"
        return self.nome_responsavel

    def set_password(self, raw_password):
                                         
        from django.contrib.auth.hashers import make_password
        self.senha = make_password(raw_password)

    def check_password(self, raw_password):
        password_is_valid, should_upgrade_hash = check_password_with_legacy_fallback(
            raw_password,
            self.senha,
        )
        if password_is_valid and should_upgrade_hash:
            self.set_password(raw_password)
            self.save(update_fields=["senha", "atualizado_em"])
        return password_is_valid

