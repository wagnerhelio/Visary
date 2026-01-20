import requests
import re

BASE_URL = "http://localhost:8000"
LOGIN_URL = f"{BASE_URL}/login/"
API_DADOS_CLIENTE_URL = f"{BASE_URL}/system/clientes/dados/"
USERNAME = "admin"
PASSWORD = "admin"
TIMEOUT = 30

def test_api_dados_cliente_retrieval():
    session = requests.Session()

    # Get CSRF token for login
    login_page = session.get(LOGIN_URL, timeout=TIMEOUT)
    assert login_page.status_code == 200, f"Login page GET failed with status {login_page.status_code}"
    csrf_match = re.search(r'name=[\'\"]csrfmiddlewaretoken[\'\"]\s*value=[\'\"]([^\'\"]+)[\'\"]', login_page.text)
    csrf_token = csrf_match.group(1).strip() if csrf_match else ""
    assert csrf_token, "CSRF token not found on login page"

    # Perform login POST with csrf token, identifier and password
    login_payload = {
        "identifier": USERNAME,
        "password": PASSWORD,
        "csrfmiddlewaretoken": csrf_token
    }
    headers = {
        "Referer": LOGIN_URL
    }
    login_resp = session.post(LOGIN_URL, data=login_payload, headers=headers, allow_redirects=False, timeout=TIMEOUT)
    assert login_resp.status_code in (200, 302), f"Login failed with status code {login_resp.status_code}"
    cookies_after_login = session.cookies.get_dict()
    assert "sessionid" in cookies_after_login, f"Session cookie not set after login POST. Cookies: {cookies_after_login}"

    # Follow redirect after login if 302 and Location header present
    if login_resp.status_code == 302:
        location = login_resp.headers.get("Location")
        if location:
            session.get(f"{BASE_URL}{location}", allow_redirects=True, timeout=TIMEOUT)

    # Verify authentication by accessing a protected page
    protected_url = f"{BASE_URL}/system/clientes/"
    protected_resp = session.get(protected_url, timeout=TIMEOUT)
    assert protected_resp.status_code == 200, f"Access to protected url failed with status {protected_resp.status_code}"
    assert "login" not in protected_resp.url.lower(), f"Still redirected to login page after authentication, got url: {protected_resp.url}"

    # Since cliente_id is required, create a new client resource via /system/clientes/cadastrar/
    cadastrar_url = f"{BASE_URL}/system/clientes/cadastrar/"
    cadastrar_page = session.get(cadastrar_url, timeout=TIMEOUT)
    assert cadastrar_page.status_code == 200, f"Client registration page GET failed with status {cadastrar_page.status_code}"
    csrf_match = re.search(r'name=[\'\"]csrfmiddlewaretoken[\'\"]\s*value=[\'\"]([^\'\"]+)[\'\"]', cadastrar_page.text)
    csrf_token_cadastrar = csrf_match.group(1).strip() if csrf_match else ""
    assert csrf_token_cadastrar, "CSRF token not found on client registration page"

    import uuid
    unique_name = f"Test Client {uuid.uuid4()}"
    client_payload = {
        "csrfmiddlewaretoken": csrf_token_cadastrar,
        "nome": unique_name,
    }
    headers_cadastrar = {"Referer": cadastrar_url}
    create_resp = session.post(cadastrar_url, data=client_payload, headers=headers_cadastrar, allow_redirects=False, timeout=TIMEOUT)
    assert create_resp.status_code in (200, 302), f"Client creation failed with status {create_resp.status_code}"
    if create_resp.status_code == 302:
        location = create_resp.headers.get("Location")
        assert location, "No Location header after client creation redirect"
        redirected_resp = session.get(f"{BASE_URL}{location}", timeout=TIMEOUT)
        cliente_id = None
        id_match = re.search(r"/system/clientes/(\d+)/", location)
        if id_match:
            cliente_id = int(id_match.group(1))
        else:
            id_search = re.search(r'href="/system/clientes/(\d+)/.*?'+re.escape(unique_name), redirected_resp.text, re.IGNORECASE | re.DOTALL)
            if id_search:
                cliente_id = int(id_search.group(1))
        if cliente_id is None:
            listar_url = f"{BASE_URL}/system/clientes/"
            listing_resp = session.get(listar_url, timeout=TIMEOUT)
            list_id_search = re.search(r'href="/system/clientes/(\d+)/.*?'+re.escape(unique_name), listing_resp.text, re.IGNORECASE | re.DOTALL)
            if list_id_search:
                cliente_id = int(list_id_search.group(1))
        assert cliente_id is not None, "Failed to determine cliente_id for newly created client"
    else:
        assert False, "Client creation did not redirect, cannot retrieve cliente_id"

    try:
        params = {"cliente_id": cliente_id}
        api_resp = session.get(API_DADOS_CLIENTE_URL, params=params, timeout=TIMEOUT)
        assert api_resp.status_code == 200, f"API call failed with status {api_resp.status_code}"
        resp_json = api_resp.json()
        assert "data_base" in resp_json or "error" in resp_json, "Response missing expected keys"
        if "error" in resp_json:
            assert False, f"API error response: {resp_json['error']}"
        else:
            assert isinstance(resp_json["data_base"], str) and resp_json["data_base"], "data_base is missing or empty"
            cliente = resp_json.get("cliente")
            assert cliente and isinstance(cliente, dict), "cliente data missing or malformed"
            nome_returned = cliente.get("nome")
            assert nome_returned == unique_name, f"Returned client name mismatch. Expected '{unique_name}', got '{nome_returned}'"
    finally:
        delete_paths = [f"/system/clientes/{cliente_id}/deletar/", f"/system/clientes/{cliente_id}/excluir/"]
        deleted = False
        for path in delete_paths:
            delete_url = f"{BASE_URL}{path}"
            del_get = session.get(delete_url, timeout=TIMEOUT)
            if del_get.status_code == 200:
                csrf_match = re.search(r'name=[\'\"]csrfmiddlewaretoken[\'\"]\s*value=[\'\"]([^\'\"]+)[\'\"]', del_get.text)
                csrf_token_del = csrf_match.group(1).strip() if csrf_match else None
                if csrf_token_del:
                    del_payload = {"csrfmiddlewaretoken": csrf_token_del}
                    del_headers = {"Referer": delete_url}
                    del_post = session.post(delete_url, data=del_payload, headers=del_headers, timeout=TIMEOUT)
                    if del_post.status_code in (200, 302):
                        deleted = True
                        break
        if not deleted:
            pass

test_api_dados_cliente_retrieval()