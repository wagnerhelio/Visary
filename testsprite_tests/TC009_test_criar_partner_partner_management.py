import requests
import re

BASE_URL = "http://localhost:8000"
LOGIN_URL = f"{BASE_URL}/login/"
CRIA_PARTNER_URL = f"{BASE_URL}/system/partners/criar/"
DELETE_PARTNER_URL_TEMPLATE = f"{BASE_URL}/system/partners/{{partner_id}}/excluir/"

def test_criar_partner_partner_management():
    session = requests.Session()

    # Step 1: Login to acquire session cookie and CSRF token
    login_page = session.get(LOGIN_URL, timeout=30)
    csrf_match = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', login_page.text)
    csrf_token = csrf_match.group(1) if csrf_match else ""
    assert csrf_token, "CSRF token not found on login page"

    login_payload = {
        "identifier": "admin",
        "password": "admin",
        "csrfmiddlewaretoken": csrf_token
    }
    login_headers = {
        "Referer": LOGIN_URL
    }
    login_resp = session.post(LOGIN_URL, data=login_payload, headers=login_headers, allow_redirects=False, timeout=30)
    assert login_resp.status_code in (200, 302), f"Login failed: status code {login_resp.status_code}"
    cookies_after_login = session.cookies.get_dict()
    assert "sessionid" in cookies_after_login, "Session cookie not set after login - login failed even with status 302"
    if login_resp.status_code == 302:
        location = login_resp.headers.get("Location")
        if location:
            session.get(f"{BASE_URL}{location}", timeout=30, allow_redirects=True)

    # Step 2: Get CSRF token for partner creation page
    create_page = session.get(CRIA_PARTNER_URL, timeout=30)
    csrf_match2 = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', create_page.text)
    csrf_token_create = csrf_match2.group(1) if csrf_match2 else ""
    assert csrf_token_create, "CSRF token not found on partner creation page"

    # Step 3: Prepare partner data
    # Using sample valid data based on typical partner fields:
    # Assuming fields: name, segment, is_active (boolean represented by checkbox), and possibly others
    # Because PRD doesn't specify exact schema fields, we assume common partner fields: name (string), segment (string), is_active (checkbox)
    partner_data = {
        "csrfmiddlewaretoken": csrf_token_create,
        "name": "Test Partner XYZ",
        "segment": "Technology",
        "is_active": "on"  # checkbox checked value is usually "on"
    }

    # Step 4: Create partner
    create_resp = session.post(CRIA_PARTNER_URL, data=partner_data, headers={"Referer": CRIA_PARTNER_URL}, timeout=30, allow_redirects=False)
    # Usually a successful create results in a redirect (302) to the partner list or detail page
    assert create_resp.status_code in (200, 302), f"Partner creation failed: status {create_resp.status_code}"

    # Step 5: Determine partner ID from redirect/location or by listing
    partner_id = None
    if create_resp.status_code == 302:
        location = create_resp.headers.get("Location")
        if location:
            # Try to extract partner_id from location URL if possible, format might be /system/partners/{id}/
            import urllib.parse
            parsed_loc = urllib.parse.urlparse(location)
            path_segments = parsed_loc.path.strip("/").split("/")
            # Looking for an int segment possibly after 'partners'
            if "partners" in path_segments:
                idx = path_segments.index("partners")
                if idx + 1 < len(path_segments):
                    possible_id = path_segments[idx + 1]
                    if possible_id.isdigit():
                        partner_id = int(possible_id)
            # If partner_id not found here, we try to parse from listing page below

            # Follow redirect to landing page where partner list or details might be shown
            follow_resp = session.get(f"{BASE_URL}{location}", timeout=30)
            assert follow_resp.status_code == 200

    if partner_id is None:
        # If partner_id not found from redirect URL, try to retrieve from listing page by searching for the partner name
        listing_url = f"{BASE_URL}/system/partners/"
        listing_resp = session.get(listing_url, timeout=30)
        assert listing_resp.status_code == 200
        # Search for partner entry in listing_resp.text
        # Looking for a link to partner details with the partner name
        partner_id_match = re.search(r'href="(/system/partners/(\d+)/)"[^>]*>\s*Test Partner XYZ\s*<', listing_resp.text)
        if partner_id_match:
            partner_id = int(partner_id_match.group(2))

    assert partner_id is not None, "Failed to find new partner ID after creation"

    try:
        # Step 6: Verify the partner details via view page
        partner_detail_url = f"{BASE_URL}/system/partners/{partner_id}/"
        detail_resp = session.get(partner_detail_url, timeout=30)
        assert detail_resp.status_code == 200, f"Partner detail page not found for ID {partner_id}"
        assert "Test Partner XYZ" in detail_resp.text, "Partner name not found on detail page"
        assert "Technology" in detail_resp.text, "Partner segment not found or incorrect on detail page"
        # Check for active status presence, for example presence of 'Active' or checkbox checked. We assume "Active" label shown if active
        assert any(keyword in detail_resp.text for keyword in ["Active", "Ativo", "active"]), "Partner active status indicator not found on detail page"

        # Optionally: Test update of active status or segment management here...
        # Without specific instructions, we just verify partner is created and retrievable

    finally:
        # Step 7: Cleanup - Delete the created partner
        # Getting CSRF token for delete form/page
        delete_url = DELETE_PARTNER_URL_TEMPLATE.format(partner_id=partner_id)
        delete_page = session.get(delete_url, timeout=30)
        assert delete_page.status_code == 200, f"Partner delete page not found for ID {partner_id}"
        csrf_match_del = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', delete_page.text)
        csrf_token_del = csrf_match_del.group(1) if csrf_match_del else ""
        assert csrf_token_del, "CSRF token not found on partner deletion page"

        delete_payload = {
            "csrfmiddlewaretoken": csrf_token_del
        }
        delete_resp = session.post(delete_url, data=delete_payload, headers={"Referer": delete_url}, timeout=30, allow_redirects=False)
        # Usually deletion results in redirect to partners list or confirmation page
        assert delete_resp.status_code in (200, 302), f"Failed to delete partner ID {partner_id}, status {delete_resp.status_code}"

test_criar_partner_partner_management()