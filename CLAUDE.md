# Visary – Contexto para Claude

Sistema de gestão de consultoria de vistos (Django). O Agent deve seguir as especificações abaixo, alinhadas às regras em `.cursor/rules/`.

## Código

- Não gerar código com comentários nem docstrings (Python, JS, TS, HTML, CSS). Código autoexplicativo; nomes de variáveis, funções e classes devem transmitir a intenção.

## Antes de responder

- Buscar na internet para atualizar informações (APIs, versões, boas práticas) e melhorar o contexto da resposta. Priorizar fontes oficiais (docs, repositórios).

## Documentação (Context7)

- Backend/modelos: consultar MCP Context7 para **Django** (views, models, ORM, migrations, settings).
- Templates/frontend: consultar **HTML**, **CSS** e **JavaScript** no Context7.
- Dados: consultar **ORM do Django** e, quando aplicável, **SQLite3** e **PostgreSQL**. Usar resolve-library-id e query-docs antes de implementar.

## Validação ao finalizar

1. **IDE**: Rodar lints nos arquivos alterados e corrigir problemas.
2. **Django ORM**: Confirmar via ORM que dados e modelagem estão corretos.
3. **Postgres MCP**: Gerar e executar SQL de verificação (consultas, integridade, modelagem) quando o projeto usar Postgres.
4. **Playwright MCP**: Validar a interface no browser (informações corretas, fluxos principais).

Considerar resposta finalizada só após essas validações quando forem aplicáveis.

## Migrations e fluxo de ambiente

- Não gerar nem editar arquivos de migrations manualmente (incluindo `0001_initial.py`). Corrigir models/views e depois recriar migrations.
- Fluxo após alterações que afetem models ou ambiente:
  1. `clear` (ou equivalente no shell)
  2. `python cleanup.py`
  3. `python manage.py makemigrations`
  4. `python manage.py migrate`
  5. `python manage.py criar_superuser_admin`
  6. `python manage.py runserver 8000`
- Validar logs do terminal (runserver sem erros). `cleanup.py` em `visary/cleanup.py`; `manage.py` em `visary/manage.py`.

## Projeto

- **Stack**: Django 5.2.8, Python 3.x, SQLite (dev), HTML/CSS/JavaScript. Opcional: PostgreSQL.
- **Módulos**: Clientes (cadastro em etapas, área do cliente), Viagens (países, tipos de visto), Processos de visto, Formulários dinâmicos, Parceiros, Financeiro, Relatórios, Usuários.
- **Permissões**: perfis Atendente e Administrador; seeds em `.env_exemple` (SYSTEM_SEED_*, CONSULTANCY_SEED_*).

CLAUDE.md é gerado a partir deste arquivo; use `python scripts/sync_claude_from_agents.py` manualmente ou ative o hook em `.githooks/pre-commit` para atualizar ao commitar.
