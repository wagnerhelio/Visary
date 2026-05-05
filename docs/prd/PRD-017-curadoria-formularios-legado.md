# PRD-017: Curadoria dos formulários legado vs novo

## Resumo do que será implementado

Reconciliar o cadastro de cliente e os formulários de visto do sistema novo com o comportamento do legado, usando o legado como matriz de sequência, perguntas e condicionais, mas preservando melhorias do novo cenário Django: formulário dinâmico, cadastro por etapas, dependentes, pré-preenchimento por dados do cliente, CPF como identificador e vínculo por viagem.

A versão inicial deste PRD registrou o diagnóstico, o de/para e a especificação. Em 25/04/2026 foi implementado o primeiro recorte funcional: etapas canônicas nos seeds JSON, remoção do `STAGES_MAP`, correção das regras condicionais cross-stage, serialização segura de `display_rule` e contagem de preenchimento baseada em perguntas visíveis com resposta real.

## Tipo de demanda

Diagnóstico de erro + regeneração documental + refatoração planejada de fluxo de formulário.

## Problema atual

O sistema novo está tecnicamente mais estruturado, mas os seeds atuais em `static/etapas_cliente_ini` e `static/forms_ini` não reproduzem com fidelidade o fluxo legado. Há divergências em:

- sequência das etapas;
- agrupamento das perguntas;
- perguntas existentes no legado que foram reagrupadas, omitidas ou reescritas;
- perguntas novas que aparecem antes do momento correto;
- condicionais ausentes, quebradas ou dependentes de etapas anteriores;
- perguntas marcadas como obrigatórias sem considerar se estão visíveis;
- comportamento de conclusão contando perguntas ocultas ou vazias;
- fonte de verdade duplicada entre JSON e `STAGES_MAP` hardcoded em Python.

## Objetivo

Criar uma matriz canônica de cadastro e formulários que:

- mantenha a ordem e a lógica de perguntas do legado onde elas estavam corretas;
- adapte os textos ao novo cenário sem alterar a intenção original;
- represente explicitamente condicionais, saltos e grupos repetidos;
- elimine divergência entre etapa, pergunta e comportamento real;
- permita validação automatizada e visual antes da troca dos seeds em produção.

## Context Ledger

### Arquivos lidos integralmente

- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `static/etapas_cliente_ini/ETAPAS_CADASTRO_CLIENTE.json`
- `static/forms_ini/FORMULARIO_AUSTRALIA_ESTUDANTE.json`
- `static/forms_ini/FORMULARIO_AUSTRALIA_VISITANTE.json`
- `static/forms_ini/FORMULARIO_CANADA_ESTUDANTE.json`
- `static/forms_ini/FORMULARIO_CANADA_TRV.json`
- `static/forms_ini/FORMULARIO_EUA_B1_B2.json`
- `static/forms_ini/FORMULARIO_EUA_F1.json`
- `static/forms_ini/FORMULARIO_EUA_J1.json`
- `system/management/commands/seed_client_steps.py`
- `system/management/commands/seed_visa_forms.py`
- `system/models/registration_step_models.py`
- `system/models/form_models.py`
- `system/models/client_models.py`
- `system/forms/client_forms.py`
- `system/forms/form_forms.py`
- `system/forms/registration_step_forms.py`
- `system/services/form_responses.py`
- `system/services/form_stages.py`
- `system/services/form_prefill.py`
- `system/services/form_prefill_rules.py`
- `system/views/client_views.py`
- `system/views/form_views.py`
- `system/views/travel_views.py`
- `system/views/client_area_views.py`
- `templates/client/register_client.html`
- `templates/client/register_dependent.html`
- `templates/travel/edit_client_form.html`
- `templates/travel/view_client_form.html`
- `templates/client_area/view_form.html`
- `static/system/js/client_register_draft.js`
- `C:/Users/whsf/Documents/GitHub/visary-front/src/pages/Clientes/Form/index.tsx`
- `C:/Users/whsf/Documents/GitHub/visary-front/src/pages/Clientes/DadosPessoais/index.tsx`
- `C:/Users/whsf/Documents/GitHub/visary-front/src/pages/Clientes/DadosViagem/index.tsx`
- `C:/Users/whsf/Documents/GitHub/visary-front/src/pages/Processos/FichaCadastral/index.tsx`
- Todos os `index.tsx` de `visary-front/src/pages/Processos/Formularios/FormulariosEua/*`
- Todos os `index.tsx` de `visary-front/src/pages/Processos/Formularios/FormulariosCa/*`
- Todos os `index.tsx` de `visary-front/src/pages/Processos/Formularios/FormulariosAusVisitante/*`
- Todos os `index.tsx` de `visary-front/src/pages/Processos/Formularios/FormularioAusEstudante/*`
- `C:/Users/whsf/Documents/GitHub/visary-back/routes/api.php`
- `C:/Users/whsf/Documents/GitHub/visary-back/app/Http/Controllers/ClienteController.php`
- `C:/Users/whsf/Documents/GitHub/visary-back/app/Http/Requests/ClienteRequest.php`
- `C:/Users/whsf/Documents/GitHub/visary-back/app/Models/Cliente.php`
- Contratos legados de formulário em `visary-back/app/Http/Controllers`, `app/Http/Requests` e `app/Models` para Processo, Conjuge, Passaporte, Custeio, DadosViagemAnterior, DadosContatoPais, DadosDosPais, DadosParenteNoPais, Ocupacao, EmpregosAnteriores, InformacoesEducacionais, IdiomasExperiencias, PerguntaDeSeguranca, VistoAnterior, DadosEscola, ContatosAdicionais, PermissaoEstudo, InformacaoProfissional, DetalheEmpregaticiosEstudoAposentadoria, DetalhamentoEmpregosAnteriores, SaudeHistoricoImigracional, InformacoesFilhos, InformacoesAdicionaisViagem, DadosResponsaveis, DeclaracaoCaraterPessoal, DeclaracaoFinal, NivelIngles, DadosVistosAnteriores, FamiliaresBrasil, DadosFinanceiros e AssistenciaMedica.

