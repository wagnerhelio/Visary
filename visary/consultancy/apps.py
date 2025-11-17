import json
import os
from contextlib import suppress
from pathlib import Path

from django.apps import AppConfig, apps as django_apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models.signals import m2m_changed, post_migrate, post_save
from django.dispatch import receiver


def _get_models():
    PaisDestino = django_apps.get_model("consultancy", "PaisDestino")
    TipoVisto = django_apps.get_model("consultancy", "TipoVisto")
    Partner = django_apps.get_model("consultancy", "Partner")
    StatusProcesso = django_apps.get_model("consultancy", "StatusProcesso")
    FormularioVisto = django_apps.get_model("consultancy", "FormularioVisto")
    PerguntaFormulario = django_apps.get_model("consultancy", "PerguntaFormulario")
    OpcaoSelecao = django_apps.get_model("consultancy", "OpcaoSelecao")
    User = get_user_model()
    return PaisDestino, TipoVisto, Partner, StatusProcesso, FormularioVisto, PerguntaFormulario, OpcaoSelecao, User


def _atualizar_campos(instancia, valores):
    """Atualiza campos de uma instância se os valores forem diferentes."""
    campos_em_mudanca = [
        campo for campo, valor in valores.items() if getattr(instancia, campo) != valor
    ]
    if not campos_em_mudanca:
        return
    for campo in campos_em_mudanca:
        setattr(instancia, campo, valores[campo])
    instancia.save(update_fields=campos_em_mudanca)


def _ensure_paises_destino(PaisDestino, User, paises_definitions):
    """Garante que os países de destino estejam cadastrados."""
    # Buscar ou criar um usuário admin para ser o criador
    admin_user, _ = User.objects.get_or_create(
        username="admin",
        defaults={
            "email": "admin@visary.com",
            "is_staff": True,
            "is_superuser": True,
        },
    )
    if not admin_user.is_superuser:
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.save()

    paises_por_nome = {}
    for definicao in paises_definitions:
        defaults = {
            "nome": definicao["nome"],
            "codigo_iso": definicao.get("codigo_iso", ""),
            "criado_por": admin_user,
            "ativo": definicao.get("ativo", True),
        }
        pais, created = PaisDestino.objects.get_or_create(
            nome=definicao["nome"], defaults=defaults
        )
        if not created:
            _atualizar_campos(
                pais,
                {
                    "codigo_iso": definicao.get("codigo_iso", ""),
                    "ativo": definicao.get("ativo", True),
                },
            )
        paises_por_nome[pais.nome] = pais
    return paises_por_nome


def _ensure_tipos_visto(TipoVisto, User, paises_por_nome, tipos_visto_definitions):
    """Garante que os tipos de visto estejam cadastrados."""
    # Buscar ou criar um usuário admin para ser o criador
    admin_user, _ = User.objects.get_or_create(
        username="admin",
        defaults={
            "email": "admin@visary.com",
            "is_staff": True,
            "is_superuser": True,
        },
    )
    if not admin_user.is_superuser:
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.save()

    tipos_visto_por_nome = {}
    for definicao in tipos_visto_definitions:
        pais_nome = definicao["pais"]
        if pais_nome not in paises_por_nome:
            continue  # Pular se o país não existir

        pais = paises_por_nome[pais_nome]
        defaults = {
            "pais_destino": pais,
            "nome": definicao["nome"],
            "descricao": definicao.get("descricao", ""),
            "criado_por": admin_user,
            "ativo": definicao.get("ativo", True),
        }
        tipo_visto, created = TipoVisto.objects.get_or_create(
            pais_destino=pais, nome=definicao["nome"], defaults=defaults
        )
        if not created:
            _atualizar_campos(
                tipo_visto,
                {
                    "descricao": definicao.get("descricao", ""),
                    "ativo": definicao.get("ativo", True),
                },
            )
        # Armazenar tipo de visto por nome para uso posterior
        tipos_visto_por_nome[definicao["nome"]] = tipo_visto
    return tipos_visto_por_nome


