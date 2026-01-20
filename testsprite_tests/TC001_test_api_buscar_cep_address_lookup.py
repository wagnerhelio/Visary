import requests
import re

BASE_URL = "http://localhost:8000"
LOGIN_URL = f"{BASE_URL}/login/"
API_CEP_URL = f"{BASE_URL}/system/api/buscar-cep/"

def test_api_buscar_cep_address_lookup():
    session = requests.Session()

    # Step 1: GET login page to obtain CSRF token
    login_page = session.get(LOGIN_URL, timeout=30)
    csrf_match = re.search(r"name=['\"]csrfmiddlewaretoken['\"]\s+value=['\"]([^'\"]+)['\"]", login_page.text)
    csrf_token = csrf_match.group(1) if csrf_match else ''
    assert csrf_token, "CSRF token not found on login page"

    # Step 2: POST login credentials with CSRF token, without redirects
    login_payload = {
        'identifier': 'admin',
        'password': 'admin',
        'csrfmiddlewaretoken': csrf_token
    }
    headers = {
        'Referer': LOGIN_URL
    }
    login_resp = session.post(LOGIN_URL, data=login_payload, headers=headers, timeout=30, allow_redirects=False)
    assert login_resp.status_code in (200, 302), f"Login failed with status code {login_resp.status_code}"

    # Step 3: Check for sessionid cookie BEFORE following redirects
    cookies_after_login = session.cookies.get_dict()
    assert 'sessionid' in cookies_after_login, (
        f"Session cookie 'sessionid' not set after login POST. Cookies present: {list(cookies_after_login.keys())}"
    )

    # Step 4: Follow redirect if present
    if login_resp.status_code == 302:
        location = login_resp.headers.get('Location')
        if location:
            session.get(f"{BASE_URL}{location}", timeout=30, allow_redirects=True)

    # At this point, session is authenticated

    test_ceps = [
        "01001000",  # São Paulo - normal CEP expected available via primary API
        "99999999"   # Nonexistent CEP to simulate primary API failure, forcing fallback or error handling
    ]

    for cep in test_ceps:
        params = {'cep': cep}
        try:
            resp = session.get(API_CEP_URL, params=params, timeout=30)
        except requests.RequestException as e:
            assert False, f"HTTP request failed for CEP {cep}: {e}"

        assert resp.status_code == 200, f"Unexpected status code {resp.status_code} for CEP {cep}"
        try:
            data = resp.json()
        except ValueError:
            assert False, f"Response is not valid JSON for CEP {cep}. Response text: {resp.text}"

        if 'error' in data:
            assert isinstance(data['error'], str) and data['error'], f"Error message missing or invalid for CEP {cep}"
        else:
            expected_keys = ['cep', 'street', 'district', 'city', 'uf', 'complement']
            for key in expected_keys:
                assert key in data, f"Key '{key}' missing in response for CEP {cep}"
                assert isinstance(data[key], str), f"Key '{key}' is not a string for CEP {cep}"
            returned_cep = data['cep'].replace('-', '').strip()
            assert returned_cep.isdigit() and len(returned_cep) == 8, f"Returned CEP invalid format for CEP {cep}"
    session.close()

test_api_buscar_cep_address_lookup()
