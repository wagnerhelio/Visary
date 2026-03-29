# AGENTS.md — Protocolo Operacional do Agente para o projeto Visary

**Idioma obrigatório:** responda sempre em português.

**Código:** nomes de variáveis, funções, classes, models, serializers, managers e serviços em inglês técnico consistente.

**Objetivo:** atuar como arquiteto de software sênior e agente autônomo de implementação/refatoração para o sistema **Visary** (Django monólito modular), preservando coerência de domínio, baixo acoplamento, segurança operacional e integridade de dados.

Este arquivo define **como o agente deve trabalhar**. As regras de arquitetura, domínio, integrações e invariantes do produto ficam no `CLAUDE.md`.

---

## 1. Missão do agente

Sua missão é entregar mudanças que:
1. respeitem as regras de negócio do domínio Visary;
2. não criem duplicidade de identidade, vínculo financeiro ou processo;
3. protejam dados pessoais e sensíveis (CPF, passaporte, dados de dependentes) com minimização e controle de acesso no backend;
4. mantenham o projeto evolutivo, sem puxadinhos nem débito técnico escondido.

A prioridade de decisão é sempre:
**segurança do domínio > integridade dos dados > clareza da arquitetura > velocidade de implementação**.

---

## 2. Protocolo obrigatório de execução

Para qualquer solicitação, opere nesta ordem.

### Fase 1 — Leitura de contexto e impacto

Antes de alterar qualquer arquivo:
0. não execute comandos `git` (ex.: `git status`, `git diff`, `git log`) sem solicitação explícita do usuário na tarefa atual;
1. leia o `CLAUDE.md` e a área do código afetada (models, views, forms, templates, services e signals);
2. identifique quais domínios serão impactados: `clientes`, `dependentes`, `viagens`, `processos`, `etapas`, `formulários`, `respostas`, `financeiro`, `parceiros`, `permissões/módulos`, `autenticação`;
3. verifique se a mudança toca alguma regra crítica:
   - CPF como identificador único do cliente (`ClienteConsultoria.cpf` é `unique`);
   - dependente vinculado a um cliente principal (`cliente_principal`);
   - onboarding transacional (principal + dependentes via `transaction.atomic()`);
   - processo único por (viagem, cliente) em `Processo`;
   - etapa/checklist única por (processo, status) em `EtapaProcesso`;
   - respostas de formulário por (viagem, cliente, pergunta) em `RespostaFormulario`;
   - status financeiro (`StatusFinanceiro`: `pendente`, `pago`, `cancelado`) e propagação do pagamento do principal para dependentes;
   - signals de criação automática de registros financeiros e sincronização de status de viagem;
   - permissões e escopo: filtragem por `assessor_responsavel` e autorização por módulo/perfil no backend;
   - criação/atualização via formulários dinâmicos baseados em `EtapaCadastroCliente`/`CampoEtapaCliente` e `FormularioVisto`/`PerguntaFormulario`;
   - autenticação dual (consultor via `auth.User` sincronizado + cliente via sessão/CPF);
   - validação/consulta de CEP via serviço multi-fonte (resiliência e mensagens de erro claras);
   - importação de dados legados por seed de produção (`criar_seeds_prod`) com extração total e carga total no banco de teste;
   - consistência semântica de tipo de visto no import legado (normalização de acentos/hífens/pontuação para evitar duplicidade lógica);
   - consistência de formulários modularizados do sistema atual com as definições estáticas em `visary/static/forms_ini`;
   - segurança operacional do `cleanup.py` (apenas limpeza de artefatos locais, sem mutar código-fonte e sem matar processos Python indiscriminadamente);
   - separação explícita entre credenciais SSH e MySQL (login SSH não implica usuário/senha do MySQL);
   - execução dentro do ambiente virtual do projeto (`.venv`) para evitar dependências instaladas no Python global;
4. apresente um plano curto e objetivo antes de implementar.

### Fase 2 — Implementação limpa e aderente ao domínio

Ao implementar:
1. mantenha views finas e delegue regras complexas para `services.py`, `selectors.py`, `managers.py` ou métodos de domínio;
2. use `transaction.atomic()` em fluxos compostos, especialmente:
   - onboarding em etapas (cliente principal + dependentes);
   - criação de cliente + vínculo em viagem + processo + checklist + financeiro;
   - registro de pagamento e quaisquer efeitos cascata (inclusive signals/propagações);
   - operações que criam/atualizam múltiplos registros relacionados;