def _load_paises_definitions():
    """Carrega países de destino a partir de variável de ambiente."""
    raw = os.environ.get("CONSULTANCY_SEED_PAISES")
    
    if not raw:
        # Retorna lista vazia se não houver variável de ambiente
        return []
    
    try:
        paises = json.loads(raw)
        if not isinstance(paises, list):
            raise ImproperlyConfigured("CONSULTANCY_SEED_PAISES deve ser uma lista de objetos JSON.")
        
        campos_obrigatorios = {"nome"}
        for posicao, definicao in enumerate(paises, start=1):
            if not isinstance(definicao, dict):
                raise ImproperlyConfigured(
                    f"CONSULTANCY_SEED_PAISES posição {posicao} deve ser um objeto JSON."
                )
            if campos_ausentes := campos_obrigatorios - definicao.keys():
                raise ImproperlyConfigured(
                    f"CONSULTANCY_SEED_PAISES posição {posicao} sem campos: {', '.join(sorted(campos_ausentes))}."
                )
        return paises
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(
            "CONSULTANCY_SEED_PAISES deve conter um JSON válido."
        ) from exc


def _load_tipos_visto_definitions():
    """Carrega tipos de visto a partir de variável de ambiente."""
    raw = os.environ.get("CONSULTANCY_SEED_TIPOS_VISTO")
    
    if not raw:
        # Retorna lista vazia se não houver variável de ambiente
        return []
    
    try:
        tipos_visto = json.loads(raw)
        if not isinstance(tipos_visto, list):
            raise ImproperlyConfigured("CONSULTANCY_SEED_TIPOS_VISTO deve ser uma lista de objetos JSON.")
        
        campos_obrigatorios = {"pais", "nome"}
        for posicao, definicao in enumerate(tipos_visto, start=1):
            if not isinstance(definicao, dict):
                raise ImproperlyConfigured(
                    f"CONSULTANCY_SEED_TIPOS_VISTO posição {posicao} deve ser um objeto JSON."
                )
            if campos_ausentes := campos_obrigatorios - definicao.keys():
                raise ImproperlyConfigured(
                    f"CONSULTANCY_SEED_TIPOS_VISTO posição {posicao} sem campos: {', '.join(sorted(campos_ausentes))}."
                )
        return tipos_visto
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(
            "CONSULTANCY_SEED_TIPOS_VISTO deve conter um JSON válido."
        ) from exc


def _ensure_partners(Partner, User, partners_definitions):
    """Garante que os parceiros estejam cadastrados."""
    # Buscar ou criar um usuário admin para ser o criador
    admin_user, _ = User.objects.get_or_create(
        username="admin",
        defaults={
            "email": "admin@visary.com",
            "is_staff": True,
            "is_superuser": True,
        },
    )
    if not admin_user.is_superuser:
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.save()

    for definicao in partners_definitions:
        defaults = {
            "nome_responsavel": definicao["nome_responsavel"],
            "nome_empresa": definicao.get("nome_empresa", ""),
            "cpf": definicao.get("cpf", ""),
            "cnpj": definicao.get("cnpj", ""),
            "email": definicao["email"],
            "telefone": definicao["telefone"],
            "segmento": definicao.get("segmento", "outros"),
            "cidade": definicao["cidade"],
            "estado": definicao["estado"],
            "criado_por": admin_user,
            "ativo": definicao.get("ativo", True),
        }
        # Definir senha antes de criar
        from django.contrib.auth.hashers import make_password
        senha = definicao.get("senha")
        if senha:
            defaults["senha"] = make_password(senha)
        else:
            # Senha padrão se não fornecida
            defaults["senha"] = make_password("parceiro123")
        
        partner, created = Partner.objects.get_or_create(
            email=definicao["email"], defaults=defaults
        )
        if not created:
            # Atualizar campos se necessário
            _atualizar_campos(
                partner,
                {
                    "nome_responsavel": definicao["nome_responsavel"],
                    "nome_empresa": definicao.get("nome_empresa", ""),
                    "cpf": definicao.get("cpf", ""),
                    "cnpj": definicao.get("cnpj", ""),
                    "telefone": definicao["telefone"],
                    "segmento": definicao.get("segmento", "outros"),
                    "cidade": definicao["cidade"],
                    "estado": definicao["estado"],
                    "ativo": definicao.get("ativo", True),
                },
            )
            # Atualizar senha se fornecida
            if senha := definicao.get("senha"):
                partner.set_password(senha)
                partner.save()


