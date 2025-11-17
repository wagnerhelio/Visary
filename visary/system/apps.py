import json
import os
from typing import Dict, Iterable, List, Tuple

from django.apps import AppConfig, apps as django_apps
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Model
from django.db.models.signals import post_migrate

def _get_models() -> Tuple[Model, Model, Model]:
    Modulo = django_apps.get_model("system", "Modulo")
    Perfil = django_apps.get_model("system", "Perfil")
    UsuarioConsultoria = django_apps.get_model("system", "UsuarioConsultoria")
    return Modulo, Perfil, UsuarioConsultoria


def _atualizar_campos(instancia: Model, valores: Dict) -> None:
    campos_em_mudanca = [campo for campo, valor in valores.items() if getattr(instancia, campo) != valor]
    if not campos_em_mudanca:
        return
    for campo in campos_em_mudanca:
        setattr(instancia, campo, valores[campo])
    instancia.save(update_fields=campos_em_mudanca)


def _ensure_modulos(Modulo: Model, module_definitions: List[Dict]) -> Dict[str, Model]:
    modulos_por_nome: Dict[str, Model] = {}
    for definicao in module_definitions:
        defaults = {
            "descricao": definicao.get("descricao", ""),
            "ordem": definicao["ordem"],
        }
        modulo, _ = Modulo.objects.get_or_create(nome=definicao["nome"], defaults=defaults)
        _atualizar_campos(
            modulo,
            {
                "descricao": defaults["descricao"],
                "ordem": defaults["ordem"],
                "ativo": definicao.get("ativo", True),
            },
        )
        modulos_por_nome[modulo.nome] = modulo
    return modulos_por_nome


def _ensure_perfis(
    Perfil: Model,
    modulos_por_nome: Dict[str, Model],
    profile_permissions: Dict[str, Dict],
    module_definitions: List[Dict],
) -> Dict[str, Model]:
    perfis_por_nome: Dict[str, Model] = {}
    for nome_perfil, configuracao in profile_permissions.items():
        perfil, _ = Perfil.objects.get_or_create(nome=nome_perfil, defaults=configuracao)
        _atualizar_campos(perfil, configuracao)
        modulos_relacionados = _modulos_por_perfil(nome_perfil, modulos_por_nome, module_definitions)
        perfil.modulos.set(modulos_relacionados)
        perfis_por_nome[nome_perfil] = perfil
    return perfis_por_nome


def _modulos_por_perfil(
    nome_perfil: str, modulos_por_nome: Dict[str, Model], module_definitions: List[Dict]
) -> Iterable[Model]:
    modulos_relacionados = (
        modulos_por_nome[modulo_def["nome"]]
        for modulo_def in module_definitions
        if nome_perfil in modulo_def["perfis"]
    )
    return list(modulos_relacionados)


def _ensure_usuarios(
    UsuarioConsultoria: Model, perfis_por_nome: Dict[str, Model], user_definitions: List[Dict]
) -> None:
    for definicao in user_definitions:
        perfil_destino = perfis_por_nome[definicao["perfil"]]
        defaults = {
            "nome": definicao["nome"],
            "senha": make_password(definicao["senha"]),
            "perfil": perfil_destino,
            "ativo": True,
        }
        usuario, created = UsuarioConsultoria.objects.get_or_create(
            email=definicao["email"].lower(),
            defaults=defaults,
        )
        if created:
            continue
        _atualizar_campos(
            usuario,
            {"nome": definicao["nome"], "perfil": perfil_destino, "ativo": True},
        )


def _load_user_definitions() -> List[Dict]:
    if not (raw := os.environ.get("SYSTEM_SEED_USERS")):
        raise ImproperlyConfigured(
            "Defina SYSTEM_SEED_USERS no ambiente com a lista de usuários padrão em JSON."
        )

    try:
        user_definitions = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(
            "SYSTEM_SEED_USERS deve conter um JSON válido."
        ) from exc

    if not isinstance(user_definitions, list):
        raise ImproperlyConfigured("SYSTEM_SEED_USERS deve ser uma lista de objetos.")

    campos_obrigatorios = {"nome", "email", "senha", "perfil"}
    for posicao, definicao in enumerate(user_definitions, start=1):
        if not isinstance(definicao, dict):
            raise ImproperlyConfigured(
                f"SYSTEM_SEED_USERS posição {posicao} deve ser um objeto JSON."
            )
        if campos_ausentes := campos_obrigatorios - definicao.keys():
            raise ImproperlyConfigured(
                f"SYSTEM_SEED_USERS posição {posicao} sem campos: {', '.join(sorted(campos_ausentes))}."
            )
    return user_definitions


