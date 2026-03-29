import re
import unicodedata
from decimal import Decimal, InvalidOperation

from system.models import OpcaoSelecao, RespostaFormulario


def normalize_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _prefill_raw_value(pergunta, cliente):
    q = normalize_text(pergunta.pergunta)
    values = [
        ("cpf", cliente.cpf),
        ("email", cliente.email),
        ("telefone secundario", cliente.telefone_secundario),
        ("telefone", cliente.telefone),
        ("cep", cliente.cep),
        ("logradouro", cliente.logradouro),
        ("endereco", cliente.logradouro),
        ("numero", cliente.numero),
        ("complemento", cliente.complemento),
        ("bairro", cliente.bairro),
        ("cidade emissao", cliente.cidade_emissao_passaporte),
        ("cidade", cliente.cidade),
        ("estado", cliente.uf),
        ("uf", cliente.uf),
        ("data de nascimento", cliente.data_nascimento),
        ("nacionalidade", cliente.nacionalidade),
        ("sobrenome", cliente.sobrenome),
        ("nome completo", cliente.nome_completo),
        ("nome", cliente.nome),
        ("tipo de passaporte", cliente.tipo_passaporte_outro or cliente.tipo_passaporte),
        ("numero do passaporte", cliente.numero_passaporte),
        ("pais emissor", cliente.pais_emissor_passaporte),
        ("data emissao", cliente.data_emissao_passaporte),
        ("data validade", cliente.valido_ate_passaporte),
        ("valido ate", cliente.valido_ate_passaporte),
        ("autoridade", cliente.autoridade_passaporte),
        ("orgao emissor", cliente.autoridade_passaporte),
    ]
    for key, value in values:
        if key in q and value not in (None, ""):
            return value
    if "passaporte roubado" in q:
        return "sim" if cliente.passaporte_roubado else "nao"
    return None


def _assign_prefill_value(resposta, pergunta, raw_value):
    resposta.resposta_texto = ""
    resposta.resposta_data = None
    resposta.resposta_numero = None
    resposta.resposta_booleano = None
    resposta.resposta_selecao = None

    if pergunta.tipo_campo == "texto":
        resposta.resposta_texto = str(raw_value)
        return True

    if pergunta.tipo_campo == "data":
        if hasattr(raw_value, "year"):
            resposta.resposta_data = raw_value
            return True
        return False

    if pergunta.tipo_campo == "numero":
        try:
            resposta.resposta_numero = Decimal(str(raw_value))
            return True
        except (InvalidOperation, ValueError):
            return False

    if pergunta.tipo_campo == "booleano":
        token = normalize_text(raw_value)
        if token in {"sim", "true", "1", "yes"}:
            resposta.resposta_booleano = True
            return True
        if token in {"nao", "false", "0", "no"}:
            resposta.resposta_booleano = False
            return True
        return False

    if pergunta.tipo_campo == "selecao":
        target = normalize_text(raw_value)
        for opcao in OpcaoSelecao.objects.filter(pergunta=pergunta, ativo=True).order_by("ordem"):
            if normalize_text(opcao.texto) == target:
                resposta.resposta_selecao = opcao
                return True
        return False

    return False


def prefill_form_answers(viagem, cliente, perguntas, respostas_existentes):
    updated = False
    for pergunta in perguntas:
        if pergunta.pk in respostas_existentes:
            continue
        raw_value = _prefill_raw_value(pergunta, cliente)
        if raw_value in (None, ""):
            continue
        resposta = RespostaFormulario(viagem=viagem, cliente=cliente, pergunta=pergunta)
        if not _assign_prefill_value(resposta, pergunta, raw_value):
            continue
        resposta.save()
        respostas_existentes[pergunta.pk] = resposta
        updated = True
    return updated, respostas_existentes