def _load_partners_definitions():
    """Carrega parceiros a partir de variável de ambiente."""
    raw = os.environ.get("CONSULTANCY_SEED_PARTNERS")
    
    if not raw:
        # Retorna lista vazia se não houver variável de ambiente
        return []
    
    try:
        partners = json.loads(raw)
        if not isinstance(partners, list):
            raise ImproperlyConfigured("CONSULTANCY_SEED_PARTNERS deve ser uma lista de objetos JSON.")
        
        campos_obrigatorios = {"nome_responsavel", "email", "telefone", "cidade", "estado"}
        for posicao, definicao in enumerate(partners, start=1):
            if not isinstance(definicao, dict):
                raise ImproperlyConfigured(
                    f"CONSULTANCY_SEED_PARTNERS posição {posicao} deve ser um objeto JSON."
                )
            if campos_ausentes := campos_obrigatorios - definicao.keys():
                raise ImproperlyConfigured(
                    f"CONSULTANCY_SEED_PARTNERS posição {posicao} sem campos: {', '.join(sorted(campos_ausentes))}."
                )
        return partners
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(
            "CONSULTANCY_SEED_PARTNERS deve conter um JSON válido."
        ) from exc


def _ensure_status_processo(StatusProcesso, TipoVisto, tipos_visto_por_nome, status_definitions):
    """Garante que os status de processos estejam cadastrados."""
    for definicao in status_definitions:
        tipo_visto_nome = definicao.get("tipo_visto")
        tipo_visto = None
        
        # Se tipo_visto foi fornecido, buscar o objeto correspondente
        if tipo_visto_nome:
            tipo_visto = tipos_visto_por_nome.get(tipo_visto_nome)
            # Se o tipo de visto não existir, pular este status
            if not tipo_visto:
                continue
        
        # Usar nome como chave única (sem tipo_visto) para evitar duplicatas
        defaults = {
            "tipo_visto": tipo_visto,
            "nome": definicao["nome"],
            "prazo_padrao_dias": definicao.get("prazo_padrao_dias", 0),
            "ordem": definicao.get("ordem", 0),
            "ativo": definicao.get("ativo", True),
        }
        # Buscar por nome apenas (permitindo que o mesmo nome seja usado para diferentes tipos ou geral)
        status, created = StatusProcesso.objects.get_or_create(
            nome=definicao["nome"],
            tipo_visto=tipo_visto,
            defaults=defaults
        )
        if not created:
            _atualizar_campos(
                status,
                {
                    "tipo_visto": tipo_visto,
                    "prazo_padrao_dias": definicao.get("prazo_padrao_dias", 0),
                    "ordem": definicao.get("ordem", 0),
                    "ativo": definicao.get("ativo", True),
                },
            )


def _load_status_processo_definitions():
    """Carrega status de processos a partir de variável de ambiente."""
    raw = os.environ.get("CONSULTANCY_SEED_STATUS_PROCESSO")
    
    if not raw:
        # Retorna lista vazia se não houver variável de ambiente
        return []
    
    try:
        status_list = json.loads(raw)
        if not isinstance(status_list, list):
            raise ImproperlyConfigured("CONSULTANCY_SEED_STATUS_PROCESSO deve ser uma lista de objetos JSON.")
        
        campos_obrigatorios = {"nome"}
        for posicao, definicao in enumerate(status_list, start=1):
            if not isinstance(definicao, dict):
                raise ImproperlyConfigured(
                    f"CONSULTANCY_SEED_STATUS_PROCESSO posição {posicao} deve ser um objeto JSON."
                )
            if campos_ausentes := campos_obrigatorios - definicao.keys():
                raise ImproperlyConfigured(
                    f"CONSULTANCY_SEED_STATUS_PROCESSO posição {posicao} sem campos: {', '.join(sorted(campos_ausentes))}."
                )
            # tipo_visto é opcional - se não fornecido, o status será geral (disponível para todos)
        return status_list
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(
            "CONSULTANCY_SEED_STATUS_PROCESSO deve conter um JSON válido."
        ) from exc


