"""
Views para gerenciar etapas de cadastro de clientes.
"""

from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from consultancy.forms import (
    CampoEtapaClienteForm,
    CampoEtapaClienteInlineForm,
    ClienteConsultoriaForm,
    EtapaCadastroClienteForm,
)
from consultancy.models import CampoEtapaCliente, EtapaCadastroCliente
from system.views.client_views import obter_consultor_usuario, usuario_pode_gerenciar_todos


@login_required
def listar_etapas_cadastro(request):
    """Lista todas as etapas de cadastro configuradas."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar:
        raise PermissionDenied("Você não tem permissão para gerenciar etapas.")
    
    # Buscar todas as etapas, incluindo inativas, com campos ordenados
    etapas_queryset = EtapaCadastroCliente.objects.all().prefetch_related(
        models.Prefetch(
            "campos",
            queryset=CampoEtapaCliente.objects.all().order_by("ordem", "nome_campo")
        )
    ).order_by("ordem", "nome")
    
    # Forçar avaliação do QuerySet para garantir que os dados sejam passados corretamente
    etapas = list(etapas_queryset)
    
    contexto = {
        "etapas": etapas,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }
    
    return render(request, "client/etapas/listar_etapas_cadastro.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def criar_etapa_cadastro(request):
    """Cria uma nova etapa de cadastro."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar:
        raise PermissionDenied("Você não tem permissão para criar etapas.")
    
    if request.method == "POST":
        form = EtapaCadastroClienteForm(data=request.POST)
        if form.is_valid():
            etapa = form.save()
            messages.success(request, f"Etapa '{etapa.nome}' criada com sucesso.")
            return redirect("system:editar_etapa_cadastro", pk=etapa.pk)
        # Mostrar erros específicos de cada campo
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"Campo '{form.fields[field].label}': {error}")
    else:
        form = EtapaCadastroClienteForm()
    
    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }
    
    return render(request, "client/etapas/criar_etapa_cadastro.html", contexto)


def _obter_campos_disponiveis(campos_ja_vinculados: set) -> list:
    """Obtém lista de campos disponíveis do formulário ClienteConsultoria."""
    temp_form = ClienteConsultoriaForm()
    campos_modelo = [
        "assessor_responsavel",
        "nome",
        "cpf",
        "data_nascimento",
        "nacionalidade",
        "telefone",
        "telefone_secundario",
        "email",
        "senha",
        "confirmar_senha",
        "parceiro_indicador",
        "cep",
        "logradouro",
        "numero",
        "complemento",
        "bairro",
        "cidade",
        "uf",
        "observacoes",
    ]
    
    return [
        {
            "nome": campo_nome,
            "label": temp_form.fields[campo_nome].label or campo_nome,
            "ja_vinculado": campo_nome in campos_ja_vinculados,
        }
        for campo_nome in campos_modelo
        if campo_nome in temp_form.fields
    ]


def _adicionar_campo_etapa(request, etapa, campos, campos_disponiveis) -> Optional[HttpResponseRedirect]:
    """Processa a adição de um campo à etapa."""
    nome_campo = request.POST.get("nome_campo")
    nomes_disponiveis = {c["nome"] for c in campos_disponiveis}
    
    if not nome_campo or nome_campo not in nomes_disponiveis:
        messages.error(request, "Campo inválido.")
        return None
    
    if CampoEtapaCliente.objects.filter(etapa=etapa, nome_campo=nome_campo).exists():
        messages.error(request, f"Campo '{nome_campo}' já está vinculado a esta etapa.")
        return None
    
    maior_ordem = campos.aggregate(models.Max("ordem"))["ordem__max"] or 0
    CampoEtapaCliente.objects.create(
        etapa=etapa,
        nome_campo=nome_campo,
        ordem=maior_ordem + 1,
        obrigatorio=False,
        ativo=True,
    )
    messages.success(request, f"Campo '{nome_campo}' adicionado à etapa.")
    return redirect("system:editar_etapa_cadastro", pk=etapa.pk)


def _processar_atualizacao_etapa(request, form, etapa) -> Optional[HttpResponseRedirect]:
    """Processa a atualização da etapa e retorna redirect se válido."""
    if not form.is_valid():
        for field, errors in form.errors.items():
            field_label = form.fields[field].label if field in form.fields else field
            for error in errors:
                messages.error(request, f"Campo '{field_label}': {error}")
        return None
    
    form.save()
    messages.success(request, f"Etapa '{etapa.nome}' atualizada com sucesso.")
    return redirect("system:editar_etapa_cadastro", pk=etapa.pk)


