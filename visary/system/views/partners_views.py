"""
Views relacionadas a parceiros.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from consultancy.forms import PartnerForm
from consultancy.models import Partner
from system.views.client_views import obter_consultor_usuario, usuario_pode_gerenciar_todos, usuario_tem_acesso_modulo


@login_required
def home_partners(request):
    consultor = obter_consultor_usuario(request.user)
    if not usuario_tem_acesso_modulo(request.user, consultor, "Parceiros"):
        raise PermissionDenied
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    partners = Partner.objects.all().order_by("nome_empresa", "nome_responsavel")[:10]
    total_partners = Partner.objects.count()
    
    contexto = {
        "partners": partners,
        "total_partners": total_partners,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }
    
    return render(request, "partners/home_partners.html", contexto)


@login_required
def criar_partner(request):
    """Formulário para cadastrar novo parceiro."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar_todos:
        raise PermissionDenied

    if request.method == "POST":
        form = PartnerForm(data=request.POST, user=request.user)
        if form.is_valid():
            partner = form.save(commit=False)
            partner.criado_por = request.user
            partner.save()
            messages.success(request, f"Parceiro {form.cleaned_data.get('nome_empresa') or form.cleaned_data.get('nome_responsavel')} cadastrado com sucesso.")
            return redirect("system:home_partners")
        messages.error(request, "Não foi possível cadastrar o parceiro. Verifique os campos.")
    else:
        form = PartnerForm(user=request.user)

    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "partners/criar_partner.html", contexto)


@login_required
def listar_partners(request):
    """Lista todos os parceiros."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    partners = Partner.objects.all().order_by("nome_empresa", "nome_responsavel")
    
    contexto = {
        "partners": partners,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }
    
    return render(request, "partners/listar_partners.html", contexto)


@login_required
def editar_partner(request, pk: int):
    """Formulário para editar parceiro existente."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar_todos:
        raise PermissionDenied
    
    partner = get_object_or_404(Partner, pk=pk)
    
    if request.method == "POST":
        # Limpar mensagens duplicadas antes de processar
        _limpar_mensagens_duplicadas_sessao(request)
        
        form = PartnerForm(data=request.POST, user=request.user, instance=partner)
        if form.is_valid():
            partner_atualizado = form.save()
            messages.success(request, f"Parceiro {partner_atualizado.nome_empresa or partner_atualizado.nome_responsavel} atualizado com sucesso.")
            return redirect("system:listar_partners")
        else:
            # Exibir erros do formulário
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{form.fields[field].label}: {error}")
    else:
        form = PartnerForm(user=request.user, instance=partner)
        # Preencher campos CPF e CNPJ se existirem
        if partner.cpf:
            form.fields["cpf"].initial = partner.cpf
        if partner.cnpj:
            form.fields["cnpj"].initial = partner.cnpj

    contexto = {
        "form": form,
        "partner": partner,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }
    
    return render(request, "partners/editar_partner.html", contexto)


@login_required
def visualizar_partner(request, pk: int):
    """Visualiza todas as informações do parceiro."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    partner = get_object_or_404(Partner, pk=pk)
    
    # Buscar clientes vinculados a este parceiro
    from consultancy.models import ClienteConsultoria
    clientes_vinculados = ClienteConsultoria.objects.filter(
        parceiro_indicador=partner
    ).select_related("assessor_responsavel", "cliente_principal").order_by("nome")
    
    contexto = {
        "partner": partner,
        "clientes_vinculados": clientes_vinculados,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "pode_editar": pode_gerenciar_todos,
    }
    
    return render(request, "partners/visualizar_partner.html", contexto)


def _limpar_mensagens_duplicadas_sessao(request):
    """Remove mensagens duplicadas da sessão."""
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
    
    # Consumir mensagens do storage também
    from django.contrib import messages
    storage = messages.get_messages(request)
    storage.used = True


@login_required
@require_http_methods(["POST"])
def excluir_partner(request, pk: int):
    """Exclui um parceiro."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar_todos:
        raise PermissionDenied
    
    # Limpar mensagens duplicadas antes de adicionar nova
    _limpar_mensagens_duplicadas_sessao(request)
    
    partner = get_object_or_404(Partner, pk=pk)
    nome_partner = partner.nome_empresa or partner.nome_responsavel
    partner.delete()
    
    messages.success(request, f"Parceiro {nome_partner} excluído com sucesso.")
    return redirect("system:listar_partners")

