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
    "acompanhantes",
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


def _contains_term(text, term):
    words = text.split()
    term_words = term.split()
    if not term_words or len(term_words) > len(words):
        return False
    if len(term_words) == 1:
        return term_words[0] in words
    span = len(term_words)
    return any(words[idx: idx + span] == term_words for idx in range(len(words) - span + 1))


def _contains_any(text, tokens):
    return any(_contains_term(text, token) for token in tokens)


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
    if _contains_any(q, RELATION_CONTEXT_TOKENS):
        return False
    exact_passport_fields = {
        "orgao emissor",
        "autoridade",
        "local de emissao autoridade emissora",
        "local de emissao",
        "cidade de emissao",
    }
    if q in exact_passport_fields:
        return True
    if "passaporte" not in q:
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
        "telefone primario",
        "telefone principal",
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
    if _is_address_question(q):
        return True
    if _is_passport_question(q):
        return True
    return False