def _load_module_definitions() -> List[Dict]:
    if not (raw := os.environ.get("SYSTEM_SEED_MODULES")):
        raise ImproperlyConfigured(
            "Defina SYSTEM_SEED_MODULES no ambiente com a lista de módulos padrão em JSON."
        )

    try:
        module_definitions = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured("SYSTEM_SEED_MODULES deve conter um JSON válido.") from exc

    if not isinstance(module_definitions, list):
        raise ImproperlyConfigured("SYSTEM_SEED_MODULES deve ser uma lista de objetos.")

    campos_obrigatorios = {"nome", "ordem", "perfis"}
    for posicao, definicao in enumerate(module_definitions, start=1):
        if not isinstance(definicao, dict):
            raise ImproperlyConfigured(
                f"SYSTEM_SEED_MODULES posição {posicao} deve ser um objeto JSON."
            )
        if campos_ausentes := campos_obrigatorios - definicao.keys():
            raise ImproperlyConfigured(
                f"SYSTEM_SEED_MODULES posição {posicao} sem campos: {', '.join(sorted(campos_ausentes))}."
            )
        if not isinstance(definicao["perfis"], list) or not definicao["perfis"]:
            raise ImproperlyConfigured(
                f"SYSTEM_SEED_MODULES posição {posicao} deve conter 'perfis' como lista não vazia."
            )
    return module_definitions


def _load_profile_permissions() -> Dict[str, Dict]:
    if not (raw := os.environ.get("SYSTEM_SEED_PROFILES")):
        raise ImproperlyConfigured(
            "Defina SYSTEM_SEED_PROFILES no ambiente com a lista de perfis padrão em JSON."
        )

    try:
        profile_list = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured("SYSTEM_SEED_PROFILES deve conter um JSON válido.") from exc

    if not isinstance(profile_list, list):
        raise ImproperlyConfigured("SYSTEM_SEED_PROFILES deve ser uma lista de objetos.")

    profile_permissions: Dict[str, Dict] = {}
    for posicao, definicao in enumerate(profile_list, start=1):
        if not isinstance(definicao, dict):
            raise ImproperlyConfigured(
                f"SYSTEM_SEED_PROFILES posição {posicao} deve ser um objeto JSON."
            )
        if not (nome := definicao.get("nome")):
            raise ImproperlyConfigured(
                f"SYSTEM_SEED_PROFILES posição {posicao} precisa do campo 'nome'."
            )
        profile_permissions[nome] = {
            "descricao": definicao.get("descricao", ""),
            "pode_criar": definicao.get("pode_criar", False),
            "pode_visualizar": definicao.get("pode_visualizar", True),
            "pode_atualizar": definicao.get("pode_atualizar", False),
            "pode_excluir": definicao.get("pode_excluir", False),
            "ativo": definicao.get("ativo", True),
        }
    return profile_permissions


def ensure_initial_system_data(sender, **kwargs):
    if sender.name != "system":
        return

    Modulo, Perfil, UsuarioConsultoria = _get_models()
    module_definitions = _load_module_definitions()
    profile_permissions = _load_profile_permissions()
    user_definitions = _load_user_definitions()

    if not module_definitions or not profile_permissions:
        return

    with transaction.atomic():
        modulos_por_nome = _ensure_modulos(Modulo, module_definitions)
        perfis_por_nome = _ensure_perfis(
            Perfil,
            modulos_por_nome,
            profile_permissions,
            module_definitions,
        )
        if user_definitions:
            _ensure_usuarios(UsuarioConsultoria, perfis_por_nome, user_definitions)


class SystemConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "system"

    def ready(self):
        if getattr(self, "_preload_registered", False):
            return

        post_migrate.connect(ensure_initial_system_data, sender=self)
        self._preload_registered = True
