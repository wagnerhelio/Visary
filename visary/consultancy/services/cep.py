"""
Serviço para busca de endereço por CEP com múltiplas fontes e fallback automático.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Tenta importar bibliotecas opcionais
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
    from pycep_correios import get_address_from_cep as correios_get_address  # type: ignore
    from pycep_correios import exceptions as correios_exceptions  # type: ignore
except ImportError:
    correios_get_address = None
    correios_exceptions = None


def _normalizar_cep(cep: str) -> str:
    """
    Remove caracteres não numéricos do CEP.
    
    Args:
        cep: CEP em qualquer formato
        
    Returns:
        CEP apenas com números (8 dígitos)
    """
    cep_limpo = re.sub(r'\D', '', cep)
    if len(cep_limpo) != 8:
        raise ValueError("CEP deve conter 8 dígitos.")
    return cep_limpo


def _normalizar_resposta(endereco: dict, cep: str) -> dict:
    """
    Normaliza a resposta de diferentes APIs para o formato padrão.
    
    Args:
        endereco: Dicionário com dados do endereço (formato variável)
        cep: CEP original (para garantir que está no retorno)
        
    Returns:
        dict normalizado no formato esperado
    """
    # Normaliza o CEP
    cep_normalizado = _normalizar_cep(cep)
    
    # Mapeia campos comuns de diferentes APIs
    resultado = {
        'cep': cep_normalizado,
        'street': '',
        'district': '',
        'city': '',
        'uf': '',
        'complement': ''
    }
    
    # Mapeamento de campos possíveis
    mapeamento = {
        'street': ['logradouro', 'address', 'rua', 'endereco', 'street', 'publicPlace'],
        'district': ['bairro', 'neighborhood', 'district', 'districtName'],
        'city': ['cidade', 'city', 'localidade', 'localidadeNome'],
        'uf': ['uf', 'state', 'estado', 'ufSigla'],
        'complement': ['complemento', 'complement', 'complementoNome']
    }
    
    # Converte chaves para minúsculas para comparação case-insensitive
    endereco_lower = {k.lower(): v for k, v in endereco.items() if v}
    
    for campo_padrao, variantes in mapeamento.items():
        for variante in variantes:
            if variante.lower() in endereco_lower:
                valor = endereco_lower[variante.lower()]
                if valor and str(valor).strip():
                    resultado[campo_padrao] = str(valor).strip()
                    break
    
    return resultado


def _buscar_via_cep(cep: str) -> dict:
    """
    Busca CEP usando a API ViaCEP (https://viacep.com.br/).
    
    Args:
        cep: CEP no formato 00000000
        
    Returns:
        dict com informações do endereço
        
    Raises:
        ValueError: Se houver erro na consulta
    """
    if requests is None:
        raise ValueError("Biblioteca requests não está instalada.")
    
    cep_normalizado = _normalizar_cep(cep)
    url = f"https://viacep.com.br/ws/{cep_normalizado}/json/"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if 'erro' in data:
            raise ValueError("CEP não encontrado na ViaCEP.")
        
        return _normalizar_resposta(data, cep_normalizado)
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout ao consultar ViaCEP para CEP {cep_normalizado}")
        raise ValueError("Timeout ao consultar ViaCEP.") from None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Erro ao consultar ViaCEP: {e}")
        raise ValueError("Erro ao consultar ViaCEP.") from e


def _buscar_brasil_api(cep: str) -> dict:
    """
    Busca CEP usando a API BrasilAPI (https://brasilapi.com.br/).
    
    Args:
        cep: CEP no formato 00000000
        
    Returns:
        dict com informações do endereço
        
    Raises:
        ValueError: Se houver erro na consulta
    """
    if requests is None:
        raise ValueError("Biblioteca requests não está instalada.")
    
    cep_normalizado = _normalizar_cep(cep)
    url = f"https://brasilapi.com.br/api/cep/v1/{cep_normalizado}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        return _normalizar_resposta(data, cep_normalizado)
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout ao consultar BrasilAPI para CEP {cep_normalizado}")
        raise ValueError("Timeout ao consultar BrasilAPI.") from None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            raise ValueError("CEP não encontrado na BrasilAPI.") from e
        logger.warning(f"Erro HTTP ao consultar BrasilAPI: {e}")
        raise ValueError("Erro ao consultar BrasilAPI.") from e
    except requests.exceptions.RequestException as e:
        logger.warning(f"Erro ao consultar BrasilAPI: {e}")
        raise ValueError("Erro ao consultar BrasilAPI.") from e


def _buscar_pycep_correios(cep: str) -> dict:
    """
    Busca CEP usando a biblioteca pycep-correios.
    
    Args:
        cep: CEP no formato 00000000 ou 00000-000
        
    Returns:
        dict com informações do endereço
        
    Raises:
        ValueError: Se houver erro na consulta
    """
    if correios_get_address is None:
        raise ValueError("Biblioteca pycep-correios não está instalada.")
    
    try:
        endereco = correios_get_address(cep)
        return _normalizar_resposta(endereco, cep)
    except Exception as e:
        if correios_exceptions and isinstance(e, (correios_exceptions.InvalidCEP, correios_exceptions.CEPNotFound)):
            raise ValueError("CEP não encontrado.") from e
        logger.warning(f"Erro ao consultar pycep-correios: {e}")
        raise ValueError("Erro ao consultar pycep-correios.") from e


def _buscar_brazilcep(cep: str) -> dict:
    """
    Busca CEP usando a biblioteca brazilcep.
    
    Args:
        cep: CEP no formato 00000000 ou 00000-000
        
    Returns:
        dict com informações do endereço
        
    Raises:
        ValueError: Se houver erro na consulta
    """
    if brazilcep is None:
        raise ValueError("Biblioteca brazilcep não está instalada.")
    
    try:
        endereco = brazilcep.get_address_from_cep(cep)
        return _normalizar_resposta(endereco, cep)
    except cep_exceptions.InvalidCEP as e:
        raise ValueError("CEP inválido.") from e
    except cep_exceptions.CEPNotFound as e:
        raise ValueError("CEP não encontrado.") from e
    except cep_exceptions.BrazilCEPException as e:
        logger.warning(f"Erro ao consultar brazilcep: {e}")
        raise ValueError("Erro ao consultar brazilcep.") from e


def buscar_endereco_por_cep(cep: str) -> dict:
    """
    Busca endereço a partir de um CEP usando múltiplas fontes com fallback automático.
    
    Tenta as seguintes fontes em ordem:
    1. ViaCEP (API pública)
    2. BrasilAPI (API pública)
    3. pycep-correios (biblioteca)
    4. brazilcep (biblioteca)
    
    Args:
        cep: CEP no formato 00000000 ou 00000-000
        
    Returns:
        dict com as informações do endereço:
        {
            'cep': '01311000',
            'street': 'Avenida Paulista',
            'district': 'Bela Vista',
            'city': 'São Paulo',
            'uf': 'SP',
            'complement': ''
        }
        
    Raises:
        ValueError: Se o CEP for inválido ou não encontrado em nenhuma fonte
    """
    if not cep or not cep.strip():
        raise ValueError("CEP não informado.")
    
    # Normaliza o CEP antes de tentar qualquer busca
    try:
        cep_normalizado = _normalizar_cep(cep)
    except ValueError as e:
        raise ValueError(f"CEP inválido: {str(e)}") from e
    
    # Lista de fontes para tentar (em ordem de prioridade)
    fontes = [
        ("ViaCEP", _buscar_via_cep),
        ("BrasilAPI", _buscar_brasil_api),
        ("pycep-correios", _buscar_pycep_correios),
        ("brazilcep", _buscar_brazilcep),
    ]
    
    # Tenta cada fonte até encontrar uma que funcione
    ultimo_erro = None
    fontes_tentadas = []
    erros_por_fonte = {}
    
    for nome_fonte, funcao_busca in fontes:
        logger.warning(f"[CEP] Tentando buscar CEP {cep_normalizado} via {nome_fonte}...")
        try:
            resultado = funcao_busca(cep_normalizado)
            if resultado and resultado.get('city'):  # Verifica se retornou dados válidos
                logger.warning(f"[CEP] ✓ Sucesso! CEP {cep_normalizado} encontrado via {nome_fonte}")
                return resultado
            else:
                # Resultado vazio ou sem cidade
                erro_msg = "Resultado vazio ou sem cidade"
                ultimo_erro = ValueError(erro_msg)
                fontes_tentadas.append(nome_fonte)
                erros_por_fonte[nome_fonte] = erro_msg
                logger.warning(f"[CEP] ✗ Falha ao buscar CEP {cep_normalizado} via {nome_fonte}: {erro_msg}")
                continue
        except ValueError as e:
            ultimo_erro = e
            fontes_tentadas.append(nome_fonte)
            erros_por_fonte[nome_fonte] = str(e)
            logger.warning(f"[CEP] ✗ Falha ao buscar CEP {cep_normalizado} via {nome_fonte}: {e}")
            continue
        except Exception as e:
            # Captura qualquer outra exceção para garantir que continue tentando outras fontes
            ultimo_erro = ValueError(f"Erro inesperado: {str(e)}")
            fontes_tentadas.append(nome_fonte)
            erros_por_fonte[nome_fonte] = f"Erro inesperado: {str(e)}"
            logger.warning(f"[CEP] ✗ Erro inesperado ao buscar CEP {cep_normalizado} via {nome_fonte}: {type(e).__name__}: {e}")
            continue
    
    # Se chegou aqui, nenhuma fonte funcionou
    if not ultimo_erro:
        raise ValueError(f"CEP não encontrado. Fontes tentadas: {', '.join(fontes_tentadas)}")
    
    # Se todas as fontes falharam, fornece uma mensagem mais informativa
    if len(fontes_tentadas) == len(fontes):
        mensagem = f"CEP {cep_normalizado} não encontrado em nenhuma fonte disponível."
        if erros_por_fonte:
            detalhes = "; ".join([f"{fonte}: {erro}" for fonte, erro in erros_por_fonte.items()])
            mensagem += f" Detalhes: {detalhes}"
        raise ValueError(mensagem)
    
    raise ultimo_erro

