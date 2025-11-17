"""
Views relacionadas a viagens e destinos.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from consultancy.forms import PaisDestinoForm, TipoVistoForm, ViagemForm
from consultancy.models import FormularioVisto, PaisDestino, RespostaFormulario, TipoVisto, Viagem
from system.views.client_views import obter_consultor_usuario, usuario_pode_gerenciar_todos


@login_required
def home_viagens(request):
    """Página inicial de viagens com opções de navegação."""
    consultor = obter_consultor_usuario(request.user)
    viagens = Viagem.objects.select_related(
        "pais_destino",
        "tipo_visto",
        "assessor_responsavel",
    ).prefetch_related("tipo_visto__formulario", "clientes").order_by("-data_prevista_viagem")[:10]

    # Buscar viagens com formulários não preenchidos
    viagens_com_formulario = []
    for viagem in viagens:
        try:
            formulario = viagem.tipo_visto.formulario
            if formulario and formulario.ativo:
                # Verificar quantos clientes não preencheram
                total_clientes = viagem.clientes.count()
                if total_clientes > 0:
                    # Contar quantos clientes já preencheram pelo menos uma pergunta
                    clientes_com_resposta = RespostaFormulario.objects.filter(
                        viagem=viagem
                    ).values_list("cliente_id", flat=True).distinct().count()
                    clientes_sem_resposta = total_clientes - clientes_com_resposta
                    if clientes_sem_resposta > 0:
                        viagens_com_formulario.append({
                            "viagem": viagem,
                            "total_clientes": total_clientes,
                            "clientes_sem_resposta": clientes_sem_resposta,
                        })
        except FormularioVisto.DoesNotExist:
            pass

    contexto = {
        "total_viagens": Viagem.objects.count(),
        "viagens": viagens,
        "viagens_formularios_nao_preenchidos": viagens_com_formulario,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "travel/home_viagens.html", contexto)


@login_required
def home_paises_destino(request):
    """Página inicial de países de destino com opções de navegação."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    paises = PaisDestino.objects.all().order_by("nome")[:10]
    total_paises = PaisDestino.objects.count()
    
    contexto = {
        "paises": paises,
        "total_paises": total_paises,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }
    
    return render(request, "travel/home_paises_destino.html", contexto)


@login_required
def home_tipos_visto(request):
    """Página inicial de tipos de visto com opções de navegação."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    tipos_visto = TipoVisto.objects.select_related("pais_destino").order_by("pais_destino__nome", "nome")[:10]
    total_tipos = TipoVisto.objects.count()
    
    contexto = {
        "tipos_visto": tipos_visto,
        "total_tipos": total_tipos,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }
    
    return render(request, "travel/home_tipos_visto.html", contexto)


@login_required
def criar_pais_destino(request):
    """Formulário para cadastrar novo país de destino."""
    consultor = obter_consultor_usuario(request.user)

    if request.method == "POST":
        form = PaisDestinoForm(data=request.POST, user=request.user)
        if form.is_valid():
            pais = form.save(commit=False)
            pais.criado_por = request.user
            pais.save()
            messages.success(request, f"País {form.cleaned_data['nome']} cadastrado com sucesso.")
            return redirect("system:home_paises_destino")
        messages.error(request, "Não foi possível cadastrar o país. Verifique os campos.")
    else:
        form = PaisDestinoForm(user=request.user)

    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "travel/criar_pais_destino.html", contexto)


@login_required
def criar_tipo_visto(request):
    """Formulário para cadastrar novo tipo de visto."""
    consultor = obter_consultor_usuario(request.user)

    if request.method == "POST":
        form = TipoVistoForm(data=request.POST, user=request.user)
        if form.is_valid():
            tipo_visto = form.save(commit=False)
            tipo_visto.criado_por = request.user
            tipo_visto.save()
            messages.success(request, f"Tipo de visto {form.cleaned_data['nome']} cadastrado com sucesso.")
            return redirect("system:home_tipos_visto")
        messages.error(request, "Não foi possível cadastrar o tipo de visto. Verifique os campos.")
    else:
        form = TipoVistoForm(user=request.user)

    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "travel/criar_tipo_visto.html", contexto)


@login_required
def criar_viagem(request):
    """Formulário para cadastrar nova viagem."""
    consultor = obter_consultor_usuario(request.user)

    if request.method == "POST":
        form = ViagemForm(data=request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Viagem cadastrada com sucesso.")
            return redirect("system:home_viagens")
        messages.error(request, "Não foi possível cadastrar a viagem. Verifique os campos.")
    else:
        form = ViagemForm(user=request.user)

    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "travel/criar_viagem.html", contexto)


@login_required
def listar_paises_destino(request):
    """Lista todos os países de destino."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    paises = PaisDestino.objects.all().order_by("nome")
    
    contexto = {
        "paises": paises,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }
    
    return render(request, "travel/listar_paises_destino.html", contexto)


