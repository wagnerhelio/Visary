import requests
import re

BASE_URL = "http://localhost:8000"


def test_api_cliente_info_access():
    session = requests.Session()

    # Step 1: Get CSRF token from login page
    login_page_resp = session.get(f"{BASE_URL}/login/", timeout=30)
    assert login_page_resp.status_code == 200, f"GET /login/ failed with status {login_page_resp.status_code}"
    csrf_match = re.search(r'name=[\'"]csrfmiddlewaretoken[\'"]\s+value=[\'"]([^\'"]+)[\'"]', login_page_resp.text)
    csrf_token = csrf_match.group(1) if csrf_match else None
    assert csrf_token, "CSRF token not found on login page"

    # Step 2: POST login with identifier, password and csrfmiddlewaretoken
    login_payload = {
        "identifier": "admin",
        "password": "admin",
        "csrfmiddlewaretoken": csrf_token,
    }
    login_headers = {
        "Referer": f"{BASE_URL}/login/",
    }
    login_resp = session.post(f"{BASE_URL}/login/", data=login_payload, headers=login_headers, timeout=30, allow_redirects=False)
    assert login_resp.status_code in (200, 302), f"Login failed with status {login_resp.status_code}"
    cookies_after_login = session.cookies.get_dict()
    assert "sessionid" in cookies_after_login, (
        f"CRITICAL: sessionid cookie not found after login POST. Cookies present: {list(cookies_after_login.keys())}"
    )
    # Follow redirect if status 302
    if login_resp.status_code == 302:
        location = login_resp.headers.get("Location")
        if location:
            follow_resp = session.get(f"{BASE_URL}{location}", timeout=30, allow_redirects=True)
            assert follow_resp.status_code == 200, f"Failed to follow login redirect: {follow_resp.status_code}"

    # Step 3: Create a new client to obtain a valid cliente_id for testing
    # We will use the client registration endpoint: /system/clientes/cadastrar/
    # First get CSRF token from cadastrar_cliente form
    cadastrar_cliente_get_resp = session.get(f"{BASE_URL}/system/clientes/cadastrar/", timeout=30)
    assert cadastrar_cliente_get_resp.status_code == 200, f"GET /system/clientes/cadastrar/ failed with status {cadastrar_cliente_get_resp.status_code}"
    csrf_match_cadastrar = re.search(r'name=[\'"]csrfmiddlewaretoken[\'"]\s+value=[\'"]([^\'"]+)[\'"]', cadastrar_cliente_get_resp.text)
    csrf_token_cadastrar = csrf_match_cadastrar.group(1) if csrf_match_cadastrar else None
    assert csrf_token_cadastrar, "CSRF token not found on cadastrar_cliente page"

    # Prepare minimal payload for client registration (must match server expectations)
    # Since detailed schema not provided, use plausible minimal required fields
    cadastrar_payload = {
        "nome": "Test Client API TC003",
        "email": "testclienttc003@example.com",
        "cpf": "00000000001",
        "telefone": "11999999999",
        "csrfmiddlewaretoken": csrf_token_cadastrar,
    }
    cadastrar_headers = {
        "Referer": f"{BASE_URL}/system/clientes/cadastrar/",
    }
    cadastrar_post_resp = session.post(
        f"{BASE_URL}/system/clientes/cadastrar/",
        data=cadastrar_payload,
        headers=cadastrar_headers,
        timeout=30,
        allow_redirects=False,
    )
    # Expect redirect on successful client creation
    assert cadastrar_post_resp.status_code in (302, 303), f"Failed to create client, status {cadastrar_post_resp.status_code}"

    # Extract the Location header for redirect to get client ID (commonly redirect might be to client detail page /system/clientes/123/)
    location = cadastrar_post_resp.headers.get("Location")
    assert location, "No redirect location found after client creation"
    import urllib.parse

    # Try to extract client ID from redirect URL which matches pattern /system/clientes/<id>/ or similar
    # Fallback to alternative method if no ID found
    cliente_id = None
    path = urllib.parse.urlparse(location).path
    # Assume pattern /system/clientes/<id>/ or /system/clientes/editar/<id>/ or similar
    import re as regex_module

    id_match = regex_module.search(r"/system/clientes/(\d+)/", path)
    if id_match:
        cliente_id = id_match.group(1)

    # If no ID found from redirect, fallback: after creation, list clients and find created one by name/email (TBD)
    if not cliente_id:
        # Fetch client list page and parse
        list_resp = session.get(f"{BASE_URL}/system/clientes/", timeout=30)
        assert list_resp.status_code == 200, "Failed to list clients to find new client ID"
        # Try to find client row in HTML with link containing client id
        id_search = regex_module.search(r'/system/clientes/(\d+)/.*?Test Client API TC003', list_resp.text)
        if id_search:
            cliente_id = id_search.group(1)
    assert cliente_id, "Failed to determine cliente_id for newly created client"

    try:
        # Step 4: Test the api_cliente_info endpoint with the obtained cliente_id
        api_url = f"{BASE_URL}/system/api/cliente-info/"
        params = {"cliente_id": cliente_id}
        api_resp = session.get(api_url, params=params, timeout=30)
        assert api_resp.status_code == 200, f"api_cliente_info returned status {api_resp.status_code}"
        json_data = api_resp.json()
        # On success, must have 'criado_em' key with ISO datetime string
        assert "criado_em" in json_data, "Response JSON missing 'criado_em' key"
        criado_em = json_data["criado_em"]
        assert isinstance(criado_em, str) and len(criado_em) > 0, "'criado_em' is empty or not a string"
        # Should NOT contain full client details like id, name, email, etc.
        wrong_keys = ["id", "nome", "email", "cliente", "data_base"]
        for key in wrong_keys:
            assert key not in json_data, f"Response JSON contains unexpected key '{key}'"

        # Step 5: Test unauthorized access to the same endpoint (logout and try)
        session.get(f"{BASE_URL}/logout/", timeout=30)  # Assuming /logout/ logs out user
        noauth_resp = session.get(api_url, params=params, timeout=30)
        # Should be redirect to login or 403/401 forbidden
        assert noauth_resp.status_code in (401, 403, 302), f"Expected unauthorized status or redirect after logout, got {noauth_resp.status_code}"
        if noauth_resp.status_code == 302:
            # Redirect location should be to login page
            loc = noauth_resp.headers.get("Location", "")
            assert "/login" in loc, f"Redirect after unauthorized access not to login page: {loc}"
    finally:
        # Cleanup: Delete the created client to leave no state
        # If there is an API or form to delete client - Not specified in PRD
        # Assuming delete at /system/clientes/remover/<cliente_id> or similar - try GET then POST
        # Try GET delete page to get CSRF token for deletion
        delete_url = f"{BASE_URL}/system/clientes/remover/{cliente_id}/"
        get_delete = session.get(delete_url, timeout=30)
        if get_delete.status_code == 200:
            csrf_match_del = regex_module.search(r'name=[\'"]csrfmiddlewaretoken[\'"]\s+value=[\'"]([^\'"]+)[\'"]', get_delete.text)
            csrf_token_del = csrf_match_del.group(1) if csrf_match_del else None
            if csrf_token_del:
                delete_headers = {"Referer": delete_url}
                delete_data = {"csrfmiddlewaretoken": csrf_token_del}
                # Assuming POST deletes
                delete_resp = session.post(delete_url, data=delete_data, headers=delete_headers, timeout=30, allow_redirects=False)
                if delete_resp.status_code not in (302, 303):
                    # Possibly deletion failed, try GET or ignore
                    pass
            else:
                # No CSRF token, can't delete
                pass
        else:
            # No delete endpoint, no cleanup possible
            pass


test_api_cliente_info_access()