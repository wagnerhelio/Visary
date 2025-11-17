"""
Views auxiliares relacionadas aos clientes.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from consultancy.forms import ClienteConsultoriaForm
from consultancy.models import ClienteConsultoria
from consultancy.services.cep import buscar_endereco_por_cep
from system.models import UsuarioConsultoria

User = get_user_model()


def listar_clientes(user: User) -> QuerySet[ClienteConsultoria]:
    """
    Retorna queryset dos clientes com relacionamentos carregados.
    """

    queryset = ClienteConsultoria.objects.select_related(
        "assessor_responsavel",
        "criado_por",
        "assessor_responsavel__perfil",
    ).order_by("-criado_em")

    if user.is_superuser or user.is_staff:
        return queryset

    try:
        consultor = UsuarioConsultoria.objects.select_related("perfil").get(
            email__iexact=user.email,
            ativo=True,
        )
    except UsuarioConsultoria.DoesNotExist:
        return queryset.none()

    if consultor.perfil.nome.lower() == "administrador":
        return queryset

    return queryset.filter(
        Q(assessor_responsavel=consultor) | Q(criado_por=user)
    ).distinct()


def usuario_pode_gerenciar_todos(user: User, consultor: UsuarioConsultoria | None) -> bool:
    if user.is_superuser or user.is_staff:
        return True

    if consultor and consultor.perfil.nome.lower() == "administrador":
        return True

    return False


def obter_consultor_usuario(user: User) -> UsuarioConsultoria | None:
    return (
        UsuarioConsultoria.objects.select_related("perfil")
        .filter(email__iexact=user.email, ativo=True)
        .first()
    )


@login_required
def excluir_cliente(request, pk: int):
    if request.method != "POST":
        raise PermissionDenied

    cliente = get_object_or_404(
        ClienteConsultoria.objects.select_related("assessor_responsavel"),
        pk=pk,
    )

    consultor = obter_consultor_usuario(request.user)

    if not usuario_pode_gerenciar_todos(request.user, consultor):
        raise PermissionDenied

    cliente.delete()
    messages.success(request, f"{cliente.nome} excluído com sucesso.")
    return redirect("system:listar_clientes_view")


@login_required
def home_clientes(request):
    """Página inicial de clientes com opções de navegação."""
    consultor = obter_consultor_usuario(request.user)
    clientes = listar_clientes(request.user)
    
    contexto = {
        "total_clientes": clientes.count(),
        "clientes": clientes[:10],  # Limita a 10 clientes mais recentes
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }
    
    return render(request, "client/home_clientes.html", contexto)


@login_required
def listar_clientes_view(request):
    """Lista todos os clientes cadastrados com filtros."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    # Sempre busca TODOS os clientes na página de listar
    clientes = ClienteConsultoria.objects.select_related(
        "assessor_responsavel",
        "criado_por",
        "assessor_responsavel__perfil",
    ).order_by("-criado_em")
    
    # Aplicar filtros
    nome = request.GET.get("nome", "").strip()
    assessor_id = request.GET.get("assessor", "").strip()
    telefone = request.GET.get("telefone", "").strip()
    telefone_secundario = request.GET.get("telefone_secundario", "").strip()
    email = request.GET.get("email", "").strip()
    nacionalidade = request.GET.get("nacionalidade", "").strip()
    data_nascimento = request.GET.get("data_nascimento", "").strip()
    data_cadastro_inicio = request.GET.get("data_cadastro_inicio", "").strip()
    data_cadastro_fim = request.GET.get("data_cadastro_fim", "").strip()
    
    if nome:
        clientes = clientes.filter(nome__icontains=nome)
    if assessor_id:
        try:
            clientes = clientes.filter(assessor_responsavel_id=int(assessor_id))
        except (ValueError, TypeError):
            pass
    if telefone:
        clientes = clientes.filter(telefone__icontains=telefone)
    if telefone_secundario:
        clientes = clientes.filter(telefone_secundario__icontains=telefone_secundario)
    if email:
        clientes = clientes.filter(email__icontains=email)
    if nacionalidade:
        clientes = clientes.filter(nacionalidade__icontains=nacionalidade)
    if data_nascimento:
        clientes = clientes.filter(data_nascimento=data_nascimento)
    if data_cadastro_inicio:
        clientes = clientes.filter(criado_em__date__gte=data_cadastro_inicio)
    if data_cadastro_fim:
        clientes = clientes.filter(criado_em__date__lte=data_cadastro_fim)
    
    # Buscar assessores para o filtro
    assessores = UsuarioConsultoria.objects.filter(ativo=True).order_by("nome")
    
    contexto = {
        "clientes": clientes,
        "assessores": assessores,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_excluir_clientes": pode_gerenciar_todos,
        "filtros": {
            "nome": nome,
            "assessor": assessor_id,
            "telefone": telefone,
            "telefone_secundario": telefone_secundario,
            "email": email,
            "nacionalidade": nacionalidade,
            "data_nascimento": data_nascimento,
            "data_cadastro_inicio": data_cadastro_inicio,
            "data_cadastro_fim": data_cadastro_fim,
        },
    }
    
    return render(request, "client/listar_clientes.html", contexto)