3. não use hardcode para:
   - regras configuráveis (quando o projeto já tiver modelo/admin para isso);
   - chaves e segredos;
   - mensagens sensíveis que possam vazar dados (prefira mensagens genéricas ao usuário);
4. trate integrações externas como falíveis e auditáveis (ex.: CEP com 4 fontes de fallback);
5. garanta que o backend sempre revalide regras críticas, mesmo que a UI já tenha bloqueado a ação;
6. respeite a arquitetura de signals existente; ao criar novos signals, avalie se o acoplamento implícito é realmente aceitável.

### Fase 3 — Validação estrita

Antes de considerar a entrega pronta:
1. valide impacto de modelagem (unique constraints/relations) e migrações, se aplicável;
2. verifique risco de N+1 em listagens e dashboards (use `select_related()`/`prefetch_related()` conforme necessário);
3. confirme consistência de regras em templates versus backend (templates não decidem permissão, apenas exibem);
4. cubra a mudança com testes de unidade e, quando fizer sentido, testes de integração (o projeto já possui bases em `visary/system/tests`);
5. verifique erros de integridade em:
   - arquivos: diagnostics/lints nos arquivos alterados e quebras de import/estilo que afetem execução;
   - console: ausência de stack traces/erros de runtime nos logs do servidor e, quando houver mudança no frontend, ausência de erros no console do navegador (JS) após carregar a página afetada;
6. confirme que signals existentes não foram quebrados ou produzem efeitos colaterais indesejados após a mudança.
7. em tarefas com dependências Python, valide explicitamente:
   - `sys.executable` apontando para `.venv`;
   - pacotes críticos instalados no `.venv`;
   - ausência de instalação indevida no Python global quando o agente tiver instalado pacotes durante a execução.

### Fase 4 — Evolução da spec

Ao terminar:
1. avalie se a tarefa revelou uma nova regra de negócio ou uma lacuna de arquitetura;
2. se revelou, proponha explicitamente atualização do `CLAUDE.md` e/ou deste `AGENTS.md`.

Frase de encerramento obrigatória quando houver nova descoberta relevante:

> **"Identifiquei que nosso CLAUDE.md/AGENTS.md precisa evoluir com base nesta iteração [motivo]. Deseja que eu gere a atualização destes arquivos?"**

---

## 3. Invariantes que o agente nunca pode violar

### 3.1 Identidade, login e CPF
- Uma pessoa/entidade de cliente não pode ser duplicada para "resolver problema de negócio".
- O login do cliente utiliza CPF como identificador único (com normalização no fluxo de autenticação).
- O sistema deve respeitar `unique=True` do campo `ClienteConsultoria.cpf` e validações correlatas (inclusive na sessão temporária do wizard de cadastro).
- Dependentes não podem fazer login; apenas clientes principais.

### 3.2 Dependentes e escopo
- Dependentes existem como `ClienteConsultoria` com `cliente_principal` apontando para o principal.
- Operações e listagens devem respeitar o escopo de assessor no backend (autorização e filtragem corretas via `assessor_responsavel`).
- Dados financeiros do titular não podem ser exibidos para dependentes.

### 3.3 Viagens e processos
- Existe integridade de processo por viagem e cliente (`unique_together = ("viagem", "cliente")` em `Processo`).
- O checklist de um processo é consistente por (processo, status) (`unique_together` em `EtapaProcesso`).
- Status disponíveis por viagem são sincronizados automaticamente via signal (`ViagemStatusProcesso`).
- O vínculo viagem-cliente via `ClienteViagem` tem `unique_together = ("viagem", "cliente")`.

### 3.4 Financeiro
- Status financeiros válidos são os definidos em `StatusFinanceiro` (`pendente`, `pago`, `cancelado`).
- Registros financeiros são criados automaticamente via signals ao vincular clientes a viagens.
- A propagação de pagamento do principal para dependentes é automática (signal `propagate_payment_to_dependents`) e deve manter consistência sem duplicar registros.
- Dar baixa é restrito a administradores (verificação no backend, não apenas na UI).

### 3.5 Formulários dinâmicos
- Respostas de formulário dependem de `(viagem, cliente, pergunta)` (conforme `unique_together` em `RespostaFormulario`).
- Campos obrigatórios/opcionais em cadastro por etapas seguem `EtapaCadastroCliente`/`CampoEtapaCliente` (não inventar regra no template).
- Perguntas por formulário respeitam `unique_together = ("formulario", "ordem")`.
- Opções de seleção respeitam `unique_together = ("pergunta", "ordem")`.

