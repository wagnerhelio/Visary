"""
Serviço para busca de endereço por CEP.
"""

try:
    import brazilcep
    from brazilcep import exceptions as cep_exceptions
except ImportError:
    brazilcep = None
    cep_exceptions = None


def buscar_endereco_por_cep(cep: str) -> dict:
    """
    Busca endereço a partir de um CEP usando a biblioteca brazilcep.
    
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
        ValueError: Se o CEP for inválido ou não encontrado
    """
    if brazilcep is None:
        raise ValueError("Biblioteca brazilcep não está instalada.")
    try:
        # brazilcep normaliza CEP automaticamente (com ou sem hífen)
        return brazilcep.get_address_from_cep(cep)
    except cep_exceptions.InvalidCEP:
        raise ValueError("CEP inválido.")
    except cep_exceptions.CEPNotFound:
        raise ValueError("CEP não encontrado.")
    except cep_exceptions.BrazilCEPException:
        raise ValueError("Erro ao consultar o CEP, tente novamente.")