@login_required
def cadastrar_cliente_view(request):
    """Formulário para cadastrar novo cliente."""
    consultor = obter_consultor_usuario(request.user)

    if request.method == "POST":
        form = ClienteConsultoriaForm(data=request.POST, user=request.user)
        if form.is_valid():
            cliente = form.save()
            messages.success(request, f"{cliente.nome} cadastrado com sucesso.")
            return redirect("system:home_clientes")
        messages.error(request, "Não foi possível cadastrar o cliente. Verifique os campos.")
    else:
        form = ClienteConsultoriaForm(user=request.user)

    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "client/cadastrar_cliente.html", contexto)


@login_required
def editar_cliente_view(request, pk: int):
    """Formulário para editar cliente existente."""
    consultor = obter_consultor_usuario(request.user)
    cliente = get_object_or_404(
        ClienteConsultoria.objects.select_related("assessor_responsavel"),
        pk=pk,
    )

    # Verificar permissão
    pode_editar = usuario_pode_gerenciar_todos(request.user, consultor)
    if not pode_editar:
        # Verificar se o usuário é o assessor responsável ou criador
        pode_editar = (
            cliente.assessor_responsavel == consultor
            or cliente.criado_por == request.user
        )
    
    if not pode_editar:
        raise PermissionDenied

    if request.method == "POST":
        form = ClienteConsultoriaForm(data=request.POST, user=request.user, instance=cliente)
        form.fields["senha"].required = False
        form.fields["confirmar_senha"].required = False
        
        if form.is_valid():
            # O formulário já trata a senha corretamente no método save()
            cliente_atualizado = form.save()
            messages.success(request, f"{cliente_atualizado.nome} atualizado com sucesso.")
            return redirect("system:listar_clientes_view")
        messages.error(request, "Não foi possível atualizar o cliente. Verifique os campos.")
    else:
        form = ClienteConsultoriaForm(user=request.user, instance=cliente)
        # Não preencher senha ao editar
        form.fields["senha"].required = False
        form.fields["senha"].widget.attrs["placeholder"] = "Deixe em branco para manter a senha atual"
        form.fields["confirmar_senha"].required = False
        form.fields["confirmar_senha"].widget.attrs["placeholder"] = "Deixe em branco para manter a senha atual"
        # Carregar parceiro atual se existir
        if cliente.parceiro_indicador:
            form.fields["parceiro_indicador"].initial = cliente.parceiro_indicador.pk

    contexto = {
        "form": form,
        "cliente": cliente,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "client/editar_cliente.html", contexto)


@login_required
@require_GET
def api_buscar_cep(request):
    """API para buscar endereço por CEP via AJAX."""
    cep = request.GET.get("cep", "").strip()

    if not cep:
        return JsonResponse({"error": "Informe um CEP."}, status=400)

    try:
        endereco = buscar_endereco_por_cep(cep)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse(endereco)