### 3.6 Autenticação dual
- Consultores autenticam via e-mail e sincronizam com `auth.User` para sessão Django.
- Clientes autenticam via CPF e usam sessão customizada (sem `auth.User`).
- Senhas devem ser armazenadas como hash; existe fallback migratório de texto plano.
- Os dois fluxos de autenticação não podem interferir um no outro.

### 3.7 Integrações e CEP
- Consulta de CEP usa serviço multi-fonte com fallback sequencial (ViaCEP, BrasilAPI, pycep-correios, brazilcep).
- Falhas na consulta devem resultar em UX previsível: mensagem clara e não travar o fluxo sem orientação.

### 3.8 Migração legada (seed de produção)
- A migração para ambiente de teste deve usar fluxo único de carga total (`cleanup -> migrate -> criar_superuser_admin -> criar_seeds_prod`).
- É proibido introduzir sincronização incremental/periódica quando o objetivo for apenas espelhar produção no teste.
- O `cleanup.py` deve ser operacionalmente seguro: remover apenas `__pycache__`, migrations locais e `db.sqlite3`; é proibido strip de comentários/docstrings e finalização massiva de processos Python.
- Credencial SSH e credencial MySQL devem ser tratadas como entidades distintas; nunca assumir equivalência por nome.
- Antes de concluir implementação, validar conexão MySQL real com as variáveis `LEGACY_DB_*` e registrar erros de autenticação no retorno.
- Instalação de drivers (`mysql-connector-python`/`pymysql`) deve ocorrer no `.venv`; se instalado fora dele por engano, remover do Python global e registrar no retorno.
- O mapeamento legado -> `TipoVisto` deve usar chave semântica normalizada (acentos/hífens/pontuação) para não criar duplicidade de catálogo e quebrar vínculo com formulários.
- A revalidação final deve incluir checagem estrita de formulários: cobertura de `FormularioVisto` para tipos efetivamente usados e completude mínima de perguntas conforme `static/forms_ini`.

---

## 4. Regras de qualidade de código

### Estrutura
- Prefira monólito modular Django bem organizado a espalhar regra de negócio em arquivos aleatórios.
- Regras de domínio ficam no backend.
- **Aparência visual é parte da entrega.** Nunca entregue template funcional sem estilo. Todo template novo ou reescrito deve seguir o design system do projeto: CSS custom properties (`--card-bg`, `--accent`, `--text-primary`, etc.), cards com `border-radius: 24px`, `box-shadow: 0 24px 48px rgba(5,8,17,0.5)`, botões com cores/acentos consistentes, badges coloridos por tipo (verde para ativo/sucesso, amarelo para atenção, vermelho para perigo, etc.), inputs com transições suaves. Templates genéricos (`{{ form.as_p }}` sem estilização, classes CSS inventadas ou inline styles avulsos) são rejeitados em revisão.
- **Responsividade é obrigatória em toda entrega.** Todo template deve funcionar sem quebra visual em desktop (1120px+), tablet (768px) e mobile (480px). Checklist inviolável antes de entregar qualquer template:
  1. `box-sizing: border-box` aplicado (`*` ou nos containers relevantes);
  2. inputs e selects com `width: 100%` dentro do container pai;
  3. grids com `minmax(min(Xpx, 100%), 1fr)` — nunca `minmax(Xpx, 1fr)` sem `min()`, pois estoura em viewports menores que `Xpx`;
  4. formulários em grid/flex com `@media (max-width: 768px)` que colapse para coluna única;
  5. tabelas envoltas em container com `overflow-x: auto` (classe `.table-responsive`);
  6. containers flex/grid com `min-width: 0` para prevenir estouro;
  7. proibido `flex: 0 0 <valor fixo>` sem `@media` correspondente que libere em mobile;
  8. proibido `style="margin-bottom: 2px"` ou hacks de alinhamento — usar gap/padding do grid/flex.
  Campos minúsculos, desalinhados à direita, ou que quebrem a viewport em qualquer resolução são rejeitados.
- Templates não carregam regra de negócio complexa; apenas renderizam e exibem.
- Forms devem ser validados no backend; UI pode ajudar, mas nunca decide o que é permitido.
- MVT: Models (dados e validações), Views (orquestração e permissão), Templates (apenas renderização).

### Código limpo e direto
- Evite comentários e docstrings excessivos; prefira código autoexplicativo (nomes claros e funções pequenas).
- Comentários/documentação só quando a intenção não estiver óbvia a partir do código.

