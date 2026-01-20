import requests
import re

BASE_URL = "http://localhost:8000"
LOGIN_URL = f"{BASE_URL}/login/"
CREATE_CLIENT_URL = f"{BASE_URL}/system/clientes/cadastrar/"
LIST_TRIPS_URL = f"{BASE_URL}/system/viagens/listar/"
CREATE_PROCESS_URL = f"{BASE_URL}/system/processos/criar/"
DELETE_PROCESS_BASE_URL = f"{BASE_URL}/system/processos/"
TIMEOUT = 30

ADMIN_IDENTIFIER = "admin"
ADMIN_PASSWORD = "admin"


def test_criar_processo_process_creation_and_tracking():
    session = requests.Session()

    # Step 1: Login (session-based authentication)
    login_page = session.get(LOGIN_URL, timeout=TIMEOUT)
    csrf_match = re.search(r'name=[\'\"]csrfmiddlewaretoken[\'\"]\s+value=[\'\"]([^\'\"]+)[\'\"]', login_page.text)
    csrf_token = csrf_match.group(1) if csrf_match else ""
    assert csrf_token, "CSRF token not found on login page."

    login_payload = {
        "identifier": ADMIN_IDENTIFIER,
        "password": ADMIN_PASSWORD,
        "csrfmiddlewaretoken": csrf_token,
    }
    login_headers = {
        "Referer": LOGIN_URL,
    }
    login_resp = session.post(LOGIN_URL, data=login_payload, headers=login_headers, timeout=TIMEOUT, allow_redirects=False)
    assert login_resp.status_code in (200, 302), f"Login failed with status code {login_resp.status_code}"

    cookies_after_login = session.cookies.get_dict()
    assert "sessionid" in cookies_after_login, f"Session cookie not set after login POST. Cookies: {cookies_after_login}"

    # Follow redirect if exists
    if login_resp.status_code == 302:
        location = login_resp.headers.get("Location")
        if location:
            session.get(f"{BASE_URL}{location}", timeout=TIMEOUT, allow_redirects=True)

    # Step 2: Create a new client to associate with the process
    # GET client creation page to obtain CSRF token
    client_creation_page = session.get(CREATE_CLIENT_URL, timeout=TIMEOUT)
    csrf_match = re.search(r'name=[\'\"]csrfmiddlewaretoken[\'\"]\s+value=[\'\"]([^\'\"]+)[\'\"]', client_creation_page.text)
    csrf_token_client = csrf_match.group(1) if csrf_match else ""
    assert csrf_token_client, "CSRF token not found on client creation page."

    # Minimal client data for creation (can be adjusted if schema known)
    new_client_payload = {
        "csrfmiddlewaretoken": csrf_token_client,
        "nome": "Teste Cliente Processo",
        "email": "testeclienteprocesso@example.com",
        "cpf": "12345678901",
        "telefone": "11999999999",
        # Add any mandatory fields required by form; dummy data used
        # Since no explicit schema, these fields are assumed placeholders
    }
    client_headers = {
        "Referer": CREATE_CLIENT_URL,
    }
    client_post_resp = session.post(CREATE_CLIENT_URL, data=new_client_payload, headers=client_headers, timeout=TIMEOUT, allow_redirects=False)
    # On success, usually redirects (302)
    assert client_post_resp.status_code in (200, 302), f"Client creation failed with status code {client_post_resp.status_code}"

    # Attempt to find created client id:
    # Since likely redirected to client list or client detail page, try to extract client id from redirect location or page content
    client_id = None
    if client_post_resp.status_code == 302:
        location = client_post_resp.headers.get("Location")
        if location:
            # Example redirect might be like /system/clientes/123/ or similar
            match = re.search(r"/system/clientes/(\d+)/", location)
            if match:
                client_id = int(match.group(1))
            else:
                # Get that page and try to parse client ID from it
                detail_resp = session.get(f"{BASE_URL}{location}", timeout=TIMEOUT)
                match = re.search(r"Cliente\s*ID[:\s]*([0-9]+)", detail_resp.text, re.IGNORECASE)
                if match:
                    client_id = int(match.group(1))
    if not client_id:
        # Fallback: try to list clients and find by name/email
        list_clients_url = f"{BASE_URL}/system/clientes/"
        clients_list_resp = session.get(list_clients_url, timeout=TIMEOUT)
        # Try to find client ID referencing "Teste Cliente Processo"
        match = re.search(r'/system/clientes/(\d+)/.*Teste Cliente Processo', clients_list_resp.text)
        if match:
            client_id = int(match.group(1))

    assert client_id is not None, "Failed to determine client ID after creation."

    # Step 3: List existing trips to associate one for the process
    trips_resp = session.get(LIST_TRIPS_URL, timeout=TIMEOUT)
    assert trips_resp.status_code == 200, f"Failed to list trips, status code {trips_resp.status_code}"
    # We expect trips in HTML; parse for trip IDs (example pattern)
    trip_id = None
    # Look for hrefs or forms with trip IDs
    trip_matches = re.findall(r'/system/viagens/(\d+)', trips_resp.text)
    if trip_matches:
        trip_id = int(trip_matches[0])
    else:
        # If no trips exist, fail as we cannot create process without trip
        raise Exception("No trips found to associate with the process.")

    # Step 4: Get CSRF token for process creation page
    create_process_page = session.get(CREATE_PROCESS_URL, timeout=TIMEOUT)
    csrf_match = re.search(r'name=[\'\"]csrfmiddlewaretoken[\'\"]\s+value=[\'\"]([^\'\"]+)[\'\"]', create_process_page.text)
    csrf_token_process = csrf_match.group(1) if csrf_match else ""
    assert csrf_token_process, "CSRF token not found on process creation page."

    # Step 5: Create the visa process linked to client and trip
    create_process_payload = {
        "csrfmiddlewaretoken": csrf_token_process,
        "cliente": str(client_id),
        "viagem": str(trip_id),
        # Include other fields as might be required for process creation (using placeholders)
        # For example, status, step, initial observations, deadlines, etc.
        # If unknown, attempt minimal needed fields
        "status": "1",  # Assuming "1" is a valid default status id
        "etapa": "1",   # Assuming "1" is a valid initial step id
    }
    process_headers = {
        "Referer": CREATE_PROCESS_URL,
    }

    # Will use try-finally to delete process after test
    created_process_id = None
    try:
        process_post_resp = session.post(CREATE_PROCESS_URL, data=create_process_payload, headers=process_headers, timeout=TIMEOUT, allow_redirects=False)
        assert process_post_resp.status_code in (200, 302), f"Process creation failed with status {process_post_resp.status_code}"

        # Extract created process ID similar to client id
        if process_post_resp.status_code == 302:
            location = process_post_resp.headers.get("Location")
            if location:
                match = re.search(r"/system/processos/(\d+)/", location)
                if match:
                    created_process_id = int(match.group(1))
        if not created_process_id:
            # If no redirect location with ID captured, fetch process listing or page and attempt capture
            list_process_url = f"{BASE_URL}/system/processos/"
            process_list_resp = session.get(list_process_url, timeout=TIMEOUT)
            # Try to find process linked to our client and trip
            # Example pattern might vary; we try to find first matching
            match = re.search(r'/system/processos/(\d+)/.*Teste Cliente Processo.*', process_list_resp.text)
            if match:
                created_process_id = int(match.group(1))

        assert created_process_id is not None, "Failed to determine created process ID."

        # Step 6: Retrieve the created process page and verify association and tracking info
        process_detail_url = f"{BASE_URL}/system/processos/{created_process_id}/"
        process_detail_resp = session.get(process_detail_url, timeout=TIMEOUT)
        assert process_detail_resp.status_code == 200, f"Failed to get process detail, status {process_detail_resp.status_code}"

        # Verify client and trip association mentioned in page content
        assert "Teste Cliente Processo" in process_detail_resp.text, "Process detail does not contain expected client name."
        assert str(trip_id) in process_detail_resp.text or "Viagem" in process_detail_resp.text, "Process detail does not mention trip."

        # Verify tracking steps and statuses appear in page content (generic check)
        expected_elements = ["Etapa", "Status", "Prazo", "Progresso"]
        for elem in expected_elements:
            assert elem in process_detail_resp.text, f"Process tracking element '{elem}' not found in detail page."

    finally:
        # Cleanup: delete created process if created
        if created_process_id:
            delete_url = f"{DELETE_PROCESS_BASE_URL}{created_process_id}/deletar/"
            delete_page = session.get(delete_url, timeout=TIMEOUT)
            csrf_match = re.search(r'name=[\'\"]csrfmiddlewaretoken[\'\"]\s+value=[\'\"]([^\'\"]+)[\'\"]', delete_page.text)
            csrf_token_delete = csrf_match.group(1) if csrf_match else ""
            if csrf_token_delete:
                delete_payload = {"csrfmiddlewaretoken": csrf_token_delete}
                delete_headers = {"Referer": delete_url}
                delete_resp = session.post(delete_url, data=delete_payload, headers=delete_headers, timeout=TIMEOUT, allow_redirects=False)
                # Accept 200 or 302 for successful deletion
                assert delete_resp.status_code in (200, 302), f"Process deletion failed with status {delete_resp.status_code}"

    # Optional: Cleanup created client if desired
    # Since no endpoint provided for client deletion, skipping cleanup


test_criar_processo_process_creation_and_tracking()