@require_http_methods(["GET", "POST"])
def editar_etapa_cadastro(request, pk: int):
    """Edita uma etapa de cadastro existente."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar:
        raise PermissionDenied("Você não tem permissão para editar etapas.")
    
    etapa = get_object_or_404(EtapaCadastroCliente, pk=pk)
    campos = CampoEtapaCliente.objects.filter(etapa=etapa).order_by("ordem", "nome_campo")
    campos_ja_vinculados = {campo.nome_campo for campo in campos}
    campos_disponiveis = _obter_campos_disponiveis(campos_ja_vinculados)
    
    if request.method == "POST":
        if "adicionar_campo" in request.POST:
            if redirect_response := _adicionar_campo_etapa(request, etapa, campos, campos_disponiveis):
                return redirect_response
        
        form = EtapaCadastroClienteForm(data=request.POST, instance=etapa)
        if redirect_response := _processar_atualizacao_etapa(request, form, etapa):
            return redirect_response
    else:
        form = EtapaCadastroClienteForm(instance=etapa)
    
    # Recarregar campos após possíveis alterações
    campos = CampoEtapaCliente.objects.filter(etapa=etapa).order_by("ordem", "nome_campo")
    
    contexto = {
        "form": form,
        "etapa": etapa,
        "campos": campos,
        "campos_disponiveis": campos_disponiveis,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }
    
    return render(request, "client/etapas/editar_etapa_cadastro.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_etapa_cadastro(request, pk: int):
    """Exclui uma etapa de cadastro."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar:
        raise PermissionDenied("Você não tem permissão para excluir etapas.")
    
    etapa = get_object_or_404(EtapaCadastroCliente, pk=pk)
    nome_etapa = etapa.nome
    etapa.delete()
    messages.success(request, f"Etapa '{nome_etapa}' excluída com sucesso.")
    return redirect("system:listar_etapas_cadastro")


@login_required
@require_http_methods(["GET", "POST"])
def criar_campo_etapa(request, etapa_id: int):
    """Cria um novo campo para uma etapa."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar:
        raise PermissionDenied("Você não tem permissão para criar campos.")
    
    etapa = get_object_or_404(EtapaCadastroCliente, pk=etapa_id)
    
    if request.method == "POST":
        form = CampoEtapaClienteInlineForm(data=request.POST)
        if form.is_valid():
            campo = form.save(commit=False)
            campo.etapa = etapa
            campo.save()
            messages.success(request, f"Campo '{campo.nome_campo}' adicionado à etapa '{etapa.nome}'.")
            return redirect("system:listar_etapas_cadastro")
        # Mostrar erros específicos de cada campo
        for field, errors in form.errors.items():
            for error in errors:
                field_label = form.fields[field].label if field in form.fields else field
                messages.error(request, f"Campo '{field_label}': {error}")
    else:
        form = CampoEtapaClienteInlineForm()
    
    contexto = {
        "form": form,
        "etapa": etapa,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }
    
    return render(request, "client/etapas/criar_campo_etapa.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def editar_campo_etapa(request, pk: int):
    """Edita um campo de etapa existente."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar:
        raise PermissionDenied("Você não tem permissão para editar campos.")
    
    campo = get_object_or_404(CampoEtapaCliente, pk=pk)
    
    if request.method == "POST":
        form = CampoEtapaClienteInlineForm(data=request.POST, instance=campo)
        if form.is_valid():
            form.save()
            messages.success(request, f"Campo '{campo.nome_campo}' atualizado com sucesso.")
            return redirect("system:listar_etapas_cadastro")
        # Mostrar erros específicos de cada campo
        for field, errors in form.errors.items():
            for error in errors:
                field_label = form.fields[field].label if field in form.fields else field
                messages.error(request, f"Campo '{field_label}': {error}")
    else:
        form = CampoEtapaClienteInlineForm(instance=campo)
    
    contexto = {
        "form": form,
        "campo": campo,
        "etapa": campo.etapa,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }
    
    return render(request, "client/etapas/editar_campo_etapa.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_campo_etapa(request, pk: int):
    """Exclui um campo de etapa."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar:
        raise PermissionDenied("Você não tem permissão para excluir campos.")
    
    campo = get_object_or_404(CampoEtapaCliente, pk=pk)
    nome_campo = campo.nome_campo
    campo.delete()
    messages.success(request, f"Campo '{nome_campo}' excluído com sucesso.")
    return redirect("system:listar_etapas_cadastro")

