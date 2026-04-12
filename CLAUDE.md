# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Protocolo de execução (fases, PRD, TDD): ver `AGENTS.md`. Este arquivo é o contexto **deste** projeto.

---

## Perfil do projeto

- **Produto:** Visary — sistema web de gestão de consultoria de vistos (clientes, viagens, processos, formulários dinâmicos, parceiros, financeiro).
- **Stack:** Django 4.1.13, Python 3.x, SQLite (dev). Frontend server-rendered (templates Django + CSS/JS por tela). OCR de passaporte via PaddleOCR/EasyOCR/PassportEye. Playwright para validação E2E.
- **Banco local é descartável** em dev. Migrações são regeneradas pelo fluxo `clear_migrations.py` (ver abaixo). Em produção isso muda — NÃO assumir descartabilidade fora do ambiente local do dev.
- **Idioma:** identificadores técnicos (models, fields, views, services, comandos, nomes de arquivo) em **inglês**. Rotas URL, labels, mensagens, `verbose_name` e texto visível ao usuário final em **pt-BR**. Respostas ao desenvolvedor em pt-BR.

---

## Layout real do repositório

**Raiz do Git = projeto Django:** `manage.py` na raiz, pacote de config `visary/`, app `system/` ao lado de `templates/` e `static/`.

```
Visary/                       # ⚠️ cwd de TODOS os comandos manage.py
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── requirements.txt
├── .env                      # local (fora do git); ver `.env.example`
├── manage.py
├── clear_migrations.py       # Reset destrutivo local (ver seção)
├── db.sqlite3                # Dev (fora do git)
├── visary/                   # Pacote de config Django (settings, urls, wsgi, asgi)
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── system/                   # App único com TODO o domínio
│   ├── models/
│   ├── views/
│   ├── forms/
│   ├── services/
│   ├── selectors/            # Consultas de leitura reutilizáveis
│   ├── utils/
│   ├── middleware.py
│   ├── management/commands/
│   ├── migrations/
│   ├── templatetags/dict_filters.py
│   ├── signals.py
│   ├── tests/
│   └── urls.py               # app_name="system"
├── templates/
├── static/
├── staticfiles/              # collectstatic (fora do git)
└── media/                    # uploads (fora do git)
```

**Fato importante:** todo o domínio vive em `system/`. Se precisar adicionar código de domínio, coloque em `system/` a menos que a tarefa diga o contrário.

---

## Comandos (PowerShell, Windows)

Execução manda que ver `AGENTS.md` (ExecutionPolicy, UTF-8, `.venv`, sem `&&`, sem `source`, sem scripts wrapper).

Todos os `manage.py` rodam com **cwd = raiz do repositório `Visary/`** (onde está `manage.py`):

```powershell
cd C:\Users\...\Visary
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
.\.venv\Scripts\python.exe manage.py makemigrations
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
.\.venv\Scripts\python.exe manage.py test --verbosity 2
.\.venv\Scripts\python.exe manage.py test system.tests.test_models
.\.venv\Scripts\python.exe manage.py test system.tests.test_services.FormStagesTests.test_progress
```

### Comandos de management do projeto (nomes REAIS, em inglês)

| Comando | Função |
|---|---|
| `create_admin_superuser` | Cria/atualiza superuser padrão (`admin` / `admin@admin.com` / `admin`). |
| `initial_seeds` | Executa todas as seeds abaixo na ordem correta. |
| `seed_modules` | Módulos funcionais do sistema (JSON em `static/modulos_ini/`). |
| `seed_profiles` | Perfis de permissão. |
| `seed_consultancy_users` | Usuários internos. Senhas vêm de `SYSTEM_SEED_USERS_PASSWORDS` no `.env`. |
| `seed_countries` | Países de destino. Aceita `--nome`. |
| `seed_visa_types` | Tipos de visto. Aceita `--nome`. |
| `seed_process_status` | Status de processo. Aceita `--nome`. |
| `seed_visa_forms` | Formulários dinâmicos. Aceita `--tipo-visto` ou `--arquivo`. |
| `seed_client_steps` | Etapas configuráveis de cadastro de cliente. Aceita `--nome`. |
| `seed_partners` | Parceiros indicadores. Senhas vêm de `SYSTEM_SEED_PARTNER_PASSWORDS`. Aceita `--email`. |
| `seed_legacy` | Marcadores legacy (ver `services/legacy_markers.py`). |

