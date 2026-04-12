from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils.text import slugify


class Module(models.Model):
    name = models.CharField("Nome", max_length=120, unique=True)
    slug = models.SlugField("Slug", max_length=120, unique=True)
    description = models.TextField("Descrição", blank=True)
    order = models.PositiveIntegerField(
        "Ordem", default=0, help_text="Define a ordem de exibição no menu."
    )
    is_active = models.BooleanField("Ativo", default=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Módulo"
        verbose_name_plural = "Módulos"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Profile(models.Model):
    name = models.CharField("Nome", max_length=120, unique=True)
    description = models.TextField("Descrição", blank=True)
    modules = models.ManyToManyField(
        Module,
        verbose_name="Módulos",
        related_name="profiles",
        blank=True,
    )
    can_create = models.BooleanField("Pode criar", default=False)
    can_view = models.BooleanField("Pode visualizar", default=True)
    can_update = models.BooleanField("Pode atualizar", default=False)
    can_delete = models.BooleanField("Pode excluir", default=False)
    is_active = models.BooleanField("Ativo", default=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Perfil"
        verbose_name_plural = "Perfis"

    def __str__(self) -> str:
        return self.name


class ConsultancyUser(models.Model):
    name = models.CharField("Nome", max_length=160)
    email = models.EmailField("E-mail", unique=True)
    password = models.CharField("Senha", max_length=128, help_text="Armazena hash da senha.")
    profile = models.ForeignKey(
        Profile,
        on_delete=models.PROTECT,
        related_name="users",
        verbose_name="Perfil",
    )
    is_active = models.BooleanField("Ativo", default=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Usuário de Consultoria"
        verbose_name_plural = "Usuários de Consultoria"

    def __str__(self) -> str:
        return self.name

    def set_password(self, raw_password: str, *, commit: bool = True) -> None:
        self.password = make_password(raw_password)
        if commit:
            self.save(update_fields=["password", "updated_at"])

    def check_password(self, raw_password: str) -> bool:
        if not self.password:
            return False
        if check_password(raw_password, self.password):
            return True
        if self.password == raw_password:
            self.set_password(raw_password)
            return True
        return False
