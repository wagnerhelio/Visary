# PRD-001: Layout do repositório Visary (raiz Django)

## Resumo

Achatar o repositório para `manage.py` na raiz do Git, alinhar settings (decouple, STATIC_ROOT/MEDIA), URLs (`django-admin/`, rotas sem prefixo `/system/`), middleware e pacotes `selectors`/`utils`, script de reset local e documentação.

## Problema atual

(Snapshot histórico.) Segundo nível extra para Django; URLs do app sob `/system/`; settings sem `STATIC_ROOT`/`MEDIA`; secrets hardcoded.

## Objetivo

Repositório com raiz = projeto Django, preservando `dict_filters` e domínio Visary.

## Variáveis de ambiente (.env)

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS` (lista separada por vírgula)
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DJANGO_EMAIL_BACKEND`, `DJANGO_DEFAULT_FROM_EMAIL`
- `ADMIN_SUPERUSER_USERNAME`, `ADMIN_SUPERUSER_EMAIL`, `ADMIN_SUPERUSER_PASSWORD` (seeds/comandos existentes)
- `SYSTEM_SEED_USERS_PASSWORDS`, `SYSTEM_SEED_PARTNER_PASSWORDS` (já usados pelo domínio)

## Critérios de aceite

- [x] `manage.py` na raiz do repo; pacote `visary/` contém só config Django.
- [x] `manage.py check` sem erros.
- [x] `manage.py test --verbosity 2` — 0 falhas.
- [x] `collectstatic --noinput` conclui com `STATIC_ROOT` definido.
- [x] Rotas do app na raiz (ex.: `/clientes/`, não `/system/clientes/`).
- [x] Admin em `/django-admin/`; login em namespace `system:`.
- [x] `clear_migrations.py` na raiz ao lado de `manage.py`.

## Riscos

Bookmarks e links com `/system/` quebram; testes com URLs literais; usuários acostumados com `/admin/`.

## Implementado

- Repositório achatado; `visary/` apenas pacote de config; `clear_migrations.py` para reset local (substitui o antigo `cleanup.py`).
- `python-decouple`, `STATIC_ROOT`/`MEDIA_*`, URLs e middleware, selectors/utils, testes e docs atualizados.

## Desvios

- `AGENTS.md` sem mudanças de caminho.
- Critérios de falha em `CLAUDE.md` sobre settings foram atualizados porque o PRD tinha settings como alvo.
