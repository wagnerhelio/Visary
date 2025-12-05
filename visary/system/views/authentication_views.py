"""
Views responsáveis pela autenticação de usuários de consultoria.
"""

from __future__ import annotations

from typing import List

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login as auth_login
from django.contrib.auth.hashers import is_password_usable
from django.shortcuts import redirect, render
from django.urls import reverse

from consultancy.models import ClienteConsultoria
from system.forms.authentication_forms import ConsultancyAuthenticationForm
from system.models import UsuarioConsultoria

UserModel = get_user_model()


def _verificar_autenticacao_previa(request):
    """Verifica se o usuário já está autenticado e redireciona se necessário."""
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    if "cliente_id" in request.session:
        return redirect("system:cliente_dashboard")
    return None


def _autenticar_consultor(identifier: str, password: str, request):
    """Tenta autenticar como consultor/admin."""
    consultor = (
        UsuarioConsultoria.objects.select_related("perfil")
        .filter(email__iexact=identifier, ativo=True)
        .first()
    )

    if consultor and consultor.check_password(password):
        return _sync_consultant_user(consultor)

    # Tentar autenticação padrão do Django
    user = authenticate(request, username=identifier, password=password)

    if user is None and "@" in identifier:
        if candidate := UserModel.objects.filter(email__iexact=identifier).only(
            "username"
        ).first():
            user = authenticate(request, username=candidate.username, password=password)

    return user


def _processar_login_consultor(request, user, remember: bool):
    """Processa o login do consultor/admin e redireciona."""
    backend = getattr(user, "backend", "django.contrib.auth.backends.ModelBackend")
    auth_login(request, user, backend=backend)

    if not remember:
        request.session.set_expiry(0)

    if redirect_to := request.POST.get("next") or request.GET.get("next"):
        return redirect(redirect_to)

    return redirect(settings.LOGIN_REDIRECT_URL)


def _autenticar_cliente(identifier: str, password: str, request, remember: bool):
    """Tenta autenticar como cliente."""
    if cliente := ClienteConsultoria.objects.filter(email__iexact=identifier).first():
        if not is_password_usable(cliente.senha):
            messages.error(
                request,
                "Sua senha precisa ser redefinida. Entre em contato com o administrador."
            )
            return None
        if cliente.check_password(password):
            return _processar_login_cliente(request, cliente, remember)
    return None


def login_view(request):
    """
    Autenticação unificada que detecta automaticamente se o usuário é:
    - Consultor/Admin (UsuarioConsultoria) -> redireciona para área administrativa
    - Cliente (ClienteConsultoria) -> redireciona para área do cliente
    """
    if redirect_response := _verificar_autenticacao_previa(request):
        return redirect_response

    form = ConsultancyAuthenticationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        identifier = form.cleaned_data["identifier"].strip()
        password = form.cleaned_data["password"]
        remember = form.cleaned_data["remember_me"]

        # 1. Tentar autenticar como CONSULTOR/ADMIN primeiro
        user = _autenticar_consultor(identifier, password, request)

        if user is not None and user.is_active:
            return _processar_login_consultor(request, user, remember)

        # 2. Se não encontrou como consultor, tentar como CLIENTE
        if redirect_response := _autenticar_cliente(identifier, password, request, remember):
            return redirect_response

        # Credenciais inválidas
        messages.error(request, "Credenciais inválidas ou usuário inativo.")

    context = {
        "form": form,
        "login_url": reverse("login"),
    }
    return render(request, "login/login.html", context)


def _processar_login_cliente(request, cliente: ClienteConsultoria, remember: bool):
    """Processa o login do cliente e configura a sessão."""
    request.session["cliente_id"] = cliente.pk
    request.session["cliente_nome"] = cliente.nome
    request.session["cliente_email"] = cliente.email

    if not remember:
        request.session.set_expiry(0)  # Expira ao fechar o navegador
    else:
        request.session.set_expiry(1209600)  # 2 semanas

    messages.success(request, f"Bem-vindo, {cliente.nome}!")
    return redirect("system:cliente_dashboard")


def _sync_consultant_user(consultor: UsuarioConsultoria):
    """
    Garante que exista um usuário do auth Django associado ao consultor.
    """

    defaults = {
        "email": consultor.email,
        "first_name": consultor.nome.split()[0] if consultor.nome else "",
        "last_name": " ".join(consultor.nome.split()[1:]) if consultor.nome else "",
        "is_active": consultor.ativo,
    }

    user, created = UserModel.objects.get_or_create(
        username=consultor.email,
        defaults=defaults,
    )

    updated_fields: List[str] = []

    for field, value in defaults.items():
        if getattr(user, field) != value:
            setattr(user, field, value)
            updated_fields.append(field)

    if created and not user.has_usable_password():
        user.set_unusable_password()
        updated_fields.append("password")

    if updated_fields:
        user.save(update_fields=updated_fields)

    return user

