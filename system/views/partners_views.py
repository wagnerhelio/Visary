from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from system.forms import PartnerForm
from system.models import Partner
from system.views.client_views import get_user_consultant, user_can_manage_all, user_has_module_access


def _segment_choices():
    return Partner._meta.get_field("segment").choices


def _apply_partner_filters(partners, request):
    filters = {
        "search": request.GET.get("search", "").strip(),
        "segment": request.GET.get("segment", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "state": request.GET.get("state", "").strip(),
        "city": request.GET.get("city", "").strip(),
    }

    if filters["search"]:
        search_term = filters["search"]
        partners = partners.filter(
            Q(contact_name__icontains=search_term)
            | Q(company_name__icontains=search_term)
            | Q(email__icontains=search_term)
        )
    if filters["segment"]:
        partners = partners.filter(segment=filters["segment"])
    if filters["status"] == "ativo":
        partners = partners.filter(is_active=True)
    elif filters["status"] == "inativo":
        partners = partners.filter(is_active=False)
    if filters["state"]:
        partners = partners.filter(state__icontains=filters["state"])
    if filters["city"]:
        partners = partners.filter(city__icontains=filters["city"])

    return partners, filters


@login_required
def home_partners(request):
    consultant = get_user_consultant(request.user)
    if not user_has_module_access(request.user, consultant, "Parceiros"):
        raise PermissionDenied
    can_manage_all = user_can_manage_all(request.user, consultant)

    partners = Partner.objects.all().order_by("company_name", "contact_name")
    partners, applied_filters = _apply_partner_filters(partners, request)
    total_partners = partners.count()

    context = {
        "partners": partners[:10],
        "total_partners": total_partners,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "applied_filters_dict": applied_filters,
        "segmentos": _segment_choices(),
    }

    return render(request, "partners/home_partners.html", context)


@login_required
def create_partner(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    if request.method == "POST":
        form = PartnerForm(data=request.POST, user=request.user)
        if form.is_valid():
            partner = form.save(commit=False)
            partner.created_by = request.user
            partner.save()
            messages.success(request, f"Parceiro {form.cleaned_data.get('company_name') or form.cleaned_data.get('contact_name')} cadastrado com sucesso.")
            return redirect("system:home_partners")
        messages.error(request, "Não foi possível cadastrar o parceiro. Verifique os campos.")
    else:
        form = PartnerForm(user=request.user)

    context = {
        "form": form,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "partners/create_partner.html", context)


@login_required
def list_partners(request):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    partners = Partner.objects.all().order_by("company_name", "contact_name")
    partners, applied_filters = _apply_partner_filters(partners, request)

    context = {
        "partners": partners,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "applied_filters_dict": applied_filters,
        "segmentos": _segment_choices(),
    }

    return render(request, "partners/list_partners.html", context)


@login_required
def edit_partner(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    partner = get_object_or_404(Partner, pk=pk)

    if request.method == "POST":
        _clear_duplicate_session_messages(request)

        form = PartnerForm(data=request.POST, user=request.user, instance=partner)
        if form.is_valid():
            updated_partner = form.save()
            messages.success(request, f"Parceiro {updated_partner.company_name or updated_partner.contact_name} atualizado com sucesso.")
            return redirect("system:list_partners")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{form.fields[field].label}: {error}")
    else:
        form = PartnerForm(user=request.user, instance=partner)
        if partner.cpf:
            form.fields["cpf"].initial = partner.cpf
        if partner.cnpj:
            form.fields["cnpj"].initial = partner.cnpj

    context = {
        "form": form,
        "partner": partner,
        "user_profile": consultant.profile.name if consultant else None,
    }

    return render(request, "partners/edit_partner.html", context)


@login_required
def view_partner(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    partner = get_object_or_404(Partner, pk=pk)

    from system.models import ConsultancyClient
    linked_clients = ConsultancyClient.objects.filter(
        referring_partner=partner
    ).select_related("assigned_advisor", "primary_client").order_by("first_name")

    context = {
        "partner": partner,
        "linked_clients": linked_clients,
        "user_profile": consultant.profile.name if consultant else None,
        "can_manage_all": can_manage_all,
        "can_edit": can_manage_all,
    }

    return render(request, "partners/view_partner.html", context)


def _clear_duplicate_session_messages(request):
    if not (stored_messages := request.session.get('_messages')):
        return

    filtered = []
    seen_texts = set()
    for msg in stored_messages:
        message_text = str(msg.get('message', '') if isinstance(msg, dict) else msg)
        if message_text not in seen_texts:
            seen_texts.add(message_text)
            filtered.append(msg)

    if filtered:
        request.session['_messages'] = filtered
    else:
        request.session.pop('_messages', None)
    request.session.modified = True

    from django.contrib import messages
    storage = messages.get_messages(request)
    storage.used = True


@login_required
@require_http_methods(["POST"])
def delete_partner(request, pk: int):
    consultant = get_user_consultant(request.user)
    can_manage_all = user_can_manage_all(request.user, consultant)

    if not can_manage_all:
        raise PermissionDenied

    _clear_duplicate_session_messages(request)

    partner = get_object_or_404(Partner, pk=pk)
    partner_name = partner.company_name or partner.contact_name
    partner.delete()

    messages.success(request, f"Parceiro {partner_name} excluído com sucesso.")
    return redirect("system:list_partners")
