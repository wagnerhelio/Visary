from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login as auth_login
from django.contrib.auth.hashers import is_password_usable
from django.shortcuts import redirect, render
from django.urls import reverse

from system.forms.authentication_forms import ConsultancyAuthenticationForm
from system.models import ConsultancyClient, ConsultancyUser, Partner

UserModel = get_user_model()


def _check_prior_auth(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    if "client_id" in request.session:
        return redirect("system:client_dashboard")
    if "partner_id" in request.session:
        return redirect("system:partner_dashboard")
    return None


def _authenticate_consultant(identifier, password, request):
    consultant = (
        ConsultancyUser.objects.select_related("profile")
        .filter(email__iexact=identifier, is_active=True)
        .first()
    )
    if consultant and consultant.check_password(password):
        return _sync_consultant_user(consultant)

    user = authenticate(request, username=identifier, password=password)
    if user is None and "@" in identifier:
        if candidate := UserModel.objects.filter(email__iexact=identifier).only("username").first():
            user = authenticate(request, username=candidate.username, password=password)
    return user


def _process_consultant_login(request, user, remember):
    backend = getattr(user, "backend", "django.contrib.auth.backends.ModelBackend")
    auth_login(request, user, backend=backend)
    request.session.set_expiry(1209600 if remember else 0)
    if redirect_to := request.POST.get("next") or request.GET.get("next"):
        return redirect(redirect_to)
    return redirect(settings.LOGIN_REDIRECT_URL)


def _normalize_cpf(value):
    digits = "".join(c for c in value if c.isdigit())
    return digits if len(digits) == 11 else ""


def _authenticate_client(identifier, password, request, remember):
    cpf_digits = _normalize_cpf(identifier)
    client = None
    if cpf_digits:
        formatted = f"{cpf_digits[:3]}.{cpf_digits[3:6]}.{cpf_digits[6:9]}-{cpf_digits[9:]}"
        client = ConsultancyClient.objects.filter(cpf__in=[cpf_digits, formatted]).first()
    if not client and "@" in identifier:
        client = ConsultancyClient.objects.filter(email__iexact=identifier.strip()).first()
    if not client:
        return None
    if not is_password_usable(client.password):
        messages.error(request, "Sua senha precisa ser redefinida. Entre em contato com o administrador.")
        return None
    if client.check_password(password):
        return _process_client_login(request, client, remember)
    return None


def _authenticate_partner(identifier, password, request, remember):
    if "@" not in identifier:
        return None
    partner = Partner.objects.filter(email__iexact=identifier.strip(), is_active=True).first()
    if not partner or not partner.check_password(password):
        return None
    request.session["partner_id"] = partner.pk
    request.session["partner_name"] = partner.contact_name
    request.session["partner_email"] = partner.email
    request.session.set_expiry(1209600 if remember else 0)
    messages.success(request, f"Bem-vindo(a), {partner.contact_name}!")
    return redirect("system:partner_dashboard")


def login_view(request):
    if redirect_response := _check_prior_auth(request):
        return redirect_response

    form = ConsultancyAuthenticationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        identifier = form.cleaned_data["identifier"].strip()
        password = form.cleaned_data["password"]
        remember = form.cleaned_data["remember_me"]

        user = _authenticate_consultant(identifier, password, request)
        if user is not None and user.is_active:
            return _process_consultant_login(request, user, remember)

        if redirect_response := _authenticate_partner(identifier, password, request, remember):
            return redirect_response

        if redirect_response := _authenticate_client(identifier, password, request, remember):
            return redirect_response

        messages.error(request, "Credenciais inválidas ou usuário inativo.")

    return render(request, "login/login.html", {"form": form, "login_url": reverse("system:login")})


def _process_client_login(request, client, remember):
    request.session["client_id"] = client.pk
    request.session["client_name"] = client.full_name
    request.session["client_cpf"] = client.cpf
    request.session.set_expiry(1209600 if remember else 0)
    messages.success(request, f"Bem-vindo, {client.full_name}!")
    return redirect("system:client_dashboard")


def _sync_consultant_user(consultant):
    defaults = {
        "email": consultant.email,
        "first_name": consultant.name.split()[0] if consultant.name else "",
        "last_name": " ".join(consultant.name.split()[1:]) if consultant.name else "",
        "is_active": consultant.is_active,
    }
    user, created = UserModel.objects.get_or_create(username=consultant.email, defaults=defaults)
    updated_fields = []
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
