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
from consultancy.models import FormularioVisto, OpcaoSelecao, PerguntaFormulario, Viagem
from system.views.client_views import listar_clientes, obter_consultor_usuario, usuario_pode_gerenciar_todos, usuario_tem_acesso_modulo


@login_required
def home_formularios(request):
    from consultancy.models import ClienteViagem, RespostaFormulario
    from contextlib import suppress

    consultor = obter_consultor_usuario(request.user)
    if not usuario_tem_acesso_modulo(request.user, consultor, "Formularios"):
        raise PermissionDenied
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    # Buscar clientes vinculados ao usuário (para administradores retorna todos, para assessores retorna apenas os vinculados)
    clientes_usuario = listar_clientes(request.user)
    clientes_ids = list(clientes_usuario.values_list("pk", flat=True))
    
    # Buscar viagens dos clientes do usuário
    viagens = Viagem.objects.filter(
        clientes__pk__in=clientes_ids
    ).select_related(
        "pais_destino",
        "tipo_visto",
        "tipo_visto__formulario",
    ).prefetch_related("clientes").distinct().order_by("-data_prevista_viagem")
    
    # Função auxiliar para obter tipo_visto do cliente
    def _obter_tipo_visto_cliente(viagem, cliente):
        """Obtém o tipo de visto individual do cliente na viagem, ou o tipo de visto da viagem como fallback."""
        with suppress(ClienteViagem.DoesNotExist):
            cliente_viagem = ClienteViagem.objects.select_related('tipo_visto__formulario').get(
                viagem=viagem, cliente=cliente
            )
            if cliente_viagem.tipo_visto:
                return cliente_viagem.tipo_visto
        return viagem.tipo_visto
    
    # Função auxiliar para obter formulário por tipo_visto
    def _obter_formulario_por_tipo_visto(tipo_visto, apenas_ativo=True):
        """Obtém o formulário de um tipo de visto diretamente do banco de dados."""
        if not tipo_visto or not hasattr(tipo_visto, 'pk') or not tipo_visto.pk:
            return None
        try:
            if apenas_ativo:
                return FormularioVisto.objects.select_related('tipo_visto').get(
                    tipo_visto_id=tipo_visto.pk,
                    ativo=True
                )
            return FormularioVisto.objects.select_related('tipo_visto').get(
                tipo_visto_id=tipo_visto.pk
            )
        except FormularioVisto.DoesNotExist:
            return None
    
    # Preparar informações dos formulários
    formularios_respostas = []
    total_clientes_com_formulario = 0
    
    for viagem in viagens[:10]:  # Limitar a 10 mais recentes
        # Buscar clientes da viagem vinculados ao usuário
        clientes_viagem = viagem.clientes.filter(pk__in=clientes_ids)
        
        if not clientes_viagem.exists():
            continue
        
        # Agrupar clientes por formulário (cada cliente pode ter um tipo_visto diferente)
        clientes_por_formulario = {}
        
        for cliente in clientes_viagem:
            # Obter o tipo_visto individual do cliente
            tipo_visto_cliente = _obter_tipo_visto_cliente(viagem, cliente)
            
            if not tipo_visto_cliente:
                continue
            
            # Buscar formulário diretamente do banco de dados
            formulario = _obter_formulario_por_tipo_visto(tipo_visto_cliente, apenas_ativo=True)
            
            if not formulario:
                continue
            
            # Usar chave única: viagem_id + formulario_id
            chave = f"{viagem.pk}_{formulario.pk}"
            
            if chave not in clientes_por_formulario:
                clientes_por_formulario[chave] = {
                    "viagem": viagem,
                    "formulario": formulario,
                    "clientes": [],
                }
            
            # Calcular informações do formulário para este cliente
            total_perguntas = formulario.perguntas.filter(ativo=True).count()
            total_respostas = RespostaFormulario.objects.filter(
                viagem=viagem,
                cliente=cliente
            ).count()
            
            clientes_por_formulario[chave]["clientes"].append({
                "cliente": cliente,
                "tipo_visto": tipo_visto_cliente,
                "total_perguntas": total_perguntas,
                "total_respostas": total_respostas,
                "completo": total_respostas == total_perguntas if total_perguntas > 0 else False,
            })
            total_clientes_com_formulario += 1
        
        # Adicionar ao resultado (todos os formulários disponíveis)
        formularios_respostas.extend(clientes_por_formulario.values())
    
    contexto = {
        "total_formularios": total_clientes_com_formulario,
        "formularios_respostas": formularios_respostas,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }

    return render(request, "forms/home_formularios.html", contexto)