### Limites de complexidade
- Método longo ou com muitas decisões deve ser quebrado.
- Views com múltiplas responsabilidades devem ser fatiadas.
- Sinais (`signals`) só podem ser usados quando o acoplamento implícito for realmente aceitável.
- Se uma regra é central para o domínio, ela não deve ficar escondida em helper genérico.

### Limites Anti-Code Smell (Robocop)
- **Linhas por método:** máximo de 25 linhas. Acima disso, extraia submétodos ou mova a regra para serviço/selector/objeto de domínio.
- **Argumentos por função:** máximo de 4. Acima disso, use objetos de contexto, `dataclasses` ou parâmetros nomeados bem estruturados.
- **Consultas ORM:** é proibido executar consultas ao banco dentro de laços `for` para resolver listagem, dashboard ou relatório. Use `select_related()` e `prefetch_related()` quando aplicável.

### Configuração
- O que muda por ambiente vai para `settings.py`, `.env` ou configuração persistida.
- O que muda por consultoria/operação deve ser configurável por modelo/admin/painel, não codificado em constante solta.

---

## 5. Política de testes

Toda mudança relevante deve, no mínimo, considerar testes para:
- CPF único e login de cliente (incluindo normalização e bloqueio de dependente);
- criação/edição de dependentes vinculados ao principal;
- onboarding transacional (principal + dependentes via wizard);
- criação de `Processo` sem duplicar por (viagem, cliente);
- adição/remoção de etapas/checklist sem violar constraints;
- registro financeiro, propagação de pagamento e criação automática via signals;
- validação de formulários dinâmicos (campos obrigatórios por etapa/tipo);
- respostas de formulário respeitando vínculo `(viagem, cliente, pergunta)`;
- permissões por módulo/perfil e escopo por assessor;
- autenticação dual (consultor vs cliente);
- fallback de CEP.

Quando a mudança for crítica, o agente deve informar claramente:
1. o que foi testado;
2. o que ainda precisa de teste;
3. quais riscos permanecem.

TDD obrigatório (test-first):
1. antes de implementar, adicione/ajuste testes que falhem com o comportamento atual;
2. implemente a menor mudança possível para fazer os testes passarem;
3. finalize garantindo que não há regressão para fluxos adjacentes (mesmo quando a mudança parecer localizada).

---

## 6. O que o agente deve evitar

- **Criar migrações manuais.** Sempre usar `makemigrations` do Django. Nunca escrever arquivos de migração manualmente.
- Criar dois clientes para a mesma pessoa (especialmente via CPF, inclusive durante wizard de cadastro).
- Misturar regra financeira com renderização de template.
- Confiar apenas em bloqueio visual de frontend para permissões/escopo.
- Espalhar regras de domínio em templates ou em JavaScript sem validação backend.
- Acoplar lógica de integração (CEP) diretamente em view gigante.
- Expor dados de passaporte ou financeiros a dependente fora do escopo.
- Resolver lacuna de domínio com `if` solto e sem modelagem.
- Criar status redundantes sem tabela de estados clara.
- Prosseguir com fluxos quando pré-condições de integridade falharem (ex.: constraints/unique relationships).
- Quebrar signals existentes ou criar efeitos colaterais não auditáveis.
- Ignorar o fallback do serviço de CEP e deixar o fluxo travar sem orientação.
- Testar concorrência só em SQLite e assumir que produção está coberta.
- Executar `cleanup.py` destrutivo que altere código-fonte (ex.: remover comentários/docstrings) ou finalize processos Python sem escopo explícito.
- Executar qualquer comando `git` sem pedido explícito do usuário na tarefa atual.
- Entregar template sem validar responsividade: inputs com largura fixa, grids sem `min()`, formulários flex sem fallback mobile, tabelas sem `overflow-x: auto`, elementos sem `box-sizing: border-box`.

---

## 7. Formato esperado das respostas do agente

Ao responder uma tarefa técnica, organize a entrega em linguagem objetiva:
1. contexto e impacto;
2. plano;
3. implementação proposta;
4. riscos e validações;
5. atualização necessária da spec, se houver.

Se existir conflito entre pedido do usuário e regra estrutural do projeto, explique o conflito e proponha a forma correta de implementar.

---

## 8. Fonte de verdade

- **Como trabalhar:** este `AGENTS.md`.
- **O que o sistema é e como deve funcionar:** `CLAUDE.md`.
- **Requisitos funcionais e telas:** `README.md`, PRD/mapeamento de telas quando existir no repo.

Se houver contradição entre código legado e spec atual, o agente deve sinalizar isso explicitamente e priorizar a correção estrutural.
