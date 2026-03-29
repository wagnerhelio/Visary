"""
Serviço consolidado para manipulação de respostas de formulários dinâmicos.

Centraliza validação, persistência transacional e lógica de visibilidade
condicional que antes estava duplicada entre travel_views e client_area_views.
"""

import logging
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_date

from system.models import OpcaoSelecao, RespostaFormulario

logger = logging.getLogger("visary.forms")


# ---------------------------------------------------------------------------
# Helpers de campo
# ---------------------------------------------------------------------------

def limpar_campos_resposta(resposta):
    """Zera todos os campos tipados de uma RespostaFormulario."""
    resposta.resposta_texto = ""
    resposta.resposta_data = None
    resposta.resposta_numero = None
    resposta.resposta_booleano = None
    resposta.resposta_selecao = None


def atualizar_resposta_por_tipo(resposta, pergunta, valor):
    """Atualiza a resposta conforme o tipo_campo da pergunta.

    Levanta ``ValueError`` se o valor for inválido para o tipo esperado.
    """
    limpar_campos_resposta(resposta)

    tipo = pergunta.tipo_campo

    if tipo == "texto":
        resposta.resposta_texto = valor or ""

    elif tipo == "data":
        if valor:
            parsed = parse_date(valor)
            if parsed is None:
                raise ValueError(
                    f"Data inválida para a pergunta '{pergunta.pergunta}'. "
                    "Use o formato AAAA-MM-DD."
                )
            resposta.resposta_data = parsed
        else:
            resposta.resposta_data = None

    elif tipo == "numero":
        if valor:
            try:
                resposta.resposta_numero = Decimal(valor)
            except (InvalidOperation, ValueError) as e:
                raise ValueError(
                    f"Valor numérico inválido para a pergunta '{pergunta.pergunta}'."
                ) from e
        else:
            resposta.resposta_numero = None

    elif tipo == "booleano":
        resposta.resposta_booleano = (valor == "sim") if valor else None

    elif tipo == "selecao":
        if valor:
            try:
                opcao_id = int(valor)
                resposta.resposta_selecao = OpcaoSelecao.objects.get(
                    pk=opcao_id, pergunta=pergunta
                )
            except (ValueError, OpcaoSelecao.DoesNotExist) as e:
                raise ValueError(
                    f"Opção inválida para a pergunta '{pergunta.pergunta}'."
                ) from e


# ---------------------------------------------------------------------------
# Visibilidade condicional
# ---------------------------------------------------------------------------

def build_pergunta_estado(perguntas, post_dict, respostas_existentes):
    """Constrói mapa de estado (ordem → valor exibido) para avaliação de regras."""
    estado = {}
    for p in perguntas:
        if p.tipo_campo == "booleano":
            val = post_dict.get(f"pergunta_{p.pk}", "")
            if val == "sim":
                estado[p.ordem] = "sim"
            elif val == "nao":
                estado[p.ordem] = "nao"
            elif p.pk in respostas_existentes:
                r = respostas_existentes[p.pk]
                if r.resposta_booleano is True:
                    estado[p.ordem] = "sim"
                elif r.resposta_booleano is False:
                    estado[p.ordem] = "nao"
        elif p.tipo_campo == "selecao":
            val = post_dict.get(f"pergunta_{p.pk}", "")
            if val:
                try:
                    opcao_id = int(val)
                    opcao = OpcaoSelecao.objects.filter(pk=opcao_id, pergunta=p).first()
                    estado[p.ordem] = opcao.texto if opcao else val
                except ValueError:
                    estado[p.ordem] = val
            elif p.pk in respostas_existentes:
                r = respostas_existentes[p.pk]
                if r.resposta_selecao_id:
                    estado[p.ordem] = r.resposta_selecao.texto
        elif p.tipo_campo == "numero":
            estado[p.ordem] = post_dict.get(f"pergunta_{p.pk}", "")
        elif p.tipo_campo == "data":
            estado[p.ordem] = post_dict.get(f"pergunta_{p.pk}", "")
        else:
            val = post_dict.get(f"pergunta_{p.pk}", "")
            if not val and p.pk in respostas_existentes:
                val = respostas_existentes[p.pk].resposta_texto or ""
            estado[p.ordem] = val
    return estado


def pergunta_e_visivel(pergunta, estado):
    """Avalia regra_exibicao para determinar se a pergunta deve ser mostrada."""
    regra = pergunta.regra_exibicao
    if not regra:
        return True
    tipo = regra.get("tipo")
    if tipo != "mostrar_se":
        return True
    pergunta_ordem = regra.get("pergunta_ordem")
    valores_esperados = regra.get("valor")
    if pergunta_ordem is None or valores_esperados is None:
        return True
    if isinstance(valores_esperados, list):
        return estado.get(pergunta_ordem) in valores_esperados
    return estado.get(pergunta_ordem) == valores_esperados


# ---------------------------------------------------------------------------
# Persistência transacional
# ---------------------------------------------------------------------------

def processar_respostas_formulario(post_dict, viagem, cliente, perguntas, respostas_existentes=None):
    """Valida e persiste respostas de formulário dentro de uma transação.

    Usa savepoints individuais por pergunta para isolar erros de validação
    sem reverter respostas já salvas com sucesso.

    Retorna ``(respostas_salvas, erros)`` onde *erros* é lista de strings.
    """
    respostas_salvas = 0
    erros = []
    respostas_existentes = respostas_existentes or {}
    estado = build_pergunta_estado(perguntas, post_dict, respostas_existentes)

    with transaction.atomic():
        for pergunta in perguntas:
            campo_name = f"pergunta_{pergunta.pk}"
            valor = post_dict.get(campo_name)

            if pergunta.obrigatorio and not valor and pergunta_e_visivel(pergunta, estado):
                erros.append(f"A pergunta '{pergunta.pergunta}' é obrigatória.")
                continue

            sid = transaction.savepoint()
            try:
                resposta, _ = RespostaFormulario.objects.get_or_create(
                    viagem=viagem,
                    cliente=cliente,
                    pergunta=pergunta,
                    defaults={},
                )
                atualizar_resposta_por_tipo(resposta, pergunta, valor)
                resposta.save()
                respostas_salvas += 1
                transaction.savepoint_commit(sid)
            except IntegrityError:
                transaction.savepoint_rollback(sid)
                sid2 = transaction.savepoint()
                try:
                    resposta = RespostaFormulario.objects.get(
                        viagem=viagem, cliente=cliente, pergunta=pergunta
                    )
                    atualizar_resposta_por_tipo(resposta, pergunta, valor)
                    resposta.save()
                    respostas_salvas += 1
                    transaction.savepoint_commit(sid2)
                except Exception as e:
                    transaction.savepoint_rollback(sid2)
                    logger.exception(
                        "Erro ao salvar resposta (pergunta pk=%s, viagem pk=%s, cliente pk=%s)",
                        pergunta.pk, viagem.pk, cliente.pk,
                    )
                    erros.append(str(e))
            except ValueError as e:
                transaction.savepoint_rollback(sid)
                erros.append(str(e))

    return respostas_salvas, erros
