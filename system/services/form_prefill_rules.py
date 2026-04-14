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

NON_APPLICANT_CONTEXT_TOKENS = RELATION_CONTEXT_TOKENS | {
    "acompanhante",
    "acompanhantes",
    "alternativo",
    "empresa",
    "empregador",
    "emergencial",
    "escola",
    "instituicao",
    "instituicoes",
    "mae",
    "organizacao",
    "pai",
    "patrocinador",
    "patrocinada",
    "patrocinado",
    "pessoa s",
}

BLOCKED_PREFILL_TOKENS = {
    "cep",
    "endereco",
    "bairro",
    "complemento",
    "logradouro",
    "passaporte",
    "rua",
}

DIRECT_CLIENT_PREFILL_FIELDS = {
    "nome": "first_name",
    "primeiro nome": "first_name",
    "sobrenome": "last_name",
    "cpf": "cpf",
    "email": "email",
    "e mail": "email",
    "telefone": "phone",
    "telefone celular": "phone",
    "telefone primario": "phone",
    "telefone principal": "phone",
    "telefone residencial": "phone",
    "telefone secundario": "secondary_phone",
    "data de nascimento": "birth_date",
    "data de nascimento dia mes ano": "birth_date",
    "nacionalidade": "nationality",
    "qual a sua nacionalidade": "nationality",
    "pais de nacionalidade": "nationality",
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


def get_client_prefill_field(question_text):
    q = normalize_text(question_text)
    if not q:
        return None
    if q[0].isdigit():
        return None
    if _contains_any(q, NON_APPLICANT_CONTEXT_TOKENS):
        return None
    if _contains_any(q, FOREIGN_ADDRESS_TOKENS):
        return None
    if _contains_any(q, BLOCKED_PREFILL_TOKENS):
        return None
    if "outra data de nascimento" in q:
        return None
    if "outros enderecos de e mail" in q:
        return None
    return DIRECT_CLIENT_PREFILL_FIELDS.get(q)


def should_prefill_from_client(question_text):
    return get_client_prefill_field(question_text) is not None