@login_required
def listar_formularios(request):
    """Lista todos os formulários dos clientes (preenchidos e não preenchidos)."""
    from consultancy.models import ClienteConsultoria, ClienteViagem, RespostaFormulario
    from contextlib import suppress
    
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    # Listar TODOS os formulários, independente de assessor
    clientes_ids = list(ClienteConsultoria.objects.values_list("pk", flat=True))
    
    # Buscar todas as viagens
    viagens = Viagem.objects.filter(
        clientes__pk__in=clientes_ids
    ).select_related(
        "pais_destino",
        "tipo_visto",
        "tipo_visto__formulario",
    ).prefetch_related("clientes").distinct().order_by("-data_prevista_viagem")
    
    # Função auxiliar para obter tipo_visto do cliente
    def _obter_tipo_visto_cliente(viagem, cliente):
        """Obtém o tipo de visto individual do cliente na viagem, ou o tipo de visto da viagem como fallback."""
        with suppress(ClienteViagem.DoesNotExist):
            cliente_viagem = ClienteViagem.objects.select_related('tipo_visto__formulario').get(
                viagem=viagem, cliente=cliente
            )
            if cliente_viagem.tipo_visto:
                return cliente_viagem.tipo_visto
        return viagem.tipo_visto
    
    # Função auxiliar para obter formulário por tipo_visto
    def _obter_formulario_por_tipo_visto(tipo_visto, apenas_ativo=True):
        """Obtém o formulário de um tipo de visto diretamente do banco de dados."""
        if not tipo_visto or not hasattr(tipo_visto, 'pk') or not tipo_visto.pk:
            return None
        try:
            if apenas_ativo:
                return FormularioVisto.objects.select_related('tipo_visto').get(
                    tipo_visto_id=tipo_visto.pk,
                    ativo=True
                )
            return FormularioVisto.objects.select_related('tipo_visto').get(
                tipo_visto_id=tipo_visto.pk
            )
        except FormularioVisto.DoesNotExist:
            return None
    
    # Preparar informações dos formulários
    formularios_respostas = []
    
    for viagem in viagens:
        # Buscar clientes da viagem vinculados ao usuário
        clientes_viagem = viagem.clientes.filter(pk__in=clientes_ids)
        
        if not clientes_viagem.exists():
            continue
        
        # Agrupar clientes por formulário (cada cliente pode ter um tipo_visto diferente)
        clientes_por_formulario = {}
        
        for cliente in clientes_viagem:
            # Obter o tipo_visto individual do cliente
            tipo_visto_cliente = _obter_tipo_visto_cliente(viagem, cliente)
            
            if not tipo_visto_cliente:
                continue
            
            # Buscar formulário diretamente do banco de dados
            formulario = _obter_formulario_por_tipo_visto(tipo_visto_cliente, apenas_ativo=True)
            
            if not formulario:
                continue
            
            # Usar chave única: viagem_id + formulario_id
            chave = f"{viagem.pk}_{formulario.pk}"
            
            if chave not in clientes_por_formulario:
                clientes_por_formulario[chave] = {
                    "viagem": viagem,
                    "formulario": formulario,
                    "clientes": [],
                }
            
            # Calcular informações do formulário para este cliente
            total_perguntas = formulario.perguntas.filter(ativo=True).count()
            total_respostas = RespostaFormulario.objects.filter(
                viagem=viagem,
                cliente=cliente
            ).count()
            
            clientes_por_formulario[chave]["clientes"].append({
                "cliente": cliente,
                "tipo_visto": tipo_visto_cliente,
                "total_perguntas": total_perguntas,
                "total_respostas": total_respostas,
                "completo": total_respostas == total_perguntas if total_perguntas > 0 else False,
            })
        
        # Adicionar ao resultado
        formularios_respostas.extend(clientes_por_formulario.values())
    
    contexto = {
        "formularios_respostas": formularios_respostas,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }

    return render(request, "forms/listar_formularios.html", contexto)


