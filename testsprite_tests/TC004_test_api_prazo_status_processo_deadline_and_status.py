import requests
import re

BASE_URL = "http://localhost:8000"
LOGIN_URL = f"{BASE_URL}/login/"
API_PRAZO_STATUS_PROCESSO_URL = f"{BASE_URL}/system/api/prazo-status-processo/"
TIMEOUT = 30

def test_api_prazo_status_processo_deadline_and_status():
    session = requests.Session()

    # Step 1: GET login page to obtain CSRF token
    login_page_resp = session.get(LOGIN_URL, timeout=TIMEOUT)
    assert login_page_resp.status_code == 200, f"Failed to load login page, status {login_page_resp.status_code}"
    csrf_search = re.search(r'name=[\'\"]csrfmiddlewaretoken[\'\"]\s+value=[\'\"]([^\'\"]+)[\'\"]', login_page_resp.text)
    csrf_token = csrf_search.group(1) if csrf_search else ''
    assert csrf_token, "CSRF token not found on login page"

    # Step 2: POST login credentials with CSRF token
    login_payload = {
        'identifier': 'admin',
        'password': 'admin',
        'csrfmiddlewaretoken': csrf_token
    }
    headers = {'Referer': LOGIN_URL}
    login_resp = session.post(
        LOGIN_URL,
        data=login_payload,
        headers=headers,
        timeout=TIMEOUT,
        allow_redirects=False
    )
    assert login_resp.status_code in (200, 302), f"Login failed, status code {login_resp.status_code}"

    # Step 3: Verify session cookie immediately after POST
    cookies_after_login = session.cookies.get_dict()
    assert 'sessionid' in cookies_after_login, (
        f"Session cookie not set after login POST. Cookies present: {list(cookies_after_login.keys())}. "
        f"Login failed even if status is {login_resp.status_code}."
    )

    # If redirected, follow the redirect
    if login_resp.status_code == 302:
        location = login_resp.headers.get('Location')
        if location:
            redirect_url = f"{BASE_URL}{location}" if location.startswith("/") else location
            follow_resp = session.get(redirect_url, timeout=TIMEOUT, allow_redirects=True)
            assert follow_resp.status_code == 200, f"Redirect follow failed with status {follow_resp.status_code}"

    # Verify that we are authenticated by accessing a protected URL
    protected_url = f"{BASE_URL}/system/clientes/"
    protected_resp = session.get(protected_url, timeout=TIMEOUT)
    assert protected_resp.status_code == 200, f"Not authenticated, got status {protected_resp.status_code}. URL: {protected_resp.url}"
    assert 'login' not in protected_resp.url.lower(), "Still on login page after authentication"

    # Use typical status_id=1 as per PRD
    status_id = 1
    params = {'status_id': status_id}

    # Make GET request to api_prazo_status_processo endpoint
    response = session.get(API_PRAZO_STATUS_PROCESSO_URL, params=params, timeout=TIMEOUT)
    assert response.status_code == 200, f"API call failed with status {response.status_code}"

    # Response must be JSON
    try:
        resp_json = response.json()
    except Exception as e:
        raise AssertionError(f"Response is not valid JSON: {e}")

    # Validate success or error structure
    if 'error' in resp_json:
        error_msg = resp_json.get('error', '')
        assert False, f"API returned error: {error_msg}"
    else:
        assert 'prazo_padrao_dias' in resp_json, "'prazo_padrao_dias' key missing in success response"
        prazo_padrao_dias = resp_json['prazo_padrao_dias']
        assert isinstance(prazo_padrao_dias, int), f"'prazo_padrao_dias' is not int: {prazo_padrao_dias}"
        assert prazo_padrao_dias > 0, f"'prazo_padrao_dias' should be positive integer, got: {prazo_padrao_dias}"

test_api_prazo_status_processo_deadline_and_status()