def _load_formularios_definitions():
    """Carrega formulários a partir de variável de ambiente ou arquivos JSON em forms_ini."""
    formularios = []
    
    # Primeiro, tenta carregar da variável de ambiente
    raw = os.environ.get("CONSULTANCY_SEED_FORMULARIOS")
    if raw:
        with suppress(json.JSONDecodeError):
            formularios_env = json.loads(raw)
            if isinstance(formularios_env, list):
                formularios.extend(formularios_env)
    
    # Carrega arquivos JSON do diretório forms_ini
    with suppress(Exception):
        # Caminho para o diretório forms_ini (relativo ao diretório static)
        base_dir = Path(settings.BASE_DIR)
        forms_ini_dir = base_dir / "static" / "forms_ini"
        
        if forms_ini_dir.is_dir():
            for arquivo_json in forms_ini_dir.glob("*.json"):
                with suppress(json.JSONDecodeError, IOError):
                    with open(arquivo_json, "r", encoding="utf-8") as f:
                        dados = json.load(f)
                        if isinstance(dados, list):
                            formularios.extend(dados)
                        elif isinstance(dados, dict) and "tipo_visto" in dados:
                            # Se for um único objeto, adiciona como lista
                            formularios.append(dados)
    
    # Valida os formulários carregados
    campos_obrigatorios = {"tipo_visto", "perguntas"}
    for posicao, definicao in enumerate(formularios, start=1):
        if not isinstance(definicao, dict):
            raise ImproperlyConfigured(
                f"Formulário posição {posicao} deve ser um objeto JSON."
            )
        if campos_ausentes := campos_obrigatorios - definicao.keys():
            raise ImproperlyConfigured(
                f"Formulário posição {posicao} sem campos: {', '.join(sorted(campos_ausentes))}."
            )
        # Validar perguntas
        if not isinstance(definicao["perguntas"], list):
            raise ImproperlyConfigured(
                f"Formulário posição {posicao}: 'perguntas' deve ser uma lista."
            )
        for idx, pergunta in enumerate(definicao["perguntas"], start=1):
            if not isinstance(pergunta, dict):
                raise ImproperlyConfigured(
                    f"Formulário posição {posicao}, pergunta {idx} deve ser um objeto JSON."
                )
            campos_obrigatorios_pergunta = {"pergunta", "tipo_campo", "ordem"}
            if campos_ausentes_pergunta := campos_obrigatorios_pergunta - pergunta.keys():
                raise ImproperlyConfigured(
                    f"Formulário posição {posicao}, pergunta {idx} sem campos: {', '.join(sorted(campos_ausentes_pergunta))}."
                )
    
    return formularios


def _ensure_formularios(FormularioVisto, PerguntaFormulario, OpcaoSelecao, TipoVisto, tipos_visto_por_nome, formularios_definitions):
    """Garante que os formulários e perguntas estejam cadastrados."""
    for definicao in formularios_definitions:
        tipo_visto_nome = definicao.get("tipo_visto")
        if not tipo_visto_nome:
            continue  # Pular se não houver tipo_visto definido
        
        tipo_visto = tipos_visto_por_nome.get(tipo_visto_nome)
        if not tipo_visto:
            continue  # Pular se o tipo de visto não existir
        
        # Criar ou atualizar formulário
        formulario, created = FormularioVisto.objects.get_or_create(
            tipo_visto=tipo_visto,
            defaults={"ativo": True}
        )
        if not created:
            formulario.ativo = True
            formulario.save()
        
        # Criar ou atualizar perguntas
        for pergunta_def in definicao.get("perguntas", []):
            defaults = {
                "formulario": formulario,
                "pergunta": pergunta_def["pergunta"],
                "tipo_campo": pergunta_def["tipo_campo"],
                "obrigatorio": pergunta_def.get("obrigatorio", False),
                "ordem": pergunta_def["ordem"],
                "ativo": pergunta_def.get("ativo", True),
            }
            pergunta, created_pergunta = PerguntaFormulario.objects.get_or_create(
                formulario=formulario,
                ordem=pergunta_def["ordem"],
                defaults=defaults
            )
            if not created_pergunta:
                _atualizar_campos(
                    pergunta,
                    {
                        "pergunta": pergunta_def["pergunta"],
                        "tipo_campo": pergunta_def["tipo_campo"],
                        "obrigatorio": pergunta_def.get("obrigatorio", False),
                        "ativo": pergunta_def.get("ativo", True),
                    },
                )
            
            # Se for tipo "selecao", criar opções
            if pergunta_def["tipo_campo"] == "selecao" and "opcoes" in pergunta_def:
                opcoes_list = pergunta_def["opcoes"]
                if isinstance(opcoes_list, list):
                    for idx, opcao_texto in enumerate(opcoes_list):
                        opcao, _ = OpcaoSelecao.objects.get_or_create(
                            pergunta=pergunta,
                            texto=opcao_texto,
                            defaults={
                                "ordem": idx + 1,
                                "ativo": True,
                            }
                        )
                        if not _:
                            _atualizar_campos(
                                opcao,
                                {
                                    "ordem": idx + 1,
                                    "ativo": True,
                                },
                            )


