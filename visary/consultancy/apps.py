import json
import logging
import os
from contextlib import suppress
from pathlib import Path

from django.apps import AppConfig, apps as django_apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import models, transaction
from django.db.models.signals import m2m_changed, post_migrate, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _get_models():
    PaisDestino = django_apps.get_model("consultancy", "PaisDestino")
    TipoVisto = django_apps.get_model("consultancy", "TipoVisto")
    Partner = django_apps.get_model("consultancy", "Partner")
    StatusProcesso = django_apps.get_model("consultancy", "StatusProcesso")
    FormularioVisto = django_apps.get_model("consultancy", "FormularioVisto")
    PerguntaFormulario = django_apps.get_model("consultancy", "PerguntaFormulario")
    OpcaoSelecao = django_apps.get_model("consultancy", "OpcaoSelecao")
    EtapaCadastroCliente = django_apps.get_model("consultancy", "EtapaCadastroCliente")
    CampoEtapaCliente = django_apps.get_model("consultancy", "CampoEtapaCliente")
    User = get_user_model()
    return PaisDestino, TipoVisto, Partner, StatusProcesso, FormularioVisto, PerguntaFormulario, OpcaoSelecao, EtapaCadastroCliente, CampoEtapaCliente, User


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


def _carregar_etapas_do_env() -> list:
    """Carrega etapas de cadastro de cliente da variável de ambiente."""
    etapas = []
    if raw := os.environ.get("CONSULTANCY_SEED_ETAPAS_CLIENTE"):
        with suppress(json.JSONDecodeError):
            if etapas_env := json.loads(raw):
                if isinstance(etapas_env, list):
                    etapas.extend(etapas_env)
    return etapas


