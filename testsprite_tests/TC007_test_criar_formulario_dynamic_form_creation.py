import requests
import re

BASE_URL = "http://localhost:8000"
LOGIN_URL = f"{BASE_URL}/login/"
CRIA_FORMULARIO_URL = f"{BASE_URL}/system/formularios/tipos/criar/"

def test_criar_formulario_dynamic_form_creation():
    session = requests.Session()
    # Step 1: Get CSRF token from login page
    login_page_resp = session.get(LOGIN_URL, timeout=30)
    assert login_page_resp.status_code == 200, f"Failed to load login page: {login_page_resp.status_code}"
    csrf_match = re.search(r'name=[\'\"]csrfmiddlewaretoken[\'\"]\s*value=[\'\"]([^\'\"]+)[\'\"]', login_page_resp.text)
    csrf_token = csrf_match.group(1) if csrf_match else ''
    assert csrf_token, "CSRF token not found on login page"

    # Step 2: POST login data
    login_payload = {
        'identifier': 'admin',
        'password': 'admin',
        'csrfmiddlewaretoken': csrf_token,
    }
    login_headers = {
        'Referer': LOGIN_URL
    }
    login_post_resp = session.post(LOGIN_URL, data=login_payload, headers=login_headers, timeout=30, allow_redirects=False)
    assert login_post_resp.status_code in (200, 302), f"Login failed: {login_post_resp.status_code}"

    cookies_after_login = session.cookies.get_dict()
    assert 'sessionid' in cookies_after_login, f"Session cookie not set after login POST. Cookies present: {list(cookies_after_login.keys())}"

    # Follow redirect if 302
    if login_post_resp.status_code == 302:
        location = login_post_resp.headers.get('Location')
        if location:
            session.get(f"{BASE_URL}{location}", timeout=30, allow_redirects=True)

    # Step 3: GET criar_formulario page to get new CSRF token for form creation
    create_form_page_resp = session.get(CRIA_FORMULARIO_URL, timeout=30)
    assert create_form_page_resp.status_code == 200, f"Failed to load form creation page: {create_form_page_resp.status_code}"
    csrf_form_match = re.search(r'name=[\'\"]csrfmiddlewaretoken[\'\"]\s*value=[\'\"]([^\'\"]+)[\'\"]', create_form_page_resp.text)
    csrf_form_token = csrf_form_match.group(1) if csrf_form_match else ''
    assert csrf_form_token, "CSRF token not found on form creation page"

    form_data = {
        'csrfmiddlewaretoken': csrf_form_token,
        'name': "Dynamic Visa Form Test",
        'visa_type': "Tourist",
        'questions-TOTAL_FORMS': '3',
        'questions-INITIAL_FORMS': '0',
        'questions-MIN_NUM_FORMS': '0',
        'questions-MAX_NUM_FORMS': '1000',
        'questions-0-question_text': 'What is your full name?',
        'questions-0-question_type': 'text',
        'questions-0-required': 'on',
        'questions-1-question_text': 'Select your gender',
        'questions-1-question_type': 'radio',
        'questions-1-required': 'on',
        'questions-1-options-TOTAL_FORMS': '2',
        'questions-1-options-INITIAL_FORMS': '0',
        'questions-1-options-MIN_NUM_FORMS': '0',
        'questions-1-options-MAX_NUM_FORMS': '1000',
        'questions-1-options-0-option_text': 'Male',
        'questions-1-options-1-option_text': 'Female',
        'questions-2-question_text': 'Which languages do you speak?',
        'questions-2-question_type': 'checkbox',
        'questions-2-required': '',
        'questions-2-options-TOTAL_FORMS': '3',
        'questions-2-options-INITIAL_FORMS': '0',
        'questions-2-options-MIN_NUM_FORMS': '0',
        'questions-2-options-MAX_NUM_FORMS': '1000',
        'questions-2-options-0-option_text': 'English',
        'questions-2-options-1-option_text': 'Spanish',
        'questions-2-options-2-option_text': 'French',
    }

    headers = {
        'Referer': CRIA_FORMULARIO_URL,
        'Content-Type': 'application/x-www-form-urlencoded',
    }

    post_resp = session.post(CRIA_FORMULARIO_URL, data=form_data, headers=headers, timeout=30, allow_redirects=True)
    assert post_resp.status_code in (200, 302), f"Form creation POST failed with status: {post_resp.status_code}"

    content = post_resp.text.lower()
    keywords = ["successfully", "created", "formulário criado", "form criado", "sucesso", "redirect"]
    assert any(k in content for k in keywords) or post_resp.status_code == 302, "Form creation might have failed, no success indication found in response"

test_criar_formulario_dynamic_form_creation()