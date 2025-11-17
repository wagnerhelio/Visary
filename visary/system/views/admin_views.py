"""
Views relacionadas à área de administração.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from system.forms import ModuloForm, PerfilForm, UsuarioConsultoriaForm
from system.models import Modulo, Perfil, UsuarioConsultoria
from system.views.client_views import obter_consultor_usuario, usuario_pode_gerenciar_todos


@login_required
def home_administracao(request):
    """Página inicial da área de administração."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    # Estatísticas
    total_usuarios = UsuarioConsultoria.objects.count()
    total_perfis = Perfil.objects.count()
    total_modulos = Modulo.objects.count()
    usuarios_ativos = UsuarioConsultoria.objects.filter(ativo=True).count()

    contexto = {
        "total_usuarios": total_usuarios,
        "total_perfis": total_perfis,
        "total_modulos": total_modulos,
        "usuarios_ativos": usuarios_ativos,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "admin/home_administracao.html", contexto)


# ========== GERENCIAR USUÁRIOS ==========

@login_required
def listar_usuarios(request):
    """Lista todos os usuários."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    usuarios = UsuarioConsultoria.objects.select_related("perfil").order_by("nome")

    # Filtros
    nome_filter = request.GET.get("nome", "")
    email_filter = request.GET.get("email", "")
    perfil_filter = request.GET.get("perfil", "")
    ativo_filter = request.GET.get("ativo", "")

    if nome_filter:
        usuarios = usuarios.filter(nome__icontains=nome_filter)

    if email_filter:
        usuarios = usuarios.filter(email__icontains=email_filter)

    if perfil_filter:
        usuarios = usuarios.filter(perfil_id=perfil_filter)

    if ativo_filter != "":
        usuarios = usuarios.filter(ativo=ativo_filter == "true")

    perfis = Perfil.objects.filter(ativo=True).order_by("nome")

    contexto = {
        "usuarios": usuarios,
        "perfis": perfis,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "filtros": {
            "nome": nome_filter,
            "email": email_filter,
            "perfil": perfil_filter,
            "ativo": ativo_filter,
        },
    }

    return render(request, "admin/usuarios/listar_usuarios.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def criar_usuario(request):
    """Cria um novo usuário."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    if request.method == "POST":
        form = UsuarioConsultoriaForm(data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Usuário criado com sucesso.")
            return redirect("system:listar_usuarios")
        messages.error(request, "Não foi possível criar o usuário. Verifique os campos.")
    else:
        form = UsuarioConsultoriaForm()

    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "admin/usuarios/criar_usuario.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def editar_usuario(request, pk: int):
    """Edita um usuário existente."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    usuario = get_object_or_404(UsuarioConsultoria.objects.select_related("perfil"), pk=pk)

    if request.method == "POST":
        form = UsuarioConsultoriaForm(data=request.POST, instance=usuario)
        if form.is_valid():
            form.save()
            messages.success(request, "Usuário atualizado com sucesso.")
            return redirect("system:listar_usuarios")
        messages.error(request, "Não foi possível atualizar o usuário. Verifique os campos.")
    else:
        form = UsuarioConsultoriaForm(instance=usuario)

    contexto = {
        "form": form,
        "usuario": usuario,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "admin/usuarios/editar_usuario.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_usuario(request, pk: int):
    """Exclui um usuário."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    usuario = get_object_or_404(UsuarioConsultoria, pk=pk)
    nome_usuario = usuario.nome
    usuario.delete()

    messages.success(request, f"Usuário {nome_usuario} excluído com sucesso.")
    return redirect("system:listar_usuarios")


# ========== GERENCIAR PERFIS/PERMISSÕES ==========

@login_required
def listar_perfis(request):
    """Lista todos os perfis/permissões."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    perfis = Perfil.objects.prefetch_related("modulos", "usuarios").order_by("nome")

    # Filtros
    nome_filter = request.GET.get("nome", "")
    ativo_filter = request.GET.get("ativo", "")

    if nome_filter:
        perfis = perfis.filter(nome__icontains=nome_filter)

    if ativo_filter != "":
        perfis = perfis.filter(ativo=ativo_filter == "true")

    contexto = {
        "perfis": perfis,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "filtros": {
            "nome": nome_filter,
            "ativo": ativo_filter,
        },
    }

    return render(request, "admin/perfis/listar_perfis.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def criar_perfil(request):
    """Cria um novo perfil/permissão."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    if request.method == "POST":
        form = PerfilForm(data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Perfil criado com sucesso.")
            return redirect("system:listar_perfis")
        messages.error(request, "Não foi possível criar o perfil. Verifique os campos.")
    else:
        form = PerfilForm()

    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "admin/perfis/criar_perfil.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def editar_perfil(request, pk: int):
    """Edita um perfil/permissão existente."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    perfil = get_object_or_404(Perfil.objects.prefetch_related("modulos", "usuarios"), pk=pk)

    if request.method == "POST":
        form = PerfilForm(data=request.POST, instance=perfil)
        if form.is_valid():
            form.save()
            messages.success(request, "Perfil atualizado com sucesso.")
            return redirect("system:listar_perfis")
        messages.error(request, "Não foi possível atualizar o perfil. Verifique os campos.")
    else:
        form = PerfilForm(instance=perfil)

    contexto = {
        "form": form,
        "perfil": perfil,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "admin/perfis/editar_perfil.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_perfil(request, pk: int):
    """Exclui um perfil/permissão."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    perfil = get_object_or_404(Perfil, pk=pk)
    nome_perfil = perfil.nome

    # Verificar se há usuários usando este perfil
    if perfil.usuarios.exists():
        messages.error(
            request,
            f"Não é possível excluir o perfil {nome_perfil} pois existem usuários vinculados a ele.",
        )
        return redirect("system:listar_perfis")

    perfil.delete()
    messages.success(request, f"Perfil {nome_perfil} excluído com sucesso.")
    return redirect("system:listar_perfis")


# ========== GERENCIAR MÓDULOS ==========

@login_required
def listar_modulos(request):
    """Lista todos os módulos."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    modulos = Modulo.objects.prefetch_related("perfis").order_by("ordem", "nome")

    # Filtros
    nome_filter = request.GET.get("nome", "")
    ativo_filter = request.GET.get("ativo", "")

    if nome_filter:
        modulos = modulos.filter(nome__icontains=nome_filter)

    if ativo_filter != "":
        modulos = modulos.filter(ativo=ativo_filter == "true")

    contexto = {
        "modulos": modulos,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "filtros": {
            "nome": nome_filter,
            "ativo": ativo_filter,
        },
    }

    return render(request, "admin/modulos/listar_modulos.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def criar_modulo(request):
    """Cria um novo módulo."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    if request.method == "POST":
        form = ModuloForm(data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Módulo criado com sucesso.")
            return redirect("system:listar_modulos")
        messages.error(request, "Não foi possível criar o módulo. Verifique os campos.")
    else:
        form = ModuloForm()

    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "admin/modulos/criar_modulo.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def editar_modulo(request, pk: int):
    """Edita um módulo existente."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    modulo = get_object_or_404(Modulo.objects.prefetch_related("perfis"), pk=pk)

    if request.method == "POST":
        form = ModuloForm(data=request.POST, instance=modulo)
        if form.is_valid():
            form.save()
            messages.success(request, "Módulo atualizado com sucesso.")
            return redirect("system:listar_modulos")
        messages.error(request, "Não foi possível atualizar o módulo. Verifique os campos.")
    else:
        form = ModuloForm(instance=modulo)

    contexto = {
        "form": form,
        "modulo": modulo,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "admin/modulos/editar_modulo.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_modulo(request, pk: int):
    """Exclui um módulo."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    modulo = get_object_or_404(Modulo, pk=pk)
    nome_modulo = modulo.nome

    # Verificar se há perfis usando este módulo
    if modulo.perfis.exists():
        messages.error(
            request,
            f"Não é possível excluir o módulo {nome_modulo} pois existem perfis vinculados a ele.",
        )
        return redirect("system:listar_modulos")

    modulo.delete()
    messages.success(request, f"Módulo {nome_modulo} excluído com sucesso.")
    return redirect("system:listar_modulos")