### Arquivos adjacentes consultados

- `system/tests/test_form_prefill.py`
- `system/tests/test_client_area_dashboard.py`
- `system/tests/test_trip_form_replication.py`
- `system/tests/test_dependent_register_fields.py`
- `system/tests/test_client_register_draft.py`
- `docs/prd/PRD-014-form-prefill-trip-replication-ptbr.md`
- `docs/prd/PRD-016-client-form-prefill-member-ui-audit.md`

### Internet / documentação oficial

- Não aplicável nesta etapa. A demanda é reconciliação entre três bases locais já disponíveis.

### MCPs / ferramentas verificadas

- PowerShell — OK — leitura de arquivos, listagem e validação.
- `.venv` Python 3.12.10 — OK — `.\.venv\Scripts\python.exe --version`.
- Django management — OK — `manage.py --help` confirmou comandos reais.
- JSON parser — OK — todos os JSON de `forms_ini` e `etapas_cliente_ini` carregam sem erro.
- Test runner — OK — `manage.py test --verbosity 2`.
- `rg` — indisponível na sessão por acesso negado ao binário empacotado; mitigado com PowerShell e scripts de leitura integral.

### Limitações encontradas

- `CLAUDE.md` ainda está em formato de template com placeholders; isso é divergência de governança e deve ser corrigido em tarefa própria ou antes da implementação.
- Não executei os sistemas legados em browser/API; a análise do legado foi feita por leitura integral de código front/back.
- Não houve validação visual com Playwright nesta etapa porque nenhum código ou seed foi alterado.
- A extração de labels do legado é uma leitura estática; a implementação deve validar runtime para confirmar campos ocultos, defaults e saltos condicionais.

## Prompt de execução

### Persona

Agente de desenvolvimento especialista em Django + migração de sistemas legados seguindo SDD + TDD + MVT com services/selectors.

### Ação

Implementar a curadoria dos seeds e do motor de preenchimento dos formulários, trazendo a ordem, perguntas e condicionais do legado para o novo cenário Django.

### Contexto

O legado React/Laravel preservava a sequência operacional correta, mas era rígido: componentes específicos por seção, tabelas específicas por domínio e fluxo guiado por `setTelaNumero`. O novo sistema Django centraliza tudo em `VisaForm`, `VisaFormStage`, `FormQuestion`, `SelectOption` e `FormAnswer`, mas os seeds atuais não refletem fielmente o legado e o motor de condicionais tem falhas.

