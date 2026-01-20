import requests
import re

BASE_URL = "http://localhost:8000"
LOGIN_URL = f"{BASE_URL}/login/"
CADASTRAR_CLIENTE_URL = f"{BASE_URL}/system/clientes/cadastrar/"
API_BUSCAR_CEP_URL = f"{BASE_URL}/system/api/buscar-cep/"

def test_cadastrar_cliente_view_registration_steps():
    session = requests.Session()

    # Step 1: Login with session-based authentication and csrf handling
    login_page = session.get(LOGIN_URL, timeout=30)
    csrf_match = re.search(r'name=[\'"]csrfmiddlewaretoken[\'"]\s+value=[\'"]([^\'"]+)[\'"]', login_page.text)
    csrf_token = csrf_match.group(1) if csrf_match else ''
    login_payload = {
        'identifier': 'admin',
        'password': 'admin',
        'remember_me': 'on',
        'csrfmiddlewaretoken': csrf_token
    }
    headers = {'Referer': LOGIN_URL}
    login_resp = session.post(LOGIN_URL, data=login_payload, headers=headers, allow_redirects=False, timeout=30)
    assert login_resp.status_code in (200, 302), f'Login failed: {login_resp.status_code}'
    cookies_after_login = session.cookies.get_dict()
    assert 'sessionid' in cookies_after_login, f'Session cookie not set after login POST. Cookies: {cookies_after_login}'
    if login_resp.status_code == 302:
        location = login_resp.headers.get('Location')
        if location:
            session.get(f"{BASE_URL}{location}", timeout=30, allow_redirects=True)

    # Step 2: Get initial CSRF token for the cadastrar_cliente_view form
    cadastrar_page = session.get(CADASTRAR_CLIENTE_URL, timeout=30)
    csrf_match = re.search(r'name=[\'"]csrfmiddlewaretoken[\'"]\s+value=[\'"]([^\'"]+)[\'"]', cadastrar_page.text)
    csrf_token = csrf_match.group(1) if csrf_match else ''
    assert csrf_token, "CSRF token not found on cadastrar_cliente_view page."

    # Step 3: Prepare multi-step registration data

    # Step 3.1: Personal data step
    personal_data_payload = {
        'csrfmiddlewaretoken': csrf_token,
        'step': 'personal_data',  # Assuming step indicator field name is 'step'
        'nome': 'Teste Cliente',
        'email': 'teste.cliente@example.com',
        'telefone': '11999999999',
        'data_nascimento': '1990-01-01',
        'cpf': '12345678909'  # Brazilian CPF format example
    }
    headers = {'Referer': CADASTRAR_CLIENTE_URL}
    resp_personal = session.post(CADASTRAR_CLIENTE_URL, data=personal_data_payload, headers=headers, timeout=30, allow_redirects=True)
    assert resp_personal.status_code == 200
    assert "endereço" in resp_personal.text.lower() or "address" in resp_personal.text.lower(), "Expected address step page after personal data."

    # Step 3.2: Address auto-fill via CEP lookup (simulate user entering CEP)
    cep = "01001000"  # Example valid CEP in São Paulo
    params = {'cep': cep}
    resp_cep = session.get(API_BUSCAR_CEP_URL, params=params, timeout=30)
    assert resp_cep.status_code == 200
    json_cep = resp_cep.json()
    assert 'cep' in json_cep and json_cep['cep'] == cep, f"CEP lookup failed or returned unexpected cep: {json_cep.get('cep')}"
    # Extract address fields from CEP lookup
    street = json_cep.get('street', '')
    district = json_cep.get('district', '')
    city = json_cep.get('city', '')
    uf = json_cep.get('uf', '')
    complement = json_cep.get('complement', '')

    # Step 3.3: Submit address step with auto-filled data
    # Get CSRF token from previous response if needed (for multiple-step forms, token may rotate)
    csrf_match = re.search(r'name=[\'"]csrfmiddlewaretoken[\'"]\s+value=[\'"]([^\'"]+)[\'"]', resp_personal.text)
    csrf_token = csrf_match.group(1) if csrf_match else csrf_token
    address_payload = {
        'csrfmiddlewaretoken': csrf_token,
        'step': 'address',
        'cep': cep,
        'street': street,
        'district': district,
        'city': city,
        'uf': uf,
        'complement': complement,
        'numero': '100',  # House number
        'bairro': district  # Some forms may expect bairro in Portuguese
    }
    headers['Referer'] = CADASTRAR_CLIENTE_URL
    resp_address = session.post(CADASTRAR_CLIENTE_URL, data=address_payload, headers=headers, timeout=30, allow_redirects=True)
    assert resp_address.status_code == 200
    assert "passaporte" in resp_address.text.lower() or "passport" in resp_address.text.lower(), "Expected passport step page after address."

    # Step 3.4: Submit passport data step
    csrf_match = re.search(r'name=[\'"]csrfmiddlewaretoken[\'"]\s+value=[\'"]([^\'"]+)[\'"]', resp_address.text)
    csrf_token = csrf_match.group(1) if csrf_match else csrf_token
    passport_payload = {
        'csrfmiddlewaretoken': csrf_token,
        'step': 'passport',
        'numero_passaporte': 'A1234567',
        'pais_emissao': 'BR',
        'data_emissao': '2015-05-10',
        'data_validade': '2025-05-10'
    }
    headers['Referer'] = CADASTRAR_CLIENTE_URL
    resp_passport = session.post(CADASTRAR_CLIENTE_URL, data=passport_payload, headers=headers, timeout=30, allow_redirects=True)
    assert resp_passport.status_code == 200
    assert ("dependente" in resp_passport.text.lower() or "dependents" in resp_passport.text.lower() or "dependente" in resp_passport.text.lower()), "Expected dependents step page after passport."

    # Step 3.5: Manage dependents - Add a dependent
    csrf_match = re.search(r'name=[\'"]csrfmiddlewaretoken[\'"]\s+value=[\'"]([^\'"]+)[\'"]', resp_passport.text)
    csrf_token = csrf_match.group(1) if csrf_match else csrf_token
    dependent_add_payload = {
        'csrfmiddlewaretoken': csrf_token,
        'step': 'dependents',
        'add_dependent': 'true',  # Assuming a flag like this enables adding
        'dependent_nome': 'Dependente Teste',
        'dependent_parentesco': 'filho',
        'dependent_data_nascimento': '2015-08-20'
    }
    headers['Referer'] = CADASTRAR_CLIENTE_URL
    resp_dependent_add = session.post(CADASTRAR_CLIENTE_URL, data=dependent_add_payload, headers=headers, timeout=30, allow_redirects=True)
    assert resp_dependent_add.status_code == 200
    assert "Dependente Teste" in resp_dependent_add.text or "dependente teste" in resp_dependent_add.text.lower(), "Dependent name not found in response after addition."

    # Step 3.6: Complete registration (submit final step)
    csrf_match = re.search(r'name=[\'"]csrfmiddlewaretoken[\'"]\s+value=[\'"]([^\'"]+)[\'"]', resp_dependent_add.text)
    csrf_token = csrf_match.group(1) if csrf_match else csrf_token
    finalize_payload = {
        'csrfmiddlewaretoken': csrf_token,
        'step': 'finalize',
        'confirm': 'true'  # Assuming a confirm field to finalize registration
    }
    headers['Referer'] = CADASTRAR_CLIENTE_URL
    resp_finalize = session.post(CADASTRAR_CLIENTE_URL, data=finalize_payload, headers=headers, timeout=30, allow_redirects=True)
    assert resp_finalize.status_code == 200
    success_msgs = ["cliente cadastrado", "cadastro efetuado", "cliente criado com sucesso"]
    assert any(msg in resp_finalize.text.lower() for msg in success_msgs), "Client registration success message not found."

    # Optionally, verify that the new client is retrievable/listed
    listar_clientes_url = f"{BASE_URL}/system/clientes/"
    resp_list = session.get(listar_clientes_url, timeout=30)
    assert resp_list.status_code == 200
    assert "teste cliente" in resp_list.text.lower(), "New client not found in clients list."

test_cadastrar_cliente_view_registration_steps()