def _carregar_etapas_de_arquivos() -> list:
    """Carrega etapas de cadastro de cliente de arquivos JSON."""
    etapas = []
    base_dir = Path(settings.BASE_DIR)
    etapas_ini_dir = base_dir / "static" / "etapas_cliente_ini"
    
    if not etapas_ini_dir.is_dir():
        return etapas
    
    for arquivo_json in etapas_ini_dir.glob("*.json"):
        try:
            with open(arquivo_json, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if isinstance(dados, list):
                    etapas.extend(dados)
                elif isinstance(dados, dict) and "nome" in dados:
                    etapas.append(dados)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Erro ao carregar arquivo {arquivo_json}: {e}")
    
    return etapas


def _validar_campo_etapa(campo: dict, posicao_etapa: int, idx_campo: int):
    """Valida um campo individual de uma etapa."""
    if not isinstance(campo, dict):
        raise ImproperlyConfigured(
            f"Etapa posição {posicao_etapa}, campo {idx_campo} deve ser um objeto JSON."
        )
    campos_obrigatorios = {"nome_campo", "ordem"}
    if campos_ausentes := campos_obrigatorios - campo.keys():
        raise ImproperlyConfigured(
            f"Etapa posição {posicao_etapa}, campo {idx_campo} sem campos: {', '.join(sorted(campos_ausentes))}."
        )


def _validar_etapas(etapas: list):
    """Valida todas as etapas e seus campos."""
    campos_obrigatorios = {"nome", "ordem"}
    for posicao, definicao in enumerate(etapas, start=1):
        if not isinstance(definicao, dict):
            raise ImproperlyConfigured(
                f"Etapa posição {posicao} deve ser um objeto JSON."
            )
        if campos_ausentes := campos_obrigatorios - definicao.keys():
            raise ImproperlyConfigured(
                f"Etapa posição {posicao} sem campos: {', '.join(sorted(campos_ausentes))}."
            )
        if "campos" in definicao:
            if not isinstance(definicao["campos"], list):
                raise ImproperlyConfigured(
                    f"Etapa posição {posicao}: 'campos' deve ser uma lista."
                )
            for idx, campo in enumerate(definicao["campos"], start=1):
                _validar_campo_etapa(campo, posicao, idx)


def _load_etapas_cliente_definitions():
    """Carrega etapas de cadastro de cliente a partir de variável de ambiente ou arquivos JSON em etapas_cliente_ini."""
    etapas = []
    etapas.extend(_carregar_etapas_do_env())
    
    try:
        etapas.extend(_carregar_etapas_de_arquivos())
    except Exception as e:
        logger.warning(f"Erro ao acessar diretório etapas_cliente_ini: {e}")
    
    _validar_etapas(etapas)
    return etapas


def _ensure_etapas_cliente(EtapaCadastroCliente, CampoEtapaCliente, User, etapas_definitions):
    """Garante que as etapas de cadastro de cliente e seus campos estejam cadastrados."""
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
    
    for definicao in etapas_definitions:
        defaults = {
            "nome": definicao["nome"],
            "descricao": definicao.get("descricao", ""),
            "ordem": definicao["ordem"],
            "ativo": definicao.get("ativo", True),
            "campo_booleano": definicao.get("campo_booleano", ""),
        }
        etapa, created = EtapaCadastroCliente.objects.get_or_create(
            nome=definicao["nome"],
            defaults=defaults
        )
        if not created:
            _atualizar_campos(
                etapa,
                {
                    "descricao": definicao.get("descricao", ""),
                    "ordem": definicao["ordem"],
                    "ativo": definicao.get("ativo", True),
                    "campo_booleano": definicao.get("campo_booleano", ""),
                },
            )
        
        # Criar ou atualizar campos da etapa
        for campo_def in definicao.get("campos", []):
            defaults_campo = {
                "etapa": etapa,
                "nome_campo": campo_def["nome_campo"],
                "tipo_campo": campo_def.get("tipo_campo", "texto"),
                "ordem": campo_def["ordem"],
                "obrigatorio": campo_def.get("obrigatorio", False),
                "ativo": campo_def.get("ativo", True),
            }
            campo, created_campo = CampoEtapaCliente.objects.get_or_create(
                etapa=etapa,
                nome_campo=campo_def["nome_campo"],
                defaults=defaults_campo
            )
            if not created_campo:
                _atualizar_campos(
                    campo,
                    {
                        "tipo_campo": campo_def.get("tipo_campo", "texto"),
                        "ordem": campo_def["ordem"],
                        "obrigatorio": campo_def.get("obrigatorio", False),
                        "ativo": campo_def.get("ativo", True),
                    },
                )


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
        PaisDestino, TipoVisto, Partner, StatusProcesso, FormularioVisto, PerguntaFormulario, OpcaoSelecao, EtapaCadastroCliente, CampoEtapaCliente, User = _get_models()
    except LookupError:
        # Modelos ainda não foram criados
        return

    paises_definitions = _load_paises_definitions()
    tipos_visto_definitions = _load_tipos_visto_definitions()
    partners_definitions = _load_partners_definitions()
    status_processo_definitions = _load_status_processo_definitions()
    formularios_definitions = _load_formularios_definitions()
    etapas_cliente_definitions = _load_etapas_cliente_definitions()

    if not paises_definitions and not status_processo_definitions and not formularios_definitions and not etapas_cliente_definitions and not partners_definitions:
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
        if etapas_cliente_definitions:
            _ensure_etapas_cliente(EtapaCadastroCliente, CampoEtapaCliente, User, etapas_cliente_definitions)


def _criar_registros_financeiros_para_viagem(viagem):
    """Cria registros financeiros para uma viagem."""
    Financeiro = django_apps.get_model("consultancy", "Financeiro")
    
    if viagem.valor_assessoria <= 0:
        return
    
    # Verificar se já existem registros para esta viagem
    registros_existentes = Financeiro.objects.filter(viagem=viagem)
    clientes_com_registro = set(registros_existentes.exclude(cliente=None).values_list("cliente_id", flat=True))
    
    # IMPORTANTE: Usar select_related para garantir que cliente_principal está carregado
    # Isso permite que is_principal funcione corretamente
    clientes = viagem.clientes.select_related('cliente_principal').all()
    
    if clientes.exists():
        # Se houver clientes, REMOVER qualquer registro sem cliente que possa ter sido criado anteriormente
        registros_existentes.filter(cliente=None).delete()
        
        # Separar clientes principais e dependentes
        cliente_principal = None
        dependentes = []
        
        for cliente in clientes:
            if cliente.is_principal:
                cliente_principal = cliente
            else:
                dependentes.append(cliente)
        
        # Se houver cliente principal na viagem, criar registro apenas para ele
        # (dependentes não devem ter registro financeiro separado)
        if cliente_principal:
            if cliente_principal.pk not in clientes_com_registro:
                Financeiro.objects.create(
                    viagem=viagem,
                    cliente=cliente_principal,
                    assessor_responsavel=viagem.assessor_responsavel,
                    valor=viagem.valor_assessoria,
                    status="pendente",
                    criado_por=viagem.criado_por,
                )
        elif dependentes:
            # Se não houver cliente principal mas houver dependentes, 
            # criar registro para o cliente principal do primeiro dependente
            primeiro_dependente = dependentes[0]
            if primeiro_dependente.cliente_principal:
                cliente_principal_do_grupo = primeiro_dependente.cliente_principal
                if cliente_principal_do_grupo.pk not in clientes_com_registro:
                    Financeiro.objects.create(
                        viagem=viagem,
                        cliente=cliente_principal_do_grupo,
                        assessor_responsavel=viagem.assessor_responsavel,
                        valor=viagem.valor_assessoria,
                        status="pendente",
                        criado_por=viagem.criado_por,
                    )
            elif primeiro_dependente.pk not in clientes_com_registro:
                # Se o dependente não tem cliente_principal, criar registro para o primeiro dependente
                # (caso onde dependentes estão órfãos ou mal configurados)
                Financeiro.objects.create(
                    viagem=viagem,
                    cliente=primeiro_dependente,
                    assessor_responsavel=viagem.assessor_responsavel,
                    valor=viagem.valor_assessoria,
                    status="pendente",
                    criado_por=viagem.criado_por,
                )
        else:
            # Se não houver cliente principal nem dependentes (caso raro), criar para o primeiro cliente
            primeiro_cliente = clientes.first()
            if primeiro_cliente and primeiro_cliente.pk not in clientes_com_registro:
                Financeiro.objects.create(
                    viagem=viagem,
                    cliente=primeiro_cliente,
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
        # Só criar registros se já houver clientes vinculados
        # Caso contrário, o signal m2m_changed cuidará disso quando os clientes forem adicionados
        if created and instance.clientes.exists():
            _criar_registros_financeiros_para_viagem(instance)
    
    @receiver(m2m_changed, sender=Viagem.clientes.through)
    def criar_registro_financeiro_ao_adicionar_cliente(sender, instance, action, pk_set, **kwargs):
        """Cria registros financeiros quando clientes são adicionados à viagem."""
        if action == "post_add" and instance.pk:
            _criar_registros_financeiros_para_viagem(instance)


def _sincronizar_status_viagem(viagem):
    """Garante que a viagem possua os status compatíveis com o tipo de visto."""
    if not viagem:
        return

    ViagemStatusProcesso = django_apps.get_model(
        "consultancy", "ViagemStatusProcesso"
    )
    StatusProcesso = django_apps.get_model("consultancy", "StatusProcesso")

    filtro = models.Q(tipo_visto__isnull=True)
    if viagem.tipo_visto_id:
        filtro |= models.Q(tipo_visto=viagem.tipo_visto)

    status_ids = set(
        StatusProcesso.objects.filter(filtro, ativo=True).values_list("id", flat=True)
    )
    existentes = set(
        ViagemStatusProcesso.objects.filter(viagem=viagem).values_list(
            "status_id", flat=True
        )
    )

    novos = status_ids - existentes
    remover = existentes - status_ids

    for status_id in novos:
        ViagemStatusProcesso.objects.create(viagem=viagem, status_id=status_id)

    if remover:
        ViagemStatusProcesso.objects.filter(
            viagem=viagem, status_id__in=remover
        ).delete()


def _registrar_signals_status_viagem():
    """Registra os signals responsáveis por manter os status vinculados às viagens."""
    Viagem = django_apps.get_model("consultancy", "Viagem")
    StatusProcesso = django_apps.get_model("consultancy", "StatusProcesso")

    @receiver(post_save, sender=Viagem)
    def sincronizar_status_viagem_post_save(sender, instance, **kwargs):
        _sincronizar_status_viagem(instance)

    @receiver(post_save, sender=StatusProcesso)
    def sincronizar_status_viagem_status(sender, instance, **kwargs):
        viagens = Viagem.objects.all()
        if instance.tipo_visto_id:
            viagens = viagens.filter(tipo_visto=instance.tipo_visto)
        for viagem in viagens:
            _sincronizar_status_viagem(viagem)


class ConsultancyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "consultancy"

    def ready(self):
        if getattr(self, "_preload_registered", False):
            return

        post_migrate.connect(ensure_initial_consultancy_data, sender=self)
        # Registrar signals para criação automática de registros financeiros
        _registrar_signals_financeiro()
        _registrar_signals_status_viagem()
        self._preload_registered = True