### Restrições

- sem migrações sem autorização explícita;
- sem hardcode de etapas em Python;
- sem mascaramento de erro;
- sem perder o pré-preenchimento a partir do cadastro do cliente;
- sem alterar a intenção das perguntas legadas sem registrar a decisão;
- leitura integral obrigatória antes de editar cada fluxo;
- validação obrigatória com testes e browser.

### Critérios de aceite

- [x] Cada formulário possui matriz de etapas derivada do legado e armazenada como fonte de verdade nos seeds, não em `STAGES_MAP`.
- [x] O cadastro do cliente preserva as melhorias do novo cenário, mas documenta quais campos foram movidos do formulário de visto para cadastro base.
- [ ] B1/B2, F1 e J1 deixam de compartilhar uma versão reduzida sem condicionais e passam a ter etapas/pulos compatíveis com o fluxo EUA legado.
- [ ] Canadá Study Permit e TRV refletem os saltos legados de cônjuge anterior, atividade dos últimos 10 anos, filhos e familiares.
- [x] Austrália Visitante volta a seguir as 10 etapas legadas, salvo decisões documentadas de expansão.
- [x] Austrália Estudante volta a seguir as 16 etapas legadas, salvo decisões documentadas de expansão.
- [x] Toda regra `display_rule` é JSON válido no HTML e funciona no browser.
- [x] Regras que dependem de perguntas de etapa anterior funcionam no frontend e no backend.
- [x] Perguntas ocultas não bloqueiam avanço e não distorcem status de conclusão.
- [x] Perguntas removidas do seed são desativadas ou tratadas explicitamente no processo de reseed.
- [ ] O admin consegue auditar/editar condicionais ou há documentação explícita de que condicionais só são editáveis por seed.

### Evidências esperadas

- `manage.py test --verbosity 2` com 0 falhas e 0 erros.
- `manage.py check` sem issues.
- `manage.py collectstatic --noinput` sem erros após alterações em estáticos/templates.
- Testes unitários para seed, condicionais e contagem de conclusão.
- Testes de template garantindo `data-rule` JSON válido.
- Validação Playwright para ao menos um fluxo de cadastro e um formulário com condicional por país/tipo de visto.
- Console do navegador sem erro JS crítico.

### Formato de saída

Código implementado + seeds revisados + testes + PRD atualizado com evidências.

## Escopo

- Cadastro inicial do cliente.
- Cadastro de dependentes/membros quando impacta sequência de campos.
- Formulários de visto EUA B1/B2, EUA F1, EUA J1.
- Formulários Canadá Study Permit e TRV.
- Formulários Austrália Visitante e Estudante.
- Motor de etapas, perguntas, opções, obrigatoriedade e condicionais.
- Status de preenchimento/conclusão.

## Fora do escopo

- Migração de schema sem autorização.
- Alteração de autenticação, permissões ou financeiro.
- Redesign visual amplo.
- Execução do legado em ambiente local.
- Mudança de regras consulares oficiais sem decisão humana.

## Arquivos impactados

Previstos para implementação:

- `static/etapas_cliente_ini/ETAPAS_CADASTRO_CLIENTE.json`
- `static/forms_ini/*.json`
- `system/management/commands/seed_visa_forms.py`
- `system/services/form_responses.py`
- `system/services/form_stages.py`
- `system/forms/form_forms.py`
- `templates/travel/edit_client_form.html`
- `templates/travel/view_client_form.html`
- `templates/client_area/view_form.html`
- testes em `system/tests/`

Possíveis, se necessário e autorizado:

- `system/models/form_models.py`
- `system/models/registration_step_models.py`

## De/Para do cadastro do cliente

