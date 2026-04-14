import re
import unicodedata


RELATION_CONTEXT_TOKENS = {
    "conjuge",
    "esposa",
    "marido",
    "pai",
    "mae",
    "filho",
    "filhos",
    "parente",
    "acompanhante",
    "supervisor",
    "responsavel",
    "contato n 1",
    "contato n 2",
}

FOREIGN_ADDRESS_TOKENS = {
    "estados unidos",
    "eua",
    "australia",
    "canada",
    "exterior",
}


def normalize_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _contains_any(text, tokens):
    return any(token in text for token in tokens)


def _is_address_question(question_text):
    q = normalize_text(question_text)
    if not q or _contains_any(q, FOREIGN_ADDRESS_TOKENS):
        return False
    if "nascimento" in q:
        return False
    if any(token in q for token in {"cep", "logradouro", "bairro", "complemento"}):
        return True
    if "endereco" in q:
        return True
    if q in {"numero", "numero da casa"}:
        return True
    if "cidade e estado em que reside" in q:
        return True
    return False


def _is_passport_question(question_text):
    q = normalize_text(question_text)
    if "passaporte" not in q:
        return False
    if _contains_any(q, RELATION_CONTEXT_TOKENS):
        return False
    return any(
        token in q
        for token in {
            "numero",
            "pais que emitiu",
            "pais referente",
            "pais emissor",
            "data de emissao",
            "data de validade",
            "data de expiracao",
            "valido ate",
            "autoridade",
            "orgao emissor",
            "local de emissao",
            "cidade de emissao",
            "tipo de passaporte",
            "roubado",
        }
    )


def should_prefill_from_client(question_text):
    q = normalize_text(question_text)
    if not q:
        return False
    if _contains_any(q, RELATION_CONTEXT_TOKENS):
        return False
    if _contains_any(q, FOREIGN_ADDRESS_TOKENS):
        return False

    if q in {
        "nome",
        "primeiro nome",
        "sobrenome",
        "nome completo",
        "cpf",
        "email",
        "e mail",
        "telefone",
        "telefone secundario",
        "telefone celular",
        "telefone residencial",
        "data de nascimento",
        "data de nascimento dia mes ano",
        "qual a sua nacionalidade",
        "nacionalidade",
    }:
        return True

    if "data de nascimento" in q and "nascimento do" not in q and "nascimento de" not in q:
        return True
    if "nacionalidade" in q and "outra" not in q:
        return True
    if "telefone" in q and "ultimos cinco anos" not in q and "trabalho" not in q:
        return True
    if _is_address_question(q):
        return True
    if _is_passport_question(q):
        return True
    return False
