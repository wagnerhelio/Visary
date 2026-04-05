import re
import logging

logger = logging.getLogger(__name__)

try:
    import brazilcep
    from brazilcep import exceptions as cep_exceptions
except ImportError:
    brazilcep = None
    cep_exceptions = None

try:
    import requests
except ImportError:
    requests = None

try:
    from pycep_correios import get_address_from_cep as correios_get_address
    from pycep_correios import exceptions as correios_exceptions
except ImportError:
    correios_get_address = None
    correios_exceptions = None


def _normalize_zip(cep):
    digits = re.sub(r"\D", "", cep)
    if len(digits) != 8:
        raise ValueError("CEP deve conter 8 dígitos.")
    return digits


def _normalize_response(raw, cep):
    normalized_cep = _normalize_zip(cep)
    result = {
        "cep": normalized_cep,
        "street": "",
        "district": "",
        "city": "",
        "uf": "",
        "complement": "",
    }
    field_map = {
        "street": ["logradouro", "address", "rua", "endereco", "street", "publicPlace"],
        "district": ["bairro", "neighborhood", "district", "districtName"],
        "city": ["cidade", "city", "localidade", "localidadeNome"],
        "uf": ["uf", "state", "estado", "ufSigla"],
        "complement": ["complemento", "complement", "complementoNome"],
    }
    lower_raw = {k.lower(): v for k, v in raw.items() if v}
    for field, variants in field_map.items():
        for variant in variants:
            if variant.lower() in lower_raw:
                value = lower_raw[variant.lower()]
                if value and str(value).strip():
                    result[field] = str(value).strip()
                    break
    return result


def _fetch_viacep(cep):
    if requests is None:
        raise ValueError("Biblioteca requests não está instalada.")
    normalized = _normalize_zip(cep)
    url = f"https://viacep.com.br/ws/{normalized}/json/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if "erro" in data:
            raise ValueError("CEP não encontrado na ViaCEP.")
        return _normalize_response(data, normalized)
    except requests.exceptions.Timeout:
        logger.warning("Timeout ao consultar ViaCEP para CEP %s", normalized)
        raise ValueError("Timeout ao consultar ViaCEP.") from None
    except requests.exceptions.RequestException as e:
        logger.warning("Erro ao consultar ViaCEP: %s", e)
        raise ValueError("Erro ao consultar ViaCEP.") from e


def _fetch_brasilapi(cep):
    if requests is None:
        raise ValueError("Biblioteca requests não está instalada.")
    normalized = _normalize_zip(cep)
    url = f"https://brasilapi.com.br/api/cep/v1/{normalized}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return _normalize_response(response.json(), normalized)
    except requests.exceptions.Timeout:
        logger.warning("Timeout ao consultar BrasilAPI para CEP %s", normalized)
        raise ValueError("Timeout ao consultar BrasilAPI.") from None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            raise ValueError("CEP não encontrado na BrasilAPI.") from e
        logger.warning("Erro HTTP ao consultar BrasilAPI: %s", e)
        raise ValueError("Erro ao consultar BrasilAPI.") from e
    except requests.exceptions.RequestException as e:
        logger.warning("Erro ao consultar BrasilAPI: %s", e)
        raise ValueError("Erro ao consultar BrasilAPI.") from e


def _fetch_pycep(cep):
    if correios_get_address is None:
        raise ValueError("Biblioteca pycep-correios não está instalada.")
    try:
        address = correios_get_address(cep)
        return _normalize_response(address, cep)
    except Exception as e:
        if correios_exceptions and isinstance(e, (correios_exceptions.InvalidCEP, correios_exceptions.CEPNotFound)):
            raise ValueError("CEP não encontrado.") from e
        logger.warning("Erro ao consultar pycep-correios: %s", e)
        raise ValueError("Erro ao consultar pycep-correios.") from e


def _fetch_brazilcep(cep):
    if brazilcep is None:
        raise ValueError("Biblioteca brazilcep não está instalada.")
    try:
        address = brazilcep.get_address_from_cep(cep)
        return _normalize_response(address, cep)
    except cep_exceptions.InvalidCEP as e:
        raise ValueError("CEP inválido.") from e
    except cep_exceptions.CEPNotFound as e:
        raise ValueError("CEP não encontrado.") from e
    except cep_exceptions.BrazilCEPException as e:
        logger.warning("Erro ao consultar brazilcep: %s", e)
        raise ValueError("Erro ao consultar brazilcep.") from e


SOURCES = [
    ("ViaCEP", _fetch_viacep),
    ("BrasilAPI", _fetch_brasilapi),
    ("pycep-correios", _fetch_pycep),
    ("brazilcep", _fetch_brazilcep),
]


def fetch_address_by_zip(cep):
    if not cep or not cep.strip():
        raise ValueError("CEP não informado.")
    try:
        normalized = _normalize_zip(cep)
    except ValueError as e:
        raise ValueError(f"CEP inválido: {e}") from e

    last_error = None
    sources_tried = []
    errors_by_source = {}

    for source_name, fetch_fn in SOURCES:
        logger.warning("[CEP] Tentando buscar CEP %s via %s...", normalized, source_name)
        try:
            result = fetch_fn(normalized)
            if result and result.get("city"):
                logger.warning("[CEP] Sucesso! CEP %s encontrado via %s", normalized, source_name)
                return result
            last_error = ValueError("Resultado vazio ou sem cidade")
            sources_tried.append(source_name)
            errors_by_source[source_name] = "Resultado vazio ou sem cidade"
        except ValueError as e:
            last_error = e
            sources_tried.append(source_name)
            errors_by_source[source_name] = str(e)
            logger.warning("[CEP] Falha via %s: %s", source_name, e)
        except Exception as e:
            last_error = ValueError(f"Erro inesperado: {e}")
            sources_tried.append(source_name)
            errors_by_source[source_name] = f"Erro inesperado: {e}"
            logger.warning("[CEP] Erro inesperado via %s: %s: %s", source_name, type(e).__name__, e)

    if len(sources_tried) == len(SOURCES):
        details = "; ".join(f"{s}: {e}" for s, e in errors_by_source.items())
        raise ValueError(f"CEP {normalized} não encontrado em nenhuma fonte disponível. Detalhes: {details}")
    if last_error:
        raise last_error
    raise ValueError(f"CEP não encontrado. Fontes tentadas: {', '.join(sources_tried)}")