⚠️ **README.md** ainda cita nomes antigos em português (`criar_superuser_admin`, `seed_modulos`, etc.) — esses **NÃO existem mais**. A migração para inglês já aconteceu (commit `847a544`). Use os nomes da tabela acima.

### `clear_migrations.py` — reset destrutivo local

Script na **raiz do repo** (ao lado de `manage.py`). Executar com **cwd = raiz do projeto**:

```powershell
.\.venv\Scripts\python.exe clear_migrations.py
```

Em ordem aproximada: remove arquivos SQLite do projeto (`db.sqlite3` e variantes), `__pycache__/`, arquivos em `migrations/` exceto `__init__.py`, e artefatos locais (`staticfiles/`, `media/`, caches de teste, etc.). Em Windows, se o banco estiver bloqueado, tenta encerrar processos Python vinculados ao repositório (e em último caso outros processos Python).

**Só rode sob pedido explícito do usuário.** Fluxo típico depois:

```powershell
.\.venv\Scripts\python.exe clear_migrations.py
.\.venv\Scripts\python.exe manage.py makemigrations
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py create_admin_superuser
.\.venv\Scripts\python.exe manage.py initial_seeds
.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

---

## Arquitetura MTV aplicada ao `system`

### Camadas (reais, não prescritivas)

| Camada | Onde está | O que vai aqui |
|---|---|---|
| Domínio | `system/models/*.py` | Modelos split por área: `client_models`, `travel_models` (DestinationCountry, VisaType, Trip, TripClient), `process_models` (Process, ProcessStage, ProcessStatus, TripProcessStatus), `form_models` (VisaForm, VisaFormStage, FormQuestion, SelectOption, FormAnswer), `registration_step_models`, `partners_models`, `permission_models` (ConsultancyUser, Profile, Module), `financial_models`. `system/models/__init__.py` reexporta tudo. |
| Serviços | `system/services/` | `cep.py` (busca CEP com fallback ViaCEP → BrasilAPI → pycep-correios → brazilcep), `passport_ocr.py` (MRZ via PaddleOCR/EasyOCR/PassportEye), `form_prefill.py`, `form_responses.py`, `form_stages.py`, `legacy_markers.py`. Lógica de negócio vive aqui — views ficam finas. |
| Forms | `system/forms/` | Validação server-side. Services recebem dados já validados. |
| Views | `system/views/*.py` | Split por fluxo: `client_views`, `client_area_views`, `client_auth_views`, `travel_views`, `process_views`, `form_views`, `partners_views`, `partner_area_views`, `financial_views`, `admin_views`, `authentication_views`, `etapa_views`, `home_views`, `status_processo_views`. |
| URLs | `system/urls.py` | `app_name = "system"`. Rotas em pt-BR, nomes de view em inglês. |
| Templates | `templates/<fluxo>/` | Organizados por fluxo funcional (não 1:1 por app). Herdam `base.html`, usam `includes/_navbar.html`, `_footer.html`, `_messages.html`. |
| Static | `static/<namespace>/css|js|images/` | Namespaced. Seeds iniciais como JSON ficam em `static/*_ini/` (`forms_ini/`, `modulos_ini/`, `perfis_ini/`, `paises_destino_ini/`, `tipos_visto_ini/`, `status_processo_ini/`, `parceiros_ini/`, `etapas_cliente_ini/`, `usuarios_consultoria_ini/`, `formularios_visto_ini/`). |
| Signals | `system/signals.py` | Usar com parcimônia — regra central deve estar no serviço. |
| Testes | `system/tests/` | Split por camada (`test_models`, `test_services`, `test_views`, `test_forms`, etc.). |

### Conceitos centrais do domínio

- **ConsultancyUser** é a entidade de usuário interno — autenticação **própria** com senha hasheada, **não** usa `django.contrib.auth.User` para usuários da consultoria (só o admin Django o usa). Veja `permission_models.py`.
- **ConsultancyClient** tem senha própria para a "área do cliente". Dependentes são modelados como `ConsultancyClient` com FK para um "cliente principal".
- **Trip** tem N clientes via `TripClient` (M2M com principal marcável). Um **Process** é único por (Trip, Client) e calcula progresso a partir das `ProcessStage` (checklist) cujos templates vêm de `ProcessStatus` vinculáveis a `VisaType`.
- **VisaForm** é 1:1 com `VisaType`. Perguntas ordenadas (`FormQuestion`) com tipos configuráveis; respostas (`FormAnswer`) são persistidas por `(client, trip, question)`. Etapas do formulário ficam em `VisaFormStage`.
- **Permissões**: `Profile` agrupa flags CRUD (`can_create`, `can_view`, `can_update`, `can_delete`) e liga em `Module`s. Views validam permissão — nunca confiar em esconder botões.

### Rotas e APIs JSON

Todas sob namespace `system:` (ver `system/urls.py`). Endpoints JSON úteis para reutilizar ao invés de recriar:

- `api/buscar-cep/?cep=...` → `services.cep`
- `api/extrair-passaporte/` → `services.passport_ocr`
- `api/tipos-visto/?pais_id=...`
- `api/clientes-viagem/?viagem_id=...`
- `api/status-processo/?tipo_visto_id=...`
- `api/prazo-status-processo/?status_id=...`
- `api/cliente-info/?cliente_id=...`
- `api/dependentes-cliente/`, `api/viagens-cliente/`

Área do cliente: `cliente/dashboard/`, `cliente/viagem/<id>/formulario/`, `cliente/viagem/<id>/salvar-resposta/`.
Área do parceiro: `parceiro/dashboard/`, `parceiro/clientes/<id>/visualizar/`.

---

## Estado do `settings.py` (pós PRD-001)

`visary/settings.py` usa **`python-decouple`** com `RepositoryEnv(BASE_DIR / ".env")`, define `STATIC_ROOT`/`MEDIA_*`, `LOGIN_*` com namespace `system:`, e admin do projeto em **`/django-admin/`** (ver `visary/urls.py`). Variáveis principais: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, etc. (ver `.env.example`).

---

## Dependências

`requirements.txt` na raiz do repo: tratar como texto; se o arquivo estiver em **UTF-16** em algum clone, preserve o encoding ao editar. Destaques da stack além de Django:

- **OCR**: `paddleocr`, `paddlepaddle`, `paddlex`, `easyocr`, `PassportEye`, `pytesseract`, `rapidocr-onnxruntime`, `opencv-*`, `onnxruntime` — pesado, instalar só quando necessário.
- **CEP**: (o código usa ViaCEP/BrasilAPI via `requests` + libs `pycep-correios`, `brazilcep` se instaladas).
- **Banco alt.**: `psycopg2-binary`, `mysql-connector-python`, `PyMySQL`, `oracledb`, `sshtunnel`, `paramiko` — presentes para conectividade legada, não usados em dev.
- **Validação E2E**: `playwright==1.56.0`, `selenium`, `webdriver-manager`.
- **Testes**: `pytest`, `pytest-django`, `pytest-cov`, `coverage` (mas o fluxo padrão é `manage.py test`, não pytest — confirme antes de mudar).

Regra: nova lib → `.\.venv\Scripts\pip.exe install <pkg>` → `pip show` → **atualizar `requirements.txt`** (preservando UTF-16 se o arquivo continuar assim) → registrar no PRD.

---

## Checklist de validação (resumo — detalhes em `AGENTS.md` Fase 6)

1. `.venv` ativa, UTF-8, dependências sincronizadas.
2. `manage.py test --verbosity 2` → 0 falhas, 0 erros.
3. `manage.py showmigrations` limpo; shell check se tocou em modelo.
4. `collectstatic --noinput` (só quando `STATIC_ROOT` existir) + `findstatic` + sem 404 no browser.
5. Playwright/headless para fluxos com UI — screenshot e console limpo.
6. Sem stack trace no runserver.
7. CSRF presente, validação server-side, sem credenciais hardcodadas introduzidas por você.

---

## Critérios de falha (além dos de `AGENTS.md`)

- Criar código de domínio fora de `system/` sem decisão explícita.
- Usar nomes antigos de comando em português (`criar_superuser_admin`, `seed_modulos`, etc.).
- Rodar `clear_migrations.py` sem pedido explícito.
- Editar `requirements.txt` sem preservar o encoding do arquivo quando for UTF-16.
- Assumir que `README.md` é fonte de verdade sobre comandos — o código é.

---

### Changelog da spec

```md
- [2026-04-12] Reescrito /init para refletir estado real: app único `system`, comandos em inglês, divergências conhecidas em settings.py, encoding UTF-16 de requirements.txt.
- [2026-04-12] Layout raiz = Django; settings via decouple; STATIC_ROOT/MEDIA; `django-admin/`, rotas sem prefixo `/system/`; middleware e selectors.
- [2026-04-12] `clear_migrations.py` substitui `cleanup.py`; sem dependência de psutil para esse fluxo.
```
