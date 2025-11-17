from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils.text import slugify


class Modulo(models.Model):
    nome = models.CharField("Nome", max_length=120, unique=True)
    slug = models.SlugField("Slug", max_length=120, unique=True)
    descricao = models.TextField("Descrição", blank=True)
    ordem = models.PositiveIntegerField(
        "Ordem", default=0, help_text="Define a ordem de exibição no menu."
    )
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ["ordem", "nome"]
        verbose_name = "Módulo"
        verbose_name_plural = "Módulos"

    def __str__(self) -> str:
        return self.nome

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nome)
        super().save(*args, **kwargs)


class Perfil(models.Model):
    nome = models.CharField("Nome", max_length=120, unique=True)
    descricao = models.TextField("Descrição", blank=True)
    modulos = models.ManyToManyField(
        Modulo,
        verbose_name="Módulos",
        related_name="perfis",
        blank=True,
    )
    pode_criar = models.BooleanField("Pode criar", default=False)
    pode_visualizar = models.BooleanField("Pode visualizar", default=True)
    pode_atualizar = models.BooleanField("Pode atualizar", default=False)
    pode_excluir = models.BooleanField("Pode excluir", default=False)
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Perfil"
        verbose_name_plural = "Perfis"

    def __str__(self) -> str:
        return self.nome


class UsuarioConsultoria(models.Model):
    nome = models.CharField("Nome", max_length=160)
    email = models.EmailField("E-mail", unique=True)
    senha = models.CharField("Senha", max_length=128, help_text="Armazena hash da senha.")
    perfil = models.ForeignKey(
        Perfil,
        on_delete=models.PROTECT,
        related_name="usuarios",
        verbose_name="Perfil",
    )
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Usuário de Consultoria"
        verbose_name_plural = "Usuários de Consultoria"

    def __str__(self) -> str:
        return self.nome

    def set_password(self, raw_password: str, *, commit: bool = True) -> None:
        """
        Atualiza o hash da senha aplicando os hashers do Django.

        Parameters
        ----------
        raw_password:
            Senha em texto puro fornecida pelo usuário.
        commit:
            Quando True (padrão), persiste a alteração imediatamente.
        """

        self.senha = make_password(raw_password)

        if commit:
            self.save(update_fields=["senha", "atualizado_em"])

    def check_password(self, raw_password: str) -> bool:
        """
        Valida a senha informada utilizando o hash armazenado.
        """

        if not self.senha:
            return False

        if check_password(raw_password, self.senha):
            return True

        # Compatibilidade com registros antigos que possuam senha em texto puro.
        if self.senha == raw_password:
            self.set_password(raw_password)
            return True

        return False