| Tema | Legado | Novo atual | Diagnóstico |
|---|---|---|---|
| Estrutura | Duas abas: `Dados pessoais` e `Dados da viagem`. | Quatro etapas: `Dados Pessoais`, `Endereço`, `Dados do Passaporte`, `Adicionar Membros`. | Parcialmente correto. O novo é melhor para wizard e pré-preenchimento, mas diverge do legado e precisa ser assumido como decisão de produto, não acidente. |
| Nome | Campo único `Nome`, dividido no submit em nome/sobrenome. | Campos separados `nome` e `sobrenome`. | Melhor implementado no novo; reduz parsing frágil. |
| CPF | Não era obrigatório no POST inicial legado; aparecia em formulários e PUT. | Obrigatório no cadastro base. | Correto para novo cenário se CPF é login/identidade. Precisa ser decisão documentada. |
| E-mail | Obrigatório no POST legado e usado para criar `User`. | Opcional no seed atual. | Divergência relevante. Se CPF é login, OK; caso contrário, mal implementado. |
| Endereço | Dentro da aba de dados pessoais. | Etapa separada. | Melhor UX no novo, mas muda sequência. |
| Passaporte | Era preenchido dentro do formulário de visto. | Foi movido para etapa base do cliente. | Pode ser melhoria por pré-preenchimento, mas altera o momento da pergunta. Precisa de regra: passaporte base só deve capturar dados universais, não substituir perguntas consulares específicas. |
| Membros | Inline dentro de dados pessoais, máximo 10, cada membro com senha própria. | Etapa própria com dependentes, usar mesma conta/endereço do titular e OCR de passaporte. | Melhor implementado no novo, mas precisa preservar obrigatoriedade/ordem dos campos do legado. |
| Parceiro/indicação | Em `Dados da viagem`, condicionado por checkbox `indicado`. | `parceiro_indicador` aparece nos dados pessoais. | Divergência de domínio. Parceiro é dado da viagem/processo no legado; mover para cliente pode gerar indicação errada em múltiplas viagens. |
| Regra `tipo_passaporte_outro` | Legado mostrava `Outro qual?` quando tipo era outro. | Seed usa valor `outro`, mas form Django usa valor técnico `other`. | Mal implementado; condicional tende a não casar. |

## De/Para dos formulários de visto

| Formulário | Sequência legado | Sequência novo atual | Perguntas novo | Regras novo | Diagnóstico |
|---|---:|---:|---:|---:|---|
| EUA B1/B2 | Fluxo EUA com 24 etapas + conclusão, com saltos por estado civil, visto anterior, parentes, emprego anterior, educação, biometria, consulado e declaração. | 15 etapas. | 117 | 26 | Mal implementado. O novo comprime e reordena etapas; há perguntas de emprego/instituição marcadas em etapa 1 embora dependam de etapas 10/11. |
| EUA F1 | Mesmo motor EUA legado, com etapas de escola/custeio/contato conforme tipo F1. | 14 etapas. | 68 | 0 | Mal implementado. Perdeu condicionais e ficou reduzido demais em relação ao fluxo legado. |
| EUA J1 | Mesmo motor EUA legado, com etapas específicas de intercâmbio/escola/custeio. | 14 etapas. | 68 | 0 | Mal implementado. Está praticamente igual ao F1 e sem regras, apesar do legado usar comportamento condicional. |
| Canadá Study Permit | 16 etapas + conclusão. | 15 etapas. | 148 | 0 | Parcial, mas problemático. Reordena segurança para cedo, remove `Cônjuge Anterior` como etapa própria e não representa saltos legados. |
| Canadá TRV | 16 etapas + conclusão. | 17 etapas. | 143 | 1 | Parcial. Tem uma regra cross-stage e sequência diferente; precisa decidir se a etapa extra é desejada ou erro. |
| Austrália Visitante | 10 etapas + conclusão. | 19 etapas. | 135 | 11 | Mal implementado. O novo superfragmentou o formulário e não segue o ritmo do legado. |
| Austrália Estudante | 16 etapas + conclusão. | 23 etapas. | 162 | 19 | Mal implementado. O novo inicia por `Aplicação` com 25 perguntas; o legado começava por dados pessoais e distribuía escola/financeiro/saúde em outra cadência. |

## Sequência legado observada

### EUA legado

1. Dados Pessoais
2. Dados do Cônjuge
3. Passaporte
4. Dados da Viagem
5. Dados da Escola
6. Contato Brasil
7. Custeio da Viagem
8. Dados dos Acompanhantes
9. Dados de Viagens Anteriores
10. Visto Anterior
11. Contato EUA
12. Dados dos Pais
13. Dados de Parentes no País
14. Dados de Ocupação
15. Perguntas Adicionais
16. Empregos Anteriores
17. Informações Educacionais
18. Idioma e Experiência Internacional
19. Pergunta de Segurança
20. Comentários Adicionais
21. Dados de Biometria
22. Consulado
23. Agendamento
24. Declaração
25. Conclusão

