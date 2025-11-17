"""
Views relacionadas a formulários dinâmicos de visto.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from consultancy.forms import (
    FormularioVistoForm,
    OpcaoSelecaoForm,
    PerguntaFormularioForm,
)
from consultancy.models import FormularioVisto, OpcaoSelecao, PerguntaFormulario
from system.views.client_views import obter_consultor_usuario, usuario_pode_gerenciar_todos


@login_required
def home_formularios(request):
    """Página inicial de formulários de visto."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    formularios = FormularioVisto.objects.select_related("tipo_visto").all().order_by(
        "tipo_visto__nome"
    )[:10]
    total_formularios = FormularioVisto.objects.count()

    contexto = {
        "formularios": formularios,
        "total_formularios": total_formularios,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }

    return render(request, "forms/home_formularios.html", contexto)


@login_required
def criar_formulario(request):
    """Formulário para criar novo formulário de visto."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    if request.method == "POST":
        form = FormularioVistoForm(data=request.POST)
        if form.is_valid():
            formulario = form.save()
            messages.success(
                request,
                f"Formulário para {formulario.tipo_visto.nome} criado com sucesso.",
            )
            return redirect("system:editar_formulario", pk=formulario.pk)
        messages.error(request, "Não foi possível criar o formulário. Verifique os campos.")
    else:
        form = FormularioVistoForm()

    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "forms/criar_formulario.html", contexto)


@login_required
def listar_formularios(request):
    """Lista todos os formulários de visto."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    formularios = (
        FormularioVisto.objects.select_related("tipo_visto")
        .prefetch_related("perguntas")
        .all()
        .order_by("tipo_visto__nome")
    )

    contexto = {
        "formularios": formularios,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }

    return render(request, "forms/listar_formularios.html", contexto)


@login_required
def editar_formulario(request, pk: int):
    """Editar formulário e gerenciar perguntas."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    formulario = get_object_or_404(
        FormularioVisto.objects.select_related("tipo_visto"), pk=pk
    )
    perguntas = (
        formulario.perguntas.all()
        .prefetch_related("opcoes")
        .order_by("ordem", "pergunta")
    )

    if request.method == "POST":
        form = FormularioVistoForm(data=request.POST, instance=formulario)
        if form.is_valid():
            form.save()
            messages.success(request, "Formulário atualizado com sucesso.")
            return redirect("system:editar_formulario", pk=formulario.pk)
        messages.error(request, "Não foi possível atualizar o formulário.")
    else:
        form = FormularioVistoForm(instance=formulario)

    contexto = {
        "form": form,
        "formulario": formulario,
        "perguntas": perguntas,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "forms/editar_formulario.html", contexto)


@login_required
def excluir_formulario(request, pk: int):
    """Exclui um formulário de visto."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    formulario = get_object_or_404(FormularioVisto, pk=pk)
    tipo_visto_nome = formulario.tipo_visto.nome
    formulario.delete()

    messages.success(request, f"Formulário de {tipo_visto_nome} excluído com sucesso.")
    return redirect("system:listar_formularios")


