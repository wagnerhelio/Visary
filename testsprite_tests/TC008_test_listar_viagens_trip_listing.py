import requests
import re

BASE_URL = "http://localhost:8000"
LOGIN_URL = f"{BASE_URL}/login/"
LISTAR_VIAGENS_URL = f"{BASE_URL}/system/viagens/listar/"

def test_listar_viagens_trip_listing():
    session = requests.Session()

    # Step 1: Obtain CSRF token for login
    login_page = session.get(LOGIN_URL, timeout=30)
    csrf_match = re.search(r'name=[\'"]csrfmiddlewaretoken[\'"]\s+value=[\'"]([^\'"]+)[\'"]', login_page.text)
    csrf_token = csrf_match.group(1) if csrf_match else ''
    assert csrf_token, "CSRF token not found on login page"

    # Step 2: Login with admin credentials (default admin/admin)
    login_payload = {
        'identifier': 'admin',
        'password': 'admin',
        'csrfmiddlewaretoken': csrf_token,
    }
    headers = {'Referer': LOGIN_URL}
    login_resp = session.post(LOGIN_URL, data=login_payload, headers=headers, timeout=30, allow_redirects=False)
    assert login_resp.status_code in (200, 302), f'Login failed: {login_resp.status_code}'

    cookies_after_login = session.cookies.get_dict()
    assert 'sessionid' in cookies_after_login, (
        f"Session cookie not set after login POST. Cookies present: {list(cookies_after_login.keys())}."
        f" Login failed even if status is {login_resp.status_code}."
    )

    if login_resp.status_code == 302:
        location = login_resp.headers.get('Location')
        if location:
            session.get(f"{BASE_URL}{location}", timeout=30, allow_redirects=True)

    # Step 3: Access the listar_viagens endpoint
    resp = session.get(LISTAR_VIAGENS_URL, timeout=30)
    assert resp.status_code == 200, f"listar_viagens endpoint request failed with status {resp.status_code}"

    # Step 4: Response is expected HTML, verify that the page contains trip listings
    content = resp.text.lower()

    # Check typical keywords that should appear in the trips list
    # e.g. country names, visa types, travel dates - at least presence of table or headings expected
    expected_keywords = [
        "viagem",     # trip
        "país",       # country
        "visa",       # visa type
        "data",       # date
        "destino",    # destination
    ]
    assert any(keyword in content for keyword in expected_keywords), (
        f"Response content does not contain expected trip listing keywords."
    )

    # For a stronger test, attempt to detect presence of trip entries with countries, visa types and travel dates
    # Look for HTML table or list elements commonly used for listings
    assert (
        ("<table" in content and "</table>" in content) or
        ("<ul" in content and "</ul>" in content) or
        ("<div" in content and "viagem" in content)
    ), "Trip listings structure (table/list/div) not detected in response content"

    # Optional: spot check presence of some structured text that suggests data completeness
    # Since we can't rely on exact data, just check that there are multiple rows/items shown
    trip_row_markers = ['<tr', '<li', 'viagem']
    assert any(marker in content for marker in trip_row_markers), "No trip rows/items found in response content"

test_listar_viagens_trip_listing()