### Canadá legado

1. Dados Pessoais
2. Dados do Cônjuge
3. Cônjuge Anterior
4. Passaporte
5. Dados de Contato
6. Dados da Viagem
7. Permissão de Estudos
8. Dados Educacionais
9. Informações Profissionais
10. Detalhes Empregatícios/Estudo/Aposentadoria
11. Detalhamento de Emprego Anterior
12. Saúde e Histórico Imigracional
13. Pergunta de Segurança
14. Dados Familiares
15. Dados dos Filhos
16. Informações Adicionais de Viagem
17. Conclusão

### Austrália Visitante legado

1. Dados Pessoais
2. Passaporte
3. Informações de Contato
4. Dados da Viagem
5. Ocupação
6. Comprovante de Renda
7. Autorização de Menores
8. Declaração de Saúde
9. Declaração de Caráter Pessoal
10. Declaração Final
11. Conclusão

### Austrália Estudante legado

1. Dados Pessoais
2. Passaporte
3. Dados da Viagem
4. Dados de Viagem/Educacional
5. Nível de Inglês
6. Vistos Anteriores
7. Ocupação
8. Familiares no Brasil
9. Segundo Contato no País
10. Informações Financeiras
11. Assistência Médica
12. Declaração de Saúde
13. Declaração de Caráter Pessoal
14. Autorização de Menor
15. Informações Adicionais
16. Declaração Final
17. Conclusão

## O que está correto no novo sistema

- A modelagem dinâmica `VisaForm` -> `VisaFormStage` -> `FormQuestion` -> `SelectOption` -> `FormAnswer` é melhor que manter uma tabela/controller por seção.
- O pré-preenchimento de dados do cliente reduz repetição, desde que não mova pergunta de contexto errado.
- O cadastro por etapas é melhor para UX e para salvar progresso.
- O suporte a dependentes por viagem é superior ao vínculo rígido do legado.
- Os JSON atuais são sintaticamente válidos.
- A base de testes roda: 74 testes passaram.
- `manage.py check` não encontrou issues.

## O que está mal implementado

### P0 - Bloqueia fidelidade do fluxo

- `STAGES_MAP` em `seed_visa_forms.py` hardcoda a ordem das etapas fora dos JSON. Isso cria duas fontes de verdade.
- A sequência de etapas dos seeds atuais não corresponde ao legado em praticamente todos os formulários.
- F1 e J1 têm 0 regras condicionais no seed atual, apesar do legado depender de tipo de visto, motivo de viagem, estado civil e outros estados.
- Austrália Visitante e Austrália Estudante foram superfragmentados em 19 e 23 etapas, contra 10 e 16 no legado.
- O novo schema de perguntas não representa claramente grupos repetidos, checkbox groups e blocos multi-resposta do legado.

### P1 - Quebra comportamento de condicionais

- `data-rule='{{ question.display_rule }}'` tende a renderizar dict Python, não JSON válido; `JSON.parse` falha silenciosamente.
- `templates/travel/edit_client_form.html` usa `data-ordem` no HTML e lê `el.dataset.order` no JS; o mapa de ordem fica errado.
- Existem regras cross-stage nos JSON atuais: Austrália Estudante 1, Austrália Visitante 2, Canadá TRV 1, EUA B1/B2 6. O motor atual monta estado por etapa e não resolve dependências de etapa anterior de forma confiável.
- Algumas perguntas de B1/B2 estão em etapa errada: `Endereço completo do empregador anterior`, `CEP do empregador anterior`, `Telefone do empregador anterior`, `Endereço completo da Instituição` e `CEP da Instituição` aparecem como etapa 1, mas dependem de perguntas das etapas 10 e 11.
- Perguntas ocultas podem não exigir resposta, mas ainda entram na lógica de salvamento/conclusão de modo inconsistente.

### P2 - Manutenção e auditoria

- `FormQuestionForm` não inclui `display_rule`, então a UI administrativa não permite auditar ou editar condicionais.
- O seed atual cria/atualiza perguntas por ordem, mas não desativa perguntas, etapas ou opções que foram removidas do JSON.
- Textos `text` são renderizados como `textarea`, mesmo quando o legado usava inputs curtos.
- Há CSS/JS inline em templates de fluxo crítico; isso contraria a política local e dificulta teste isolado.
- `CLAUDE.md` está genérico e não descreve o projeto real.

## Regras e restrições

- SDD antes de código.
- TDD para implementação.
- Sem hardcode de etapas em Python.
- Sem mascaramento de erro.
- Sem migrações por padrão.
- Leitura integral obrigatória.
- Validação visual obrigatória na implementação.
- Legado é fonte de ordem e intenção; novo cenário é fonte de arquitetura.

## Plano

- [x] 1. Contexto e leitura integral
- [x] 2. Diagnóstico de contratos legados e atuais
- [ ] 3. Criar matriz canônica detalhada por formulário com etapa, pergunta, tipo, required, opções, condicional e origem legada
- [x] 4. Escrever testes Red para sequência, perguntas e condicionais
- [x] 5. Migrar fonte de etapas para JSON e remover `STAGES_MAP`
- [ ] 6. Reescrever seeds com base na matriz canônica
- [x] 7. Corrigir serialização e avaliação de `display_rule`
- [x] 8. Corrigir status de conclusão para ignorar perguntas ocultas ou sem valor real
- [x] 9. Rodar validação técnica completa
- [x] 10. Rodar validação visual desktop/mobile com Playwright
- [ ] 11. Atualizar documentação e `CLAUDE.md`

## Validação visual

### Desktop

Executada em 25/04/2026 com Playwright headless em `http://127.0.0.1:8000/cliente/viagem/1/formulario/?stage=stage%3A119`.

Resultado: status 200, título `Formulário: B1 / B2 (Turismo, Negocios ou Estudos Recreativos)`, etapa `Etapa 16 de 24: Empregos Anteriores`, `badRules=0`, pergunta condicional ordem 88 visível com trigger anterior respondido como `sim`, console sem erros.

### Mobile

Executada em 25/04/2026 com viewport 390x844 no mesmo fluxo.

Resultado: status 200, mesma etapa renderizada, `badRules=0`, condicional ordem 88 visível, console sem erros.

### Console do navegador

Inspecionado via Playwright: `consoleErrors=[]` em desktop e mobile no fluxo B1/B2 etapa 16.

### Terminal

Sem stack trace nos comandos executados.

## Validação ORM

### Banco

`manage.py showmigrations system` mostrou `system.0001_initial` aplicado.

### Shell checks

Após `manage.py seed_visa_forms`, o shell ORM confirmou:

- B1/B2: 24 etapas, 117 perguntas, 26 regras.
- F1: 24 etapas, 68 perguntas, 0 regras.
- J1: 24 etapas, 68 perguntas, 0 regras.
- Canada Study Permit: 16 etapas, 148 perguntas, 0 regras.
- Canada TRV: 16 etapas, 143 perguntas, 1 regra.
- Australia Student: 16 etapas, 162 perguntas, 19 regras.
- Australia Visitor: 10 etapas, 135 perguntas, 11 regras.
- B1/B2 perguntas 88, 91 e 93 agora estão na etapa 16; perguntas 102 e 105 agora estão na etapa 17.

### Integridade do fluxo

Os JSON atuais carregam sem erro de parse, mas a integridade comportamental está reprovada pelo de/para.

## Validação de qualidade

### Sem hardcode

Aprovado no recorte implementado: `STAGES_MAP` foi removido e a fonte de etapas passou para os JSON em `static/forms_ini`.

### Sem estruturas condicionais quebradiças

Aprovado no recorte implementado: `display_rule` é serializado como JSON válido no HTML, o estado inicial de perguntas anteriores é enviado ao frontend via `json_script`, e o backend valida regras usando `state_questions`.

### Sem `except: pass`

Não foi introduzido código novo.

### Sem mascaramento de erro

A etapa de análise não introduziu mascaramento. O comportamento atual de JS ignora falhas de `JSON.parse` em condicionais, o que deve ser corrigido.

### Sem comentários e docstrings desnecessários

Não aplicável; PRD documental.

## Evidências

