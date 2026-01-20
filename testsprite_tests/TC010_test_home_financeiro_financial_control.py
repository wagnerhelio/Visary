import requests
import re

BASE_URL = "http://localhost:8000"
LOGIN_URL = f"{BASE_URL}/login/"
SYSTEM_PREFIX = "/system"
HOME_FINANCEIRO_PATH = f"{SYSTEM_PREFIX}/financeiro/"
LISTAR_FINANCEIRO_PATH = f"{SYSTEM_PREFIX}/financeiro/listar/"
DAR_BAIXA_FINANCEIRO_PATH = f"{SYSTEM_PREFIX}/financeiro/baixar/"  # Assumed endpoint for payment updates

def test_home_financeiro_financial_control():
    session = requests.Session()
    # Step 1: Login with session-based auth
    login_page = session.get(LOGIN_URL, timeout=30)
    csrf_match = re.search(r'name=[\'"]csrfmiddlewaretoken[\'"]\s+value=[\'"]([^\'"]+)[\'"]', login_page.text)
    assert csrf_match, "CSRF token not found on login page"
    csrf_token = csrf_match.group(1)
    login_payload = {
        "identifier": "admin",
        "password": "admin",
        "csrfmiddlewaretoken": csrf_token
    }
    headers = {
        "Referer": LOGIN_URL
    }
    login_resp = session.post(LOGIN_URL, data=login_payload, headers=headers, timeout=30, allow_redirects=False)
    assert login_resp.status_code in (200, 302), f"Login failed with status code {login_resp.status_code}"
    cookies_after_login = session.cookies.get_dict()
    assert "sessionid" in cookies_after_login, f"Session cookie not set after login. Cookies: {list(cookies_after_login.keys())}"
    if login_resp.status_code == 302:
        location = login_resp.headers.get("Location")
        if location:
            session.get(f"{BASE_URL}{location}", timeout=30, allow_redirects=True)

    # Step 2: Access the home_financeiro page (HTML) and verify financial records are displayed
    financeiro_resp = session.get(f"{BASE_URL}{HOME_FINANCEIRO_PATH}", timeout=30)
    assert financeiro_resp.status_code == 200, f"Failed to load home_financeiro page, status {financeiro_resp.status_code}"
    financeiro_text = financeiro_resp.text.lower()
    # Check for expected content that indicates presence of financial records
    assert ("financeiro" in financeiro_text or "pagamento" in financeiro_text or "observação" in financeiro_text), \
        "Expected financial keywords not found in home_financeiro page content"

    # Step 3: List financial records via listar_financeiro endpoint (assuming JSON response)
    listar_resp = session.get(f"{BASE_URL}{LISTAR_FINANCEIRO_PATH}", timeout=30)
    assert listar_resp.status_code == 200, f"Failed to list financial records, status {listar_resp.status_code}"
    try:
        financial_data = listar_resp.json()
    except Exception:
        raise AssertionError("listar_financeiro did not return valid JSON")
    # financial_data format unknown, but must be a list or dict
    assert isinstance(financial_data, (list, dict)), "Financial list response data is not list or dict"

    # If no financial records, create a temporary financial record if possible (no create API info given).
    # Because PRD doesn't specify how to create financial entries via API, we can't create a new financial record.
    # So we will check if at least one financial record returned and operate on it.
    # If no records, skip update tests.
    if isinstance(financial_data, dict):
        # Might be dict with keys and list inside
        records = financial_data.get("results") or financial_data.get("financeiro_list") or []
    else:
        records = financial_data

    if not records:
        return  # No financial records to test update and observation notes

    # Use the first financial record for update test. Assume it has 'id', 'payment_status', 'observations' fields
    record = records[0]
    record_id = record.get("id")
    assert record_id is not None, "Financial record does not have 'id' field"

    # Assume payment status update requires POST or PUT to /system/financeiro/baixar/ with record id and payment status
    # Payload example: {"financeiro_id": record_id, "pago": True, "observacao": "Test note"}
    # We will attempt to toggle payment status and update observation note and verify updates.

    # Step 4: Get current status if possible and prepare update
    current_pago = record.get("pago")
    new_pago = not current_pago if isinstance(current_pago, bool) else True
    new_observacao = "Pagamento atualizado via automated test."

    # Before update, get fresh CSRF token from home_financeiro page for POST (likely needed)
    finance_page = session.get(f"{BASE_URL}{HOME_FINANCEIRO_PATH}", timeout=30)
    csrf_match = re.search(r'name=[\'"]csrfmiddlewaretoken[\'"]\s+value=[\'"]([^\'"]+)[\'"]', finance_page.text)
    assert csrf_match, "CSRF token not found on home_financeiro page"
    csrf_token = csrf_match.group(1)

    update_payload = {
        "financeiro_id": record_id,
        "pago": str(new_pago).lower(),  # Django may expect "true"/"false" strings
        "observacao": new_observacao,
        "csrfmiddlewaretoken": csrf_token
    }
    update_headers = {
        "Referer": f"{BASE_URL}{HOME_FINANCEIRO_PATH}"
    }
    update_url = f"{BASE_URL}{DAR_BAIXA_FINANCEIRO_PATH}"
    update_resp = session.post(update_url, data=update_payload, headers=update_headers, timeout=30, allow_redirects=False)

    # Accept status 200 or a redirect (e.g., 302) after POST
    assert update_resp.status_code in (200, 302), f"Failed to update payment status, got {update_resp.status_code}"

    # Step 5: Verify update by fetching the financial list again
    verify_resp = session.get(f"{BASE_URL}{LISTAR_FINANCEIRO_PATH}", timeout=30)
    assert verify_resp.status_code == 200, f"Failed to list financial records for verification, status {verify_resp.status_code}"
    try:
        verify_data = verify_resp.json()
    except Exception:
        raise AssertionError("listar_financeiro did not return valid JSON on verification")

    if isinstance(verify_data, dict):
        verify_records = verify_data.get("results") or verify_data.get("financeiro_list") or []
    else:
        verify_records = verify_data

    # Find the updated record by id
    updated_record = None
    for r in verify_records:
        if r.get("id") == record_id:
            updated_record = r
            break
    assert updated_record is not None, "Updated financial record not found after update"

    # Check payment status updated and observation note maintained
    updated_pago = updated_record.get("pago")
    updated_observacao = updated_record.get("observacao") or updated_record.get("observations") or ""
    # Django strings might be case insensitive, or might be boolean; handle flexibly
    if isinstance(updated_pago, str):
        updated_pago_bool = updated_pago.lower() == "true"
    else:
        updated_pago_bool = bool(updated_pago)
    assert updated_pago_bool == new_pago, "Payment status not updated correctly"
    assert new_observacao in updated_observacao, "Observation note not updated/maintained correctly"

test_home_financeiro_financial_control()