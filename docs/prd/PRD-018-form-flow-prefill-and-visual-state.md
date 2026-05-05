# PRD-018: Fluxo de formulários, pré-preenchimento e estado visual

## Resumo do que será implementado
Corrigir a sequência das perguntas dos formulários de visto a partir da matriz legada já mapeada no PRD-017, remover a dependência artificial de pré-preenchimento apenas na primeira etapa e garantir que campos restaurados/preenchidos disparem os gatilhos de coloração e visibilidade.

## Tipo de demanda
Correção pontual com refatoração de fluxo e UI.

## Problema atual
Perguntas diretas do cliente foram deslocadas para a etapa 1 para viabilizar pré-preenchimento, o que aproximou o dado inicial, mas distanciou a sequência do legado. Além disso, rascunhos restaurados no formulário do cliente eram aplicados sem disparar eventos `input/change`, deixando coloração e condicionais desatualizadas.

Em 05/05/2026 foi confirmado um incidente adicional: o seed sincronizava `FormQuestion` por `(form, order)`. Ao renumerar perguntas, respostas existentes em `FormAnswer` permaneceram ligadas ao mesmo `question_id`, mas esse `question_id` passou a representar outra pergunta. Resultado observado no banco local: endereço aparecendo em `Telefone Primário`, bairro em `Telefone Secundário` e CPF em `Estado`.

## Objetivo
Manter a etapa da pergunta alinhada ao legado e fazer o pré-preenchimento funcionar em qualquer etapa, sem preencher dados de terceiros. Ao restaurar valores no navegador, o estado visual deve ser recalculado.

## Context Ledger
### Arquivos lidos integralmente
- `CLAUDE.md`
- `docs/prd/PRD-017-curadoria-formularios-legado.md`
- `static/forms_ini/*.json`
- `static/etapas_cliente_ini/ETAPAS_CADASTRO_CLIENTE.json`
- `system/models/form_models.py`
- `system/models/client_models.py`
- `system/models/registration_step_models.py`
- `system/services/form_prefill.py`
- `system/services/form_prefill_rules.py`
- `system/services/form_responses.py`
- `system/services/form_stages.py`
- `system/views/client_area_views.py`
- `system/views/client_views.py`
- `system/forms/client_forms.py`
- `templates/client_area/view_form.html`
- `templates/client/register_client.html`
- `static/system/js/client_register_draft.js`
- `system/tests/test_form_prefill.py`
- `system/tests/test_form_flow_curation.py`
- `C:/Users/whsf/Documents/GitHub/visary-front/src/pages/Processos/FichaCadastral/index.tsx`
- `C:/Users/whsf/Documents/GitHub/visary-front/src/pages/Processos/Formularios/FormulariosEua/index.tsx`
- `C:/Users/whsf/Documents/GitHub/visary-front/src/pages/Processos/Formularios/FormulariosEua/DadosPessoais/index.tsx`
- `C:/Users/whsf/Documents/GitHub/visary-front/src/pages/Processos/Formularios/FormulariosEua/Passaporte/index.tsx`
- `C:/Users/whsf/Documents/GitHub/visary-front/src/pages/Processos/Formularios/FormulariosEua/DadosContatoBrasil/index.tsx`
- `C:/Users/whsf/Documents/GitHub/visary-front/src/pages/Clientes/Form/index.tsx`
- `C:/Users/whsf/Documents/GitHub/visary-front/src/pages/Clientes/DadosPessoais/index.tsx`

### Arquivos adjacentes consultados
- `system/management/commands/seed_visa_forms.py`
- `system/tests/test_client_area_dashboard.py`
- `system/tests/test_trip_form_replication.py`

### Internet / documentação oficial
- Não aplicável. A fonte de verdade é o legado local e o PRD-017.

### MCPs / ferramentas verificadas
- PowerShell — OK — leitura, seed e testes.
- `.venv` Python/Django — OK — `manage.py check`, `manage.py test`.
- Node REPL — OK — revisão mecânica dos JSON.
- Browser Use — skill carregada; validação visual ainda pendente neste PRD até servidor local.
- `rg` — indisponível por acesso negado; mitigado com `git ls-files`, PowerShell e Node.

### Limitações encontradas
- `CLAUDE.md` permanece genérico e desalinhado com a realidade do projeto.
- A curadoria pergunta-a-pergunta completa ainda depende de revisão humana do PRD-017.

## Prompt de execução
### Persona
Agente de desenvolvimento especialista em Django seguindo SDD + TDD + MVT.

### Ação
Corrigir seeds, pré-preenchimento e estado visual dos formulários do cliente.

### Contexto
O legado determina a ordem operacional das etapas. O Django novo usa formulários dinâmicos e deve preservar essa arquitetura.

### Restrições
- sem migrações;
- sem hardcode de etapas em Python;
- sem preencher dados de terceiros;
- sem mascarar erro;
- validação técnica e visual obrigatória.

### Critérios de aceite
- [x] O pré-preenchimento funciona para perguntas diretas do cliente em qualquer etapa.
- [x] Perguntas de terceiros continuam bloqueadas no pré-preenchimento.
- [x] B1/B2 inicia com Nome, Sobrenome, Nomes Anteriores, E-mail, outros e-mails, Sexo e rede social.
- [x] Campos restaurados por rascunho disparam eventos para recalcular coloração e condicionais.
- [x] `seed_visa_forms` importa todos os JSON sem erro.
- [x] O seed preserva a identidade da pergunta por texto normalizado antes de alterar ordem.
- [x] O pré-preenchimento repara respostas diretas deslocadas e remove respostas stale que contêm valores do cadastro em perguntas sem mapeamento direto.

