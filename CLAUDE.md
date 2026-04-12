# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Protocolo de execução (fases, PRD, TDD): ver `AGENTS.md`. Este arquivo é o contexto **deste** projeto.

---

## Perfil do projeto

- **Produto:** Visary — sistema web de gestão de consultoria de vistos (clientes, viagens, processos, formulários dinâmicos, parceiros, financeiro).
- **Stack:** Django 4.1.13, Python 3.x, SQLite (dev). Frontend server-rendered (templates Django + CSS/JS por tela). OCR de passaporte via PaddleOCR/EasyOCR/PassportEye. Playwright para validação E2E.
- **Banco local é descartável** em dev. Migrações são regeneradas pelo fluxo `cleanup.py` (ver abaixo). Em produção isso muda — NÃO assumir descartabilidade fora do ambiente local do dev.
- **Idioma:** identificadores técnicos (models, fields, views, services, comandos, nomes de arquivo) em **inglês**. Rotas URL, labels, mensagens, `verbose_name` e texto visível ao usuário final em **pt-BR**. Respostas ao desenvolvedor em pt-BR.

---

## Layout real do repositório

```
Visary/
├── AGENTS.md                 # Protocolo universal (fases obrigatórias)
├── CLAUDE.md                 # Este arquivo
├── README.md                 # Visão funcional (pode estar defasado em versões)
├── requirements.txt
└── visary/                   # ⚠️ cwd de TODOS os comandos manage.py
    ├── manage.py
    ├── cleanup.py            # Script destrutivo local (ver seção)
    ├── db.sqlite3            # Dev (fora do git)
    ├── visary/               # Project config (settings.py, urls.py)
    ├── system/               # App único com TODO o domínio
    │   ├── models/           # Split por área (client, travel, process, form, ...)
    │   ├── views/            # Split por fluxo (client_views, travel_views, form_views, ...)
    │   ├── forms/
    │   ├── services/         # cep, passport_ocr, form_prefill, form_responses, form_stages, legacy_markers
    │   ├── management/commands/  # Seeds + create_admin_superuser + initial_seeds
    │   ├── migrations/
    │   ├── templatetags/dict_filters.py
    │   ├── signals.py
    │   ├── tests/
    │   └── urls.py           # app_name="system"
    ├── consultancy/          # ⚠️ App esqueleto, ATUALMENTE VAZIO (models/views/services/forms todos sem arquivos). Não está em INSTALLED_APPS.
    ├── templates/            # base.html + includes/ + pastas por fluxo (client/, travel/, process/, forms/, partners/, ...)
    └── static/               # base + <namespace>/css/|js/|images/ e ...ini/ JSONs de seed
```

**Fato importante:** todo o domínio vive em `system/`. `consultancy/` é um app planejado mas não implementado — NÃO criar modelos/views ali sem decisão explícita do usuário. Se precisar adicionar código de domínio, coloque em `system/` a menos que a tarefa diga o contrário.

---

## Comandos (PowerShell, Windows)

Execução manda que ver `AGENTS.md` (ExecutionPolicy, UTF-8, `.venv`, sem `&&`, sem `source`, sem scripts wrapper).

Todos os `manage.py` rodam com **cwd = `visary/`**:

```powershell
cd visary
..\.venv\Scripts\Activate.ps1             # ou .\.venv\Scripts\Activate.ps1 da raiz
..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
..\.venv\Scripts\python.exe manage.py makemigrations
..\.venv\Scripts\python.exe manage.py migrate
..\.venv\Scripts\python.exe manage.py collectstatic --noinput
..\.venv\Scripts\python.exe manage.py test --verbosity 2
..\.venv\Scripts\python.exe manage.py test system.tests.test_models        # um módulo
..\.venv\Scripts\python.exe manage.py test system.tests.test_services.FormStagesTests.test_progress  # um teste
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

### `cleanup.py` — reset destrutivo local

`visary/cleanup.py` (executado com `.\.venv\Scripts\python.exe cleanup.py` a partir de `visary/`) faz, nesta ordem:

1. Remove todos os `__pycache__/` recursivamente.
2. Apaga **todos os arquivos de migration** (exceto `__init__.py`) em qualquer pasta `migrations/`.
3. Tenta matar processos que seguram `db.sqlite3` (via `psutil`) e deleta o arquivo.

Há também um stripper de comentários/docstrings embutido no módulo (`strip_comments_and_docstrings`) usado por outras rotinas — **não é chamado** por `clean()` / `main()`. `main()` só roda o passo destrutivo simples.

**Só rode `cleanup.py` sob pedido explícito do usuário.** Depois dele, o fluxo típico é:

```powershell
.\.venv\Scripts\python.exe cleanup.py
..\.venv\Scripts\python.exe manage.py makemigrations
..\.venv\Scripts\python.exe manage.py migrate
..\.venv\Scripts\python.exe manage.py create_admin_superuser
..\.venv\Scripts\python.exe manage.py initial_seeds
..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
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
- **Permissões**: `Profile` agrupa flags CRUD (`pode_criar`, `pode_visualizar`, `pode_atualizar`, `pode_excluir`) e liga em `Module`s. Views validam permissão — nunca confiar em esconder botões.

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

## Estado conhecido do `settings.py` (⚠️ divergências)

`visary/visary/settings.py` hoje tem:

- `SECRET_KEY` **hardcoded** + `DEBUG = True` + `ALLOWED_HOSTS = ['*']`. `load_dotenv()` é chamado mas os valores não são lidos via `decouple`/`environ`.
- Sem `STATIC_ROOT` definido (só `STATIC_URL` e `STATICFILES_DIRS`). `collectstatic` **vai falhar** até isso ser corrigido.
- Sem `MEDIA_URL`/`MEDIA_ROOT` mesmo com upload de passaporte/OCR em uso.
- `INSTALLED_APPS` tem apenas `system` — `consultancy` não está registrado.
- `CSRF_TRUSTED_ORIGINS` inclui um domínio ngrok específico.

Essas são dívidas conhecidas. **Não "corrija" como efeito colateral** de outra tarefa — tratar explicitamente via PRD quando for o alvo. Seguir as regras de `AGENTS.md` (ler `.env`, não hardcodar) ao tocar no settings.

---

## Dependências

`requirements.txt` na raiz do repo está codificado em **UTF-16** (não UTF-8 puro). Ao ler/editar, preservar encoding. Destaques da stack além de Django:

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

- Criar código de domínio em `consultancy/` sem decisão explícita.
- Usar nomes antigos de comando em português (`criar_superuser_admin`, `seed_modulos`, etc.).
- Rodar `cleanup.py` sem pedido explícito.
- Editar `requirements.txt` sem preservar o encoding UTF-16 atual.
- "Consertar" `settings.py` como efeito colateral de outra tarefa.
- Assumir que `README.md` é fonte de verdade sobre comandos — o código é.

---

### Changelog da spec

```md
- [2026-04-12] Reescrito /init para refletir estado real: app único `system`, comandos em inglês, cleanup.py destrutivo, divergências conhecidas em settings.py, encoding UTF-16 de requirements.txt.
```