@login_required
def editar_pais_destino(request, pk: int):
    """Formulário para editar país de destino existente."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar_todos:
        raise PermissionDenied
    
    pais = get_object_or_404(PaisDestino, pk=pk)
    
    if request.method == "POST":
        form = PaisDestinoForm(data=request.POST, instance=pais)
        if form.is_valid():
            form.save()
            messages.success(request, f"País {form.cleaned_data['nome']} atualizado com sucesso.")
            return redirect("system:listar_paises_destino")
        messages.error(request, "Não foi possível atualizar o país. Verifique os campos.")
    else:
        form = PaisDestinoForm(instance=pais)
    
    contexto = {
        "form": form,
        "pais": pais,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }
    
    return render(request, "travel/editar_pais_destino.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_pais_destino(request, pk: int):
    """Exclui um país de destino."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar_todos:
        raise PermissionDenied
    
    pais = get_object_or_404(PaisDestino, pk=pk)
    nome_pais = pais.nome
    pais.delete()
    
    messages.success(request, f"País {nome_pais} excluído com sucesso.")
    return redirect("system:listar_paises_destino")


@login_required
def listar_tipos_visto(request):
    """Lista todos os tipos de visto."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    tipos_visto = TipoVisto.objects.select_related("pais_destino").order_by("pais_destino__nome", "nome")
    
    contexto = {
        "tipos_visto": tipos_visto,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }
    
    return render(request, "travel/listar_tipos_visto.html", contexto)


@login_required
def editar_tipo_visto(request, pk: int):
    """Formulário para editar tipo de visto existente."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar_todos:
        raise PermissionDenied
    
    tipo_visto = get_object_or_404(TipoVisto.objects.select_related("pais_destino"), pk=pk)
    
    if request.method == "POST":
        form = TipoVistoForm(data=request.POST, instance=tipo_visto)
        if form.is_valid():
            form.save()
            messages.success(request, f"Tipo de visto {form.cleaned_data['nome']} atualizado com sucesso.")
            return redirect("system:listar_tipos_visto")
        messages.error(request, "Não foi possível atualizar o tipo de visto. Verifique os campos.")
    else:
        form = TipoVistoForm(instance=tipo_visto)
        # Garantir que o campo tipo_visto seja preenchido com o valor atual
        if tipo_visto.pais_destino:
            form.fields["pais_destino"].initial = tipo_visto.pais_destino.pk
    
    contexto = {
        "form": form,
        "tipo_visto": tipo_visto,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }
    
    return render(request, "travel/editar_tipo_visto.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_tipo_visto(request, pk: int):
    """Exclui um tipo de visto."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar_todos:
        raise PermissionDenied
    
    tipo_visto = get_object_or_404(TipoVisto, pk=pk)
    nome_tipo = tipo_visto.nome
    tipo_visto.delete()
    
    messages.success(request, f"Tipo de visto {nome_tipo} excluído com sucesso.")
    return redirect("system:listar_tipos_visto")


@login_required
def listar_viagens(request):
    """Lista todas as viagens com filtros."""
    from django.db.models import Q
    from datetime import datetime
    from consultancy.models import ClienteConsultoria
    from system.models import UsuarioConsultoria
    
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    eh_administrador = pode_gerenciar_todos
    
    # Filtrar viagens: admin vê todas, assessor vê apenas as suas
    if pode_gerenciar_todos:
        viagens = Viagem.objects.select_related(
            "pais_destino",
            "tipo_visto",
            "assessor_responsavel",
        ).prefetch_related("tipo_visto__formulario", "clientes", "clientes__parceiro_indicador").order_by("-data_prevista_viagem")
    else:
        # Assessor vê apenas suas próprias viagens
        viagens = Viagem.objects.select_related(
            "pais_destino",
            "tipo_visto",
            "assessor_responsavel",
        ).prefetch_related("tipo_visto__formulario", "clientes", "clientes__parceiro_indicador").filter(
            assessor_responsavel=consultor
        ).order_by("-data_prevista_viagem")
    
    # Aplicar filtros
    filtros_aplicados = {}
    
    # Filtro por assessor responsável
    assessor_id = request.GET.get("assessor")
    if assessor_id:
        try:
            viagens = viagens.filter(assessor_responsavel_id=int(assessor_id))
            filtros_aplicados["assessor"] = int(assessor_id)
        except (ValueError, TypeError):
            pass
    
    # Filtro por país de destino
    pais_id = request.GET.get("pais")
    if pais_id:
        try:
            viagens = viagens.filter(pais_destino_id=int(pais_id))
            filtros_aplicados["pais"] = int(pais_id)
        except (ValueError, TypeError):
            pass
    
    # Filtro por tipo de visto
    tipo_visto_id = request.GET.get("tipo_visto")
    if tipo_visto_id:
        try:
            viagens = viagens.filter(tipo_visto_id=int(tipo_visto_id))
            filtros_aplicados["tipo_visto"] = int(tipo_visto_id)
        except (ValueError, TypeError):
            pass
    
    # Filtro por data prevista da viagem (range)
    data_viagem_inicio = request.GET.get("data_viagem_inicio")
    data_viagem_fim = request.GET.get("data_viagem_fim")
    if data_viagem_inicio:
        try:
            data_inicio = datetime.strptime(data_viagem_inicio, "%Y-%m-%d").date()
            viagens = viagens.filter(data_prevista_viagem__gte=data_inicio)
            filtros_aplicados["data_viagem_inicio"] = data_viagem_inicio
        except (ValueError, TypeError):
            pass
    if data_viagem_fim:
        try:
            data_fim = datetime.strptime(data_viagem_fim, "%Y-%m-%d").date()
            viagens = viagens.filter(data_prevista_viagem__lte=data_fim)
            filtros_aplicados["data_viagem_fim"] = data_viagem_fim
        except (ValueError, TypeError):
            pass
    
    # Filtro por data prevista de retorno (range)
    data_retorno_inicio = request.GET.get("data_retorno_inicio")
    data_retorno_fim = request.GET.get("data_retorno_fim")
    if data_retorno_inicio:
        try:
            data_inicio = datetime.strptime(data_retorno_inicio, "%Y-%m-%d").date()
            viagens = viagens.filter(data_prevista_retorno__gte=data_inicio)
            filtros_aplicados["data_retorno_inicio"] = data_retorno_inicio
        except (ValueError, TypeError):
            pass
    if data_retorno_fim:
        try:
            data_fim = datetime.strptime(data_retorno_fim, "%Y-%m-%d").date()
            viagens = viagens.filter(data_prevista_retorno__lte=data_fim)
            filtros_aplicados["data_retorno_fim"] = data_retorno_fim
        except (ValueError, TypeError):
            pass
    
    # Filtro por valor assessoria (range)
    valor_min = request.GET.get("valor_min")
    valor_max = request.GET.get("valor_max")
    if valor_min:
        try:
            viagens = viagens.filter(valor_assessoria__gte=float(valor_min))
            filtros_aplicados["valor_min"] = valor_min
        except (ValueError, TypeError):
            pass
    if valor_max:
        try:
            viagens = viagens.filter(valor_assessoria__lte=float(valor_max))
            filtros_aplicados["valor_max"] = valor_max
        except (ValueError, TypeError):
            pass
    
    # Filtro por cliente vinculado
    cliente_id = request.GET.get("cliente")
    if cliente_id:
        try:
            viagens = viagens.filter(clientes__id=int(cliente_id)).distinct()
            filtros_aplicados["cliente"] = int(cliente_id)
        except (ValueError, TypeError):
            pass
    
    # Filtro por parceiro vinculado (através dos clientes)
    parceiro_id = request.GET.get("parceiro")
    if parceiro_id:
        try:
            viagens = viagens.filter(clientes__parceiro_indicador_id=int(parceiro_id)).distinct()
            filtros_aplicados["parceiro"] = int(parceiro_id)
        except (ValueError, TypeError):
            pass
    
    # Filtro por data de criação (range)
    data_criacao_inicio = request.GET.get("data_criacao_inicio")
    data_criacao_fim = request.GET.get("data_criacao_fim")
    if data_criacao_inicio:
        try:
            data_inicio = datetime.strptime(data_criacao_inicio, "%Y-%m-%d").date()
            viagens = viagens.filter(criado_em__date__gte=data_inicio)
            filtros_aplicados["data_criacao_inicio"] = data_criacao_inicio
        except (ValueError, TypeError):
            pass
    if data_criacao_fim:
        try:
            data_fim = datetime.strptime(data_criacao_fim, "%Y-%m-%d").date()
            viagens = viagens.filter(criado_em__date__lte=data_fim)
            filtros_aplicados["data_criacao_fim"] = data_criacao_fim
        except (ValueError, TypeError):
            pass
    
    # Preparar informações sobre formulários para cada viagem
    viagens_com_info = []
    for viagem in viagens:
        tem_formulario = False
        total_clientes = viagem.clientes.count()
        clientes_com_resposta = 0
        
        try:
            formulario = viagem.tipo_visto.formulario
            if formulario and formulario.ativo:
                tem_formulario = True
                if total_clientes > 0:
                    # Contar quantos clientes já preencheram pelo menos uma pergunta
                    clientes_com_resposta = RespostaFormulario.objects.filter(
                        viagem=viagem
                    ).values_list("cliente_id", flat=True).distinct().count()
        except FormularioVisto.DoesNotExist:
            pass
        
        # Buscar parceiros vinculados através dos clientes
        parceiros_vinculados = set()
        for cliente in viagem.clientes.all():
            if cliente.parceiro_indicador:
                parceiros_vinculados.add(cliente.parceiro_indicador)
        
        # Verificar se o assessor pode editar/excluir (apenas se for o responsável)
        pode_editar_excluir = pode_gerenciar_todos or (consultor and viagem.assessor_responsavel == consultor)
        
        viagens_com_info.append({
            "viagem": viagem,
            "tem_formulario": tem_formulario,
            "total_clientes": total_clientes,
            "clientes_com_resposta": clientes_com_resposta,
            "clientes_sem_resposta": total_clientes - clientes_com_resposta if tem_formulario else 0,
            "pode_editar_excluir": pode_editar_excluir,
            "parceiros_vinculados": list(parceiros_vinculados),
        })
    
    # Buscar opções para os filtros
    assessores = UsuarioConsultoria.objects.filter(ativo=True).order_by("nome")
    paises = PaisDestino.objects.filter(ativo=True).order_by("nome")
    tipos_visto = TipoVisto.objects.filter(ativo=True).select_related("pais_destino").order_by("pais_destino__nome", "nome")
    clientes = ClienteConsultoria.objects.all().order_by("nome")
    from consultancy.models import Partner
    parceiros = Partner.objects.filter(ativo=True).order_by("nome_empresa", "nome_responsavel")
    
    contexto = {
        "viagens_com_info": viagens_com_info,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "eh_administrador": eh_administrador,
        "assessores": assessores,
        "paises": paises,
        "tipos_visto": tipos_visto,
        "clientes": clientes,
        "parceiros": parceiros,
        "filtros_aplicados": filtros_aplicados,
    }
    
    return render(request, "travel/listar_viagens.html", contexto)


@login_required
def editar_viagem(request, pk: int):
    """Formulário para editar viagem existente."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    viagem = get_object_or_404(
        Viagem.objects.select_related("pais_destino", "tipo_visto", "assessor_responsavel"),
        pk=pk
    )
    
    # Verificar se o usuário tem permissão: admin pode editar todas, assessor apenas as suas
    if not pode_gerenciar_todos:
        if not consultor or viagem.assessor_responsavel != consultor:
            raise PermissionDenied("Você não tem permissão para editar esta viagem.")
    
    if request.method == "POST":
        form = ViagemForm(data=request.POST, user=request.user, instance=viagem)
        if form.is_valid():
            form.save()
            messages.success(request, "Viagem atualizada com sucesso.")
            return redirect("system:listar_viagens")
        messages.error(request, "Não foi possível atualizar a viagem. Verifique os campos.")
    else:
        form = ViagemForm(user=request.user, instance=viagem)
    
    contexto = {
        "form": form,
        "viagem": viagem,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }
    
    return render(request, "travel/editar_viagem.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_viagem(request, pk: int):
    """Exclui uma viagem."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    viagem = get_object_or_404(
        Viagem.objects.select_related("assessor_responsavel"),
        pk=pk
    )
    
    # Verificar se o usuário tem permissão: admin pode excluir todas, assessor apenas as suas
    if not pode_gerenciar_todos:
        if not consultor or viagem.assessor_responsavel != consultor:
            raise PermissionDenied("Você não tem permissão para excluir esta viagem.")
    
    pais_destino = viagem.pais_destino.nome
    data_viagem = viagem.data_prevista_viagem.strftime("%d/%m/%Y")
    viagem.delete()
    
    messages.success(request, f"Viagem para {pais_destino} ({data_viagem}) excluída com sucesso.")
    return redirect("system:listar_viagens")


@login_required
@require_GET
def api_tipos_visto(request):
    """API para buscar tipos de visto por país via AJAX."""
    pais_id = request.GET.get("pais", "").strip()

    if not pais_id:
        return JsonResponse({"error": "Informe um país."}, status=400)

    try:
        tipos_visto = TipoVisto.objects.filter(
            pais_destino_id=int(pais_id),
            ativo=True
        ).order_by("nome")

        data = [{"id": tipo.id, "nome": tipo.nome} for tipo in tipos_visto]
        return JsonResponse(data, safe=False)
    except (ValueError, TypeError):
        return JsonResponse({"error": "País inválido."}, status=400)


@login_required
def listar_formularios_viagem(request, viagem_id: int):
    """Lista os formulários dos clientes de uma viagem específica."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    viagem = get_object_or_404(
        Viagem.objects.select_related("pais_destino", "tipo_visto", "assessor_responsavel"),
        pk=viagem_id
    )
    
    # Verificar se o usuário tem permissão: admin pode ver todas, assessor apenas as suas
    if not pode_gerenciar_todos:
        if not consultor or viagem.assessor_responsavel != consultor:
            raise PermissionDenied("Você não tem permissão para acessar esta viagem.")
    
    # Verificar se há formulário vinculado
    formulario = None
    try:
        formulario = viagem.tipo_visto.formulario
    except FormularioVisto.DoesNotExist:
        pass
    
    # Buscar clientes e verificar status dos formulários
    clientes_com_info = []
    for cliente in viagem.clientes.all():
        tem_resposta = False
        total_perguntas = 0
        total_respostas = 0
        
        if formulario and formulario.ativo:
            perguntas = formulario.perguntas.filter(ativo=True)
            total_perguntas = perguntas.count()
            if total_perguntas > 0:
                respostas = RespostaFormulario.objects.filter(
                    viagem=viagem,
                    cliente=cliente
                )
                total_respostas = respostas.count()
                tem_resposta = total_respostas > 0
        
        clientes_com_info.append({
            "cliente": cliente,
            "tem_resposta": tem_resposta,
            "total_perguntas": total_perguntas,
            "total_respostas": total_respostas,
            "completo": tem_resposta and total_respostas == total_perguntas if total_perguntas > 0 else False,
        })
    
    contexto = {
        "viagem": viagem,
        "formulario": formulario,
        "clientes_com_info": clientes_com_info,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }
    
    return render(request, "travel/listar_formularios_viagem.html", contexto)


@login_required
def editar_formulario_cliente(request, viagem_id: int, cliente_id: int):
    """Permite editar o formulário de um cliente específico de uma viagem."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    viagem = get_object_or_404(
        Viagem.objects.select_related("tipo_visto__formulario"),
        pk=viagem_id
    )
    
    # Verificar se o usuário tem permissão: admin pode editar todas, assessor apenas as suas
    if not pode_gerenciar_todos:
        if not consultor or viagem.assessor_responsavel != consultor:
            raise PermissionDenied("Você não tem permissão para acessar esta viagem.")
    
    from consultancy.models import ClienteConsultoria
    cliente = get_object_or_404(ClienteConsultoria, pk=cliente_id)
    
    # Verificar se o cliente está vinculado à viagem
    if cliente not in viagem.clientes.all():
        raise PermissionDenied("Este cliente não está vinculado a esta viagem.")
    
    # Verificar se há formulário
    formulario = None
    try:
        formulario = viagem.tipo_visto.formulario
    except FormularioVisto.DoesNotExist:
        pass
    
    if not formulario or not formulario.ativo:
        messages.warning(
            request,
            "Este tipo de visto não possui um formulário cadastrado ou o formulário está inativo.",
        )
        return redirect("system:listar_formularios_viagem", viagem_id=viagem_id)
    
    # Buscar perguntas e respostas
    perguntas = (
        formulario.perguntas.filter(ativo=True)
        .prefetch_related("opcoes")
        .order_by("ordem", "pergunta")
    )
    
    respostas_list = RespostaFormulario.objects.filter(
        viagem=viagem, cliente=cliente
    ).select_related("resposta_selecao")
    
    respostas_existentes = {r.pergunta_id: r for r in respostas_list}
    respostas_ids = list(respostas_existentes.keys())
    
    if request.method == "POST":
        # Processar todas as respostas enviadas
        respostas_salvas = 0
        erros = []
        
        for pergunta in perguntas:
            campo_name = f"pergunta_{pergunta.pk}"
            valor = request.POST.get(campo_name)
            
            # Verificar se é obrigatório
            if pergunta.obrigatorio and not valor:
                erros.append(f"A pergunta '{pergunta.pergunta}' é obrigatória.")
                continue
            
            # Buscar ou criar resposta
            resposta, created = RespostaFormulario.objects.get_or_create(
                viagem=viagem,
                cliente=cliente,
                pergunta=pergunta,
                defaults={},
            )
            
            # Atualizar resposta de acordo com o tipo
            if pergunta.tipo_campo == "texto":
                resposta.resposta_texto = valor or ""
                resposta.resposta_data = None
                resposta.resposta_numero = None
                resposta.resposta_booleano = None
                resposta.resposta_selecao = None
            elif pergunta.tipo_campo == "data":
                from django.utils.dateparse import parse_date
                resposta.resposta_data = parse_date(valor) if valor else None
                resposta.resposta_texto = ""
                resposta.resposta_numero = None
                resposta.resposta_booleano = None
                resposta.resposta_selecao = None
            elif pergunta.tipo_campo == "numero":
                from decimal import Decimal, InvalidOperation
                try:
                    resposta.resposta_numero = Decimal(valor) if valor else None
                except (InvalidOperation, ValueError):
                    erros.append(f"Valor inválido para a pergunta '{pergunta.pergunta}'.")
                    continue
                resposta.resposta_texto = ""
                resposta.resposta_data = None
                resposta.resposta_booleano = None
                resposta.resposta_selecao = None
            elif pergunta.tipo_campo == "booleano":
                resposta.resposta_booleano = valor == "sim" if valor else None
                resposta.resposta_texto = ""
                resposta.resposta_data = None
                resposta.resposta_numero = None
                resposta.resposta_selecao = None
            elif pergunta.tipo_campo == "selecao":
                from consultancy.models import OpcaoSelecao
                try:
                    opcao_id = int(valor) if valor else None
                    resposta.resposta_selecao = (
                        OpcaoSelecao.objects.get(pk=opcao_id, pergunta=pergunta)
                        if opcao_id
                        else None
                    )
                except (ValueError, OpcaoSelecao.DoesNotExist):
                    erros.append(f"Opção inválida para a pergunta '{pergunta.pergunta}'.")
                    continue
                resposta.resposta_texto = ""
                resposta.resposta_data = None
                resposta.resposta_numero = None
                resposta.resposta_booleano = None
            
            resposta.save()
            respostas_salvas += 1
        
        if erros:
            for erro in erros:
                messages.error(request, erro)
        else:
            messages.success(
                request,
                f"Formulário do cliente {cliente.nome} salvo com sucesso! {respostas_salvas} resposta(s) registrada(s).",
            )
            return redirect("system:listar_formularios_viagem", viagem_id=viagem_id)
    
    contexto = {
        "viagem": viagem,
        "cliente": cliente,
        "formulario": formulario,
        "perguntas": perguntas,
        "respostas_existentes": respostas_existentes,
        "respostas_ids": respostas_ids,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }
    
    return render(request, "travel/editar_formulario_cliente.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_respostas_formulario(request, viagem_id: int, cliente_id: int):
    """Exclui todas as respostas de um formulário de um cliente específico."""
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    viagem = get_object_or_404(
        Viagem.objects.select_related("assessor_responsavel"),
        pk=viagem_id
    )
    
    # Verificar se o usuário tem permissão: apenas administradores podem excluir
    if not pode_gerenciar_todos:
        raise PermissionDenied("Apenas administradores podem excluir respostas de formulários.")
    
    from consultancy.models import ClienteConsultoria
    cliente = get_object_or_404(ClienteConsultoria, pk=cliente_id)
    
    # Verificar se o cliente está vinculado à viagem
    if cliente not in viagem.clientes.all():
        raise PermissionDenied("Este cliente não está vinculado a esta viagem.")
    
    # Excluir todas as respostas do cliente para esta viagem
    respostas_deletadas = RespostaFormulario.objects.filter(
        viagem=viagem,
        cliente=cliente
    ).delete()[0]
    
    messages.success(
        request,
        f"Todas as respostas do formulário do cliente {cliente.nome} foram excluídas com sucesso. ({respostas_deletadas} resposta(s) removida(s))"
    )
    
    return redirect("system:listar_formularios_viagem", viagem_id=viagem_id)