### Evidências esperadas
- testes passando;
- `manage.py check` sem issues;
- seed executado sem erro;
- validação visual com console limpo.

### Formato de saída
Código + seeds revisados + testes + evidências.

## Escopo
Formulários dinâmicos de visto, pré-preenchimento, template da área do cliente e testes relacionados.

## Fora do escopo
Migrações, redesign amplo, execução completa do legado e reescrita humana integral de todas as perguntas.

## Arquivos impactados
- `static/forms_ini/*.json`
- `system/services/form_prefill.py`
- `system/management/commands/seed_visa_forms.py`
- `system/tests/test_form_prefill.py`
- `system/tests/test_form_flow_curation.py`
- `templates/client_area/view_form.html`

## Riscos e edge cases
- Renumerar perguntas exige atualizar `regra_exibicao.pergunta_ordem`.
- Perguntas com texto genérico como `CEP` podem representar endereço residencial, escola ou contato.
- Respostas antigas podem permanecer ligadas a perguntas antigas se o banco já tiver dados reais.
- A limpeza do banco local com respostas já corrompidas remove respostas stale; por política de confirmação, a execução local deve ser confirmada pelo usuário antes de alterar `db.sqlite3`.

## Regras e restrições
- SDD antes de código.
- TDD para implementação.
- Sem migrações.
- Sem hardcode.
- Validação obrigatória.

## Plano
- [x] 1. Contexto e leitura integral
- [x] 2. Contratos e modelagem
- [x] 3. Testes (Red)
- [x] 4. Implementação (Green)
- [x] 5. Refatoração (Refactor)
- [x] 6. Validação completa
- [x] 7. Limpeza final
- [x] 8. Atualização documental

## Validação visual
### Desktop
Executada em `http://127.0.0.1:8000/cliente/viagem/<trip>/formulario/?client_id=<client>` com sessão local de cliente. Resultado: status 200, título do B1/B2, etapa `Etapa 1 de 24: Dados Pessoais`, 13 campos com estado visual preenchido, `bad_rules=0`, console sem erros. Evidência: `docs/prd/PRD-018-client-form-desktop.png`.

### Mobile
Executada com viewport 390x844. Resultado: status 200, etapa `Etapa 1 de 24: Dados Pessoais`, 13 campos preenchidos, `bad_rules=0`, console sem erros. Evidência: `docs/prd/PRD-018-client-form-mobile.png`.

### Console do navegador
Desktop e mobile sem erros JS críticos.

### Terminal
Sem stack trace nos comandos executados até o momento.

## Validação ORM
### Banco
`seed_visa_forms` executado no banco local.

### Shell checks
Shell ORM confirmou B1/B2 com 117 perguntas ativas, 24 etapas ativas e início da etapa 1 em `Nome`, `Sobrenome`, `Nomes Anteriores`, `E-mail`, outros e-mails e `Sexo`.

### Integridade do fluxo
JSON importados pelo seed sem erro.

## Validação de qualidade
### Sem hardcode
Aprovado: pré-preenchimento usa regras de texto existentes.

### Sem estruturas condicionais quebradiças
Aprovado parcialmente: rascunho agora dispara eventos; curadoria completa ainda exige revisão.

### Sem `except: pass`
Não introduzido.

### Sem mascaramento de erro
Não introduzido.

### Sem comentários e docstrings desnecessários
Não introduzido.

## Evidências
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_form_flow_curation system.tests.test_form_prefill --verbosity 2` -> 11 testes, 0 falhas, 0 erros.
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2` -> 78 testes, 0 falhas, 0 erros.
- `.\.venv\Scripts\python.exe manage.py check` -> `System check identified no issues (0 silenced).`
- `.\.venv\Scripts\python.exe manage.py seed_visa_forms` -> seed concluído.
- `.\.venv\Scripts\python.exe manage.py showmigrations system` -> `[X] 0001_initial`.
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput` -> 186 arquivos copiados.
- Shell ORM B1/B2 -> primeiros campos: `Nome`, `Sobrenome`, `Nomes Anteriores`, `E-mail`, outros e-mails, `Sexo`; 117 perguntas e 24 etapas.
- Playwright desktop/mobile -> status 200, `bad_rules=0`, 13 campos com `.is-filled`, console sem erros.

## Implementado
- Pré-preenchimento deixou de ser limitado à etapa 1.
- Teste de pré-preenchimento atualizado para cobrir campos diretos em etapa posterior.
- Seeds JSON foram reorganizados por etapa e renumerados mantendo `display_rule`.
- Restauração de rascunho no formulário do cliente passou a disparar `input/change`.
- Teste de B1/B2 agora verifica a sequência inicial mais próxima do legado.
- `seed_visa_forms` deixou de identificar pergunta apenas por ordem e passou a preservar `question_id` por texto normalizado.
- O pré-preenchimento passou a reconciliar respostas existentes de campos diretos do cliente, corrigindo deslocamentos como telefone preenchido com endereço.

## Desvios do plano
- A correção de `CLAUDE.md` foi mantida como pendência para não misturar governança com fluxo funcional.

## Pendências
- Executar limpeza confirmada no banco local para remover respostas stale já persistidas no `db.sqlite3`.
- Revisão humana fina das perguntas genéricas de cada formulário.

## Status final verdadeiro
Concluída com limitações até a confirmação de limpeza do banco local.
