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


def login_view(request):
    """
    Autenticação unificada que detecta automaticamente se o usuário é:
    - Consultor/Admin (UsuarioConsultoria) -> redireciona para área administrativa
    - Cliente (ClienteConsultoria) -> redireciona para área do cliente
    """

    # Se já estiver autenticado como consultor/admin
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    
    # Se já estiver autenticado como cliente (via sessão)
    if "cliente_id" in request.session:
        return redirect("system:cliente_dashboard")

    form = ConsultancyAuthenticationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        identifier = form.cleaned_data["identifier"].strip()
        password = form.cleaned_data["password"]
        remember = form.cleaned_data["remember_me"]

        # 1. Tentar autenticar como CONSULTOR/ADMIN primeiro
        consultor = (
            UsuarioConsultoria.objects.select_related("perfil")
            .filter(email__iexact=identifier, ativo=True)
            .first()
        )

        user = None

        if consultor and consultor.check_password(password):
            # Autenticado como consultor/admin
            user = _sync_consultant_user(consultor)
        else:
            # Tentar autenticação padrão do Django
            user = authenticate(request, username=identifier, password=password)

            if user is None and "@" in identifier:
                candidate = UserModel.objects.filter(email__iexact=identifier).only(
                    "username"
                ).first()
                if candidate:
                    user = authenticate(
                        request, username=candidate.username, password=password
                    )

        if user is not None and user.is_active:
            # Login como CONSULTOR/ADMIN bem-sucedido
            backend = getattr(
                user, "backend", "django.contrib.auth.backends.ModelBackend"
            )
            auth_login(request, user, backend=backend)

            if not remember:
                request.session.set_expiry(0)

            messages.success(request, "Autenticado com sucesso.")

            redirect_to = request.POST.get("next") or request.GET.get("next")
            if redirect_to:
                return redirect(redirect_to)

            return redirect(settings.LOGIN_REDIRECT_URL)

        # 2. Se não encontrou como consultor, tentar como CLIENTE
        cliente = ClienteConsultoria.objects.filter(email__iexact=identifier).first()

        if cliente:
            # Verificar se a senha está em formato válido
            senha_valida = is_password_usable(cliente.senha)
            
            if not senha_valida:
                messages.error(
                    request,
                    "Sua senha precisa ser redefinida. Entre em contato com o administrador."
                )
            else:
                # Verificar senha do cliente
                senha_correta = cliente.check_password(password)
                
                if senha_correta:
                    # Login como CLIENTE bem-sucedido
                    request.session["cliente_id"] = cliente.pk
                    request.session["cliente_nome"] = cliente.nome
                    request.session["cliente_email"] = cliente.email

                    if not remember:
                        request.session.set_expiry(0)  # Expira ao fechar o navegador
                    else:
                        request.session.set_expiry(1209600)  # 2 semanas

                    messages.success(request, f"Bem-vindo, {cliente.nome}!")
                    return redirect("system:cliente_dashboard")
                else:
                    # Senha incorreta para cliente
                    messages.error(request, "Credenciais inválidas ou usuário inativo.")
        else:
            # Não encontrou nem como consultor nem como cliente
            messages.error(request, "Credenciais inválidas ou usuário inativo.")

    context = {
        "form": form,
        "login_url": reverse("login"),
    }
    return render(request, "login/login.html", context)


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