@login_required
def home_tipos_formulario(request):
    consultor = obter_consultor_usuario(request.user)
    if not usuario_tem_acesso_modulo(request.user, consultor, "Tipos de Formulario de Visto"):
        raise PermissionDenied
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

    return render(request, "forms/home_tipos_formulario.html", contexto)


@login_required
def criar_formulario(request):
    """Formulário para criar novo formulário de visto."""
    consultor = obter_consultor_usuario(request.user)

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
def listar_tipos_formulario(request):
    """Lista todos os tipos de formulário de visto."""
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

    return render(request, "forms/listar_tipos_formulario.html", contexto)


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
    return redirect("system:listar_tipos_formulario")


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
def selecionar_viagem_cliente_formulario(request):
    """Seleciona uma viagem e cliente para criar/preencher formulário."""
    from consultancy.models import ClienteConsultoria
    
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    # Se for admin, buscar todos os clientes
    if pode_gerenciar_todos:
        clientes_ids = list(ClienteConsultoria.objects.values_list("pk", flat=True))
    else:
        # Buscar apenas clientes vinculados ao usuário
        clientes_usuario = listar_clientes(request.user)
        clientes_ids = list(clientes_usuario.values_list("pk", flat=True))
    
    # Buscar viagens dos clientes do usuário que têm formulário
    viagens = Viagem.objects.filter(
        clientes__pk__in=clientes_ids,
        tipo_visto__formulario__isnull=False,
        tipo_visto__formulario__ativo=True
    ).select_related(
        "pais_destino",
        "tipo_visto",
        "tipo_visto__formulario",
    ).prefetch_related("clientes").distinct().order_by("-data_prevista_viagem")
    
    # Processar POST - redirecionar para editar formulário
    if request.method == "POST":
        viagem_id = request.POST.get("viagem_id")
        cliente_id = request.POST.get("cliente_id")
        
        if not viagem_id or not cliente_id:
            messages.error(request, "Por favor, selecione uma viagem e um cliente.")
            return redirect("system:selecionar_viagem_cliente_formulario")
        
        try:
            viagem = Viagem.objects.get(pk=viagem_id)
            cliente = ClienteConsultoria.objects.get(pk=cliente_id)
            
            # Verificar permissão
            if not pode_gerenciar_todos and int(cliente_id) not in clientes_ids:
                raise PermissionDenied("Você não tem permissão para acessar este cliente.")
            
            if cliente not in viagem.clientes.all():
                messages.error(request, "Este cliente não está vinculado a esta viagem.")
                return redirect("system:selecionar_viagem_cliente_formulario")
            
            # Redirecionar para editar formulário
            return redirect("system:editar_formulario_cliente", viagem_id=viagem_id, cliente_id=cliente_id)
        except (Viagem.DoesNotExist, ClienteConsultoria.DoesNotExist, ValueError):
            messages.error(request, "Viagem ou cliente não encontrado.")
            return redirect("system:selecionar_viagem_cliente_formulario")
    
    # Preparar dados para o template
    viagens_com_clientes = []
    for viagem in viagens:
        clientes_viagem = viagem.clientes.filter(pk__in=clientes_ids).select_related("cliente_principal")
        if clientes_viagem.exists():
            viagens_com_clientes.append({
                "viagem": viagem,
                "clientes": clientes_viagem,
            })
    
    contexto = {
        "viagens_com_clientes": viagens_com_clientes,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }
    
    return render(request, "forms/selecionar_viagem_cliente_formulario.html", contexto)


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

