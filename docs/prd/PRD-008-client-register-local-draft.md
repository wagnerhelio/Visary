# PRD-008: Rascunho local no cadastro de cliente
## Resumo
Adicionar persistencia local no navegador para o cadastro de cliente, inspirada no fluxo de rascunho do `lvjiujitsu`, para suportar perda de conexao ou redes ruins antes do envio da etapa ao servidor.

## Problema atual
O Visary ja salva os dados no backend quando o usuario avanca uma etapa, mas os campos digitados na etapa atual podem ser perdidos se a conexao cair, a aba recarregar ou o usuario sair antes do POST concluir.

## Objetivo
Salvar automaticamente um rascunho local dos campos preenchidos no cadastro de cliente e restaurar esses valores quando o usuario voltar para o formulario.

## Contexto consultado
  - Context7: nao disponivel neste ambiente.
  - Web: nao consultada; o comportamento foi comparado localmente com `C:\Users\whsf\Documents\GitHub\lvjiujitsu`.
  - `lvjiujitsu`: usa `localStorage`, indicador "Rascunho salvo", TTL e exclusao de campos sensiveis como senha/CSRF.

## Dependencias adicionadas
  - nenhuma.

## Escopo / Fora do escopo
Escopo: cadastro principal de cliente, rascunho local no navegador, indicador visual, botao de limpar rascunho e limpeza apos concluir/cancelar.

Fora do escopo: persistencia em nova tabela de banco, autosave via AJAX, upload offline de arquivos e alteracoes no fluxo de dependentes.

## Arquivos impactados
  - `templates/client/register_client.html`
  - `templates/client/home_clients.html`
  - `static/system/css/client_register_wizard.css`
  - `static/system/js/client_register_draft.js`
  - `system/views/client_views.py`
  - `system/tests/test_client_register_draft.py`
  - `docs/prd/PRD-008-client-register-local-draft.md`

## Riscos e edge cases
  - Rascunho local guarda dados pessoais no navegador; por seguranca, senha, CSRF e arquivos nao devem ser salvos.
  - O rascunho nao deve sobrescrever valores ja preenchidos pelo servidor/sessao.
  - Ao concluir ou cancelar, o rascunho deve ser removido para evitar restaurar dados antigos.

## Regras e restricoes
  - Sem dependencia nova.
  - Sem credenciais hardcoded.
  - Validacao server-side permanece obrigatoria.
  - Persistencia local e melhoria de UX; o backend continua sendo a fonte de verdade.

## Criterios de aceite
  - [x] O formulario principal de cadastro expoe atributos de rascunho e carrega o JS namespaced.
  - [x] O JS salva campos em `localStorage` com TTL e ignora senha, CSRF, arquivo e botao de acao.
  - [x] O JS restaura somente campos vazios, sem sobrescrever dados ja renderizados pelo servidor.
  - [x] Ha indicador "Rascunho salvo" com opcao de limpar.
  - [x] A tela de clientes limpa o rascunho apos cadastro concluido/cancelado.

## Plano
  - [x] 1. Adicionar testes de regressao para markup e limpeza de rascunho.
  - [x] 2. Criar JS namespaced de rascunho local.
  - [x] 3. Integrar template de cadastro e CSS do indicador.
  - [x] 4. Marcar limpeza no backend apos concluir/cancelar e executar no destino.
  - [x] 5. Validar com testes, collectstatic e Playwright.

## Comandos de validacao
  - `.\.venv\Scripts\python.exe manage.py test system.tests.test_client_register_draft --verbosity 2`
  - `.\.venv\Scripts\python.exe manage.py check`
  - `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`
  - `.\.venv\Scripts\python.exe manage.py test --verbosity 2`

## Implementado
- `static/system/js/client_register_draft.js`: autosave local em `localStorage`, TTL de 7 dias, restauracao de campos vazios, exclusao de senha/CSRF/arquivos/acoes e botao de limpar.
- `templates/client/register_client.html`: indicador "Rascunho salvo", atributos `data-client-draft-*` no formulario principal e carregamento do JS namespaced.
- `static/system/css/client_register_wizard.css`: estilos do indicador de rascunho e estado restaurado.
- `system/views/client_views.py`: marca `clear_client_register_draft` na sessao ao concluir/cancelar cadastro e expõe o marcador na home de clientes.
- `templates/client/home_clients.html`: remove o rascunho local quando recebe o marcador de limpeza.
- `system/tests/test_client_register_draft.py`: regressao de markup do rascunho e limpeza apos flag de sessao.

Evidencias:
- Red: `system.tests.test_client_register_draft` falhou antes da implementacao por ausencia de markup/limpeza.
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_client_register_draft --verbosity 2` => 2 testes OK.
- `.\.venv\Scripts\python.exe manage.py check` => sem issues.
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput` => 2 estaticos copiados, 182 inalterados, sem erro.
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2` => 41 testes OK.
- `.\.venv\Scripts\python.exe manage.py findstatic system/js/client_register_draft.js` => encontrado.
- `.\.venv\Scripts\python.exe manage.py findstatic system/css/client_register_wizard.css` => encontrado.
- `.\.venv\Scripts\python.exe manage.py showmigrations` => migrations aplicadas.
- Playwright mobile em `/clientes/cadastrar/`: campo `first_name` restaurou apos reload, `localStorage` contem rascunho, senha literal nao foi persistida, `app_console_errors []`, `request_failures []`.
- Screenshot: `docs/prd/PRD-008-client-register-draft-mobile.png`.

## Desvios do plano
Nenhum.