def ensure_initial_consultancy_data(sender, **kwargs):
    """Garante que os dados iniciais de países, tipos de visto, parceiros, status de processos e formulários estejam cadastrados."""
    if sender.name != "consultancy":
        return

    try:
        PaisDestino, TipoVisto, Partner, StatusProcesso, FormularioVisto, PerguntaFormulario, OpcaoSelecao, User = _get_models()
    except LookupError:
        # Modelos ainda não foram criados
        return

    paises_definitions = _load_paises_definitions()
    tipos_visto_definitions = _load_tipos_visto_definitions()
    partners_definitions = _load_partners_definitions()
    status_processo_definitions = _load_status_processo_definitions()
    formularios_definitions = _load_formularios_definitions()

    if not paises_definitions and not status_processo_definitions and not formularios_definitions:
        return

    with transaction.atomic():
        tipos_visto_por_nome = {}
        if paises_definitions:
            paises_por_nome = _ensure_paises_destino(PaisDestino, User, paises_definitions)
            if tipos_visto_definitions:
                tipos_visto_por_nome = _ensure_tipos_visto(
                    TipoVisto, User, paises_por_nome, tipos_visto_definitions
                )
        
        # Se tipos_visto_por_nome estiver vazio mas precisamos criar formulários,
        # buscar tipos de visto existentes no banco
        if formularios_definitions and not tipos_visto_por_nome:
            tipos_visto_existentes = TipoVisto.objects.all()
            tipos_visto_por_nome = {tipo.nome: tipo for tipo in tipos_visto_existentes}
        
        if partners_definitions:
            _ensure_partners(Partner, User, partners_definitions)
        if status_processo_definitions:
            _ensure_status_processo(StatusProcesso, TipoVisto, tipos_visto_por_nome, status_processo_definitions)
        if formularios_definitions:
            _ensure_formularios(FormularioVisto, PerguntaFormulario, OpcaoSelecao, TipoVisto, tipos_visto_por_nome, formularios_definitions)


def _criar_registros_financeiros_para_viagem(viagem):
    """Cria registros financeiros para uma viagem."""
    Financeiro = django_apps.get_model("consultancy", "Financeiro")
    
    if viagem.valor_assessoria <= 0:
        return
    
    # Verificar se já existem registros para esta viagem
    registros_existentes = Financeiro.objects.filter(viagem=viagem)
    clientes_com_registro = set(registros_existentes.exclude(cliente=None).values_list("cliente_id", flat=True))
    
    # Criar um registro para cada cliente vinculado à viagem que ainda não tem registro
    clientes = viagem.clientes.all()
    
    if clientes.exists():
        # Se houver clientes, criar um registro para cada um que ainda não tem
        for cliente in clientes:
            if cliente.pk not in clientes_com_registro:
                Financeiro.objects.create(
                    viagem=viagem,
                    cliente=cliente,
                    assessor_responsavel=viagem.assessor_responsavel,
                    valor=viagem.valor_assessoria,
                    status="pendente",
                    criado_por=viagem.criado_por,
                )
    elif not registros_existentes.filter(cliente=None).exists():
        # Se não houver clientes e não existir registro sem cliente, criar um
        Financeiro.objects.create(
            viagem=viagem,
            cliente=None,
            assessor_responsavel=viagem.assessor_responsavel,
            valor=viagem.valor_assessoria,
            status="pendente",
            criado_por=viagem.criado_por,
        )


def _registrar_signals_financeiro():
    """Registra os signals para criação automática de registros financeiros."""
    Viagem = django_apps.get_model("consultancy", "Viagem")
    
    @receiver(post_save, sender=Viagem)
    def criar_registro_financeiro(sender, instance, created, **kwargs):
        """Cria automaticamente um registro financeiro quando uma viagem é criada."""
        if created:
            _criar_registros_financeiros_para_viagem(instance)
    
    @receiver(m2m_changed, sender=Viagem.clientes.through)
    def criar_registro_financeiro_ao_adicionar_cliente(sender, instance, action, pk_set, **kwargs):
        """Cria registros financeiros quando clientes são adicionados à viagem."""
        if action == "post_add" and instance.pk:
            _criar_registros_financeiros_para_viagem(instance)


class ConsultancyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "consultancy"

    def ready(self):
        if getattr(self, "_preload_registered", False):
            return

        post_migrate.connect(ensure_initial_consultancy_data, sender=self)
        # Registrar signals para criação automática de registros financeiros
        _registrar_signals_financeiro()
        self._preload_registered = True