@login_required
def criar_pergunta(request, formulario_id: int):
    """Criar nova pergunta em um formulário."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    formulario = get_object_or_404(FormularioVisto, pk=formulario_id)

    if request.method == "POST":
        form = PerguntaFormularioForm(data=request.POST, formulario=formulario)
        if form.is_valid():
            pergunta = form.save()
            messages.success(request, f"Pergunta '{pergunta.pergunta}' adicionada com sucesso.")
            return redirect("system:editar_formulario", pk=formulario.pk)
        messages.error(request, "Não foi possível criar a pergunta. Verifique os campos.")
    else:
        form = PerguntaFormularioForm(formulario=formulario)

    contexto = {
        "form": form,
        "formulario": formulario,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "forms/criar_pergunta.html", contexto)


@login_required
def editar_pergunta(request, pk: int):
    """Editar pergunta existente."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    pergunta = get_object_or_404(
        PerguntaFormulario.objects.select_related("formulario"), pk=pk
    )
    formulario = pergunta.formulario
    opcoes = pergunta.opcoes.all().order_by("ordem", "texto") if pergunta.tipo_campo == "selecao" else []

    if request.method == "POST":
        form = PerguntaFormularioForm(data=request.POST, instance=pergunta, formulario=formulario)
        if form.is_valid():
            form.save()
            messages.success(request, f"Pergunta '{pergunta.pergunta}' atualizada com sucesso.")
            return redirect("system:editar_formulario", pk=formulario.pk)
        messages.error(request, "Não foi possível atualizar a pergunta.")
    else:
        form = PerguntaFormularioForm(instance=pergunta, formulario=formulario)

    contexto = {
        "form": form,
        "pergunta": pergunta,
        "formulario": formulario,
        "opcoes": opcoes,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "forms/editar_pergunta.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_pergunta(request, pk: int):
    """Exclui uma pergunta."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    pergunta = get_object_or_404(PerguntaFormulario.objects.select_related("formulario"), pk=pk)
    formulario = pergunta.formulario
    pergunta_texto = pergunta.pergunta
    pergunta.delete()

    messages.success(request, f"Pergunta '{pergunta_texto}' excluída com sucesso.")
    return redirect("system:editar_formulario", pk=formulario.pk)


@login_required
def criar_opcao_selecao(request, pergunta_id: int):
    """Criar nova opção de seleção para uma pergunta."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    pergunta = get_object_or_404(
        PerguntaFormulario.objects.select_related("formulario"), pk=pergunta_id
    )
    
    # Verificar se a pergunta é do tipo seleção
    if pergunta.tipo_campo != "selecao":
        messages.error(request, "Apenas perguntas do tipo 'Seleção' podem ter opções.")
        return redirect("system:editar_pergunta", pk=pergunta.pk)

    if request.method == "POST":
        form = OpcaoSelecaoForm(data=request.POST, pergunta=pergunta)
        if form.is_valid():
            opcao = form.save()
            messages.success(request, f"Opção '{opcao.texto}' adicionada com sucesso.")
            return redirect("system:editar_pergunta", pk=pergunta.pk)
        messages.error(request, "Não foi possível criar a opção. Verifique os campos.")
    else:
        form = OpcaoSelecaoForm(pergunta=pergunta)

    contexto = {
        "form": form,
        "pergunta": pergunta,
        "formulario": pergunta.formulario,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "forms/criar_opcao_selecao.html", contexto)


@login_required
def editar_opcao_selecao(request, pk: int):
    """Editar opção de seleção existente."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    opcao = get_object_or_404(
        OpcaoSelecao.objects.select_related("pergunta__formulario"), pk=pk
    )
    pergunta = opcao.pergunta

    if request.method == "POST":
        form = OpcaoSelecaoForm(data=request.POST, instance=opcao, pergunta=pergunta)
        if form.is_valid():
            form.save()
            messages.success(request, f"Opção '{opcao.texto}' atualizada com sucesso.")
            return redirect("system:editar_pergunta", pk=pergunta.pk)
        messages.error(request, "Não foi possível atualizar a opção.")
    else:
        form = OpcaoSelecaoForm(instance=opcao, pergunta=pergunta)

    contexto = {
        "form": form,
        "opcao": opcao,
        "pergunta": pergunta,
        "formulario": pergunta.formulario,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "forms/editar_opcao_selecao.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_opcao_selecao(request, pk: int):
    """Exclui uma opção de seleção."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    opcao = get_object_or_404(
        OpcaoSelecao.objects.select_related("pergunta__formulario"), pk=pk
    )
    pergunta = opcao.pergunta
    opcao_texto = opcao.texto
    opcao.delete()

    messages.success(request, f"Opção '{opcao_texto}' excluída com sucesso.")
    return redirect("system:editar_pergunta", pk=pergunta.pk)