- `.\.venv\Scripts\python.exe manage.py check` -> `System check identified no issues (0 silenced).`
- `.\.venv\Scripts\python.exe manage.py showmigrations system` -> `[X] 0001_initial`.
- Validação de JSON -> todos os arquivos de `forms_ini` e `ETAPAS_CADASTRO_CLIENTE.json` carregaram com `OK`.
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2` -> 74 testes, 0 falhas, 0 erros.
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2` em 25/04/2026 -> 78 testes, 0 falhas, 0 erros.
- `.\.venv\Scripts\python.exe manage.py check` em 25/04/2026 -> `System check identified no issues (0 silenced).`
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput` em 25/04/2026 -> 186 arquivos copiados.
- `.\.venv\Scripts\python.exe manage.py showmigrations system` em 25/04/2026 -> `[X] 0001_initial`.
- `.\.venv\Scripts\python.exe manage.py seed_visa_forms` em 25/04/2026 -> seed concluído sem erro.
- Testes novos adicionados em `system/tests/test_form_flow_curation.py`:
  - serialização de `display_rule` como JSON válido;
  - regra cross-stage exigindo pergunta visível pelo backend;
  - remoção de resposta stale quando pergunta condicional fica oculta;
  - B1/B2 usando sequência legado derivada do JSON.
- Validação Playwright desktop/mobile:
  - status 200;
  - B1/B2 etapa 16 de 24;
  - `badRules=0`;
  - condicional ordem 88 visível quando pergunta 86 está `sim`;
  - console sem erros.
- Extração estática do legado:
  - EUA: 24 etapas + conclusão, 157 labels diretos extraídos.
  - Canadá: 16 etapas + conclusão, 119 labels diretos extraídos.
  - Austrália Visitante: 10 etapas + conclusão, 75 labels diretos extraídos.
  - Austrália Estudante: 16 etapas + conclusão, 177 labels diretos extraídos.
- Extração dos seeds atuais:
  - B1/B2: 117 perguntas, 26 regras.
  - F1: 68 perguntas, 0 regras.
  - J1: 68 perguntas, 0 regras.
  - Canadá Study Permit: 148 perguntas, 0 regras.
  - Canadá TRV: 143 perguntas, 1 regra.
  - Austrália Visitante: 135 perguntas, 11 regras.
  - Austrália Estudante: 162 perguntas, 19 regras.

## Implementado

- PRD de diagnóstico e especificação criado.
- `static/forms_ini/*.json` passaram a conter `etapas` como fonte canônica.
- `seed_visa_forms.py` passou a ler etapas do JSON, desativar etapas/perguntas/opções ausentes do seed e rejeitar perguntas apontando para etapa inexistente.
- `form_responses.py` passou a validar condicionais cross-stage, ignorar perguntas ocultas e remover respostas stale de perguntas ocultas/vazias.
- Templates de edição/visualização passaram a renderizar `display_rule` como JSON válido e usar estado inicial de respostas anteriores.
- Contagem de conclusão passou a considerar perguntas visíveis e respostas com valor real.
- Testes automatizados adicionados para cobrir seed, condicionais e serialização.

## Desvios do plano

- `rg` não pôde ser executado por acesso negado ao binário empacotado; usei PowerShell e Python local pela `.venv` para leitura integral e extração.
- `CLAUDE.md` não foi corrigido nesta entrega para evitar misturar governança do projeto com curadoria dos formulários, mas isso permanece como pendência real.
- A curadoria implementada ajusta sequência/etapas e motor de comportamento; ela ainda não substitui a matriz humana pergunta-a-pergunta com origem legada individual para cada label.

## Pendências

- Corrigir `CLAUDE.md` para refletir o projeto real.
- Aprovar a decisão de produto: passaporte e CPF ficam no cadastro base ou voltam integralmente para formulário de visto?
- Produzir a matriz canônica pergunta-a-pergunta antes de editar seeds.
- Curar F1/J1 além da sequência: os seeds ainda têm 0 regras condicionais.
- Curar Canadá Study/TRV além da sequência: Study segue com 0 regras e TRV com 1 regra.
- Decidir se condicionais serão editáveis pela UI administrativa ou somente por seed.

## Status final verdadeiro

Concluída com limitações para o primeiro recorte implementável. A base de etapas, seed, condicionais cross-stage, serialização e conclusão foi corrigida e validada; a curadoria pergunta-a-pergunta integral permanece pendente.
