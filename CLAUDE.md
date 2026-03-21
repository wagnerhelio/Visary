# CLAUDE.md — Spec Arquitetural e de Domínio do projeto Visary

> **Fonte única de verdade técnica do projeto.**
> Este documento descreve arquitetura, domínios, invariantes, integrações, fluxos críticos e restrições operacionais do sistema **Visary**.
> Regras de comportamento do agente ficam no `AGENTS.md`.

---

## 0. Status da spec

**Projeto:** Visary
**Tipo:** plataforma web (Django monólito modular) para gestão de consultoria de vistos
**Escopo atual:** operação completa de consultoria, incluindo onboarding de clientes em etapas configuráveis, gestão de dependentes com vínculo principal/dependente, viagens (país + tipo de visto), processos com checklist por etapas, formulários dinâmicos por tipo de visto, controle financeiro por viagem com propagação automática de pagamento, parceiros indicadores, área do cliente com acesso por CPF e painel administrativo com permissões por módulo/perfil.

Esta spec deve ser atualizada sempre que surgir:
- nova regra de negócio da consultoria;
- nova exigência operacional ou legal;
- nova restrição de integração ou de dados sensíveis;
- nova decisão estrutural que afete o projeto inteiro.

---

## 1. Visão do sistema

O **Visary** é um monólito modular Django para consultorias de vistos, com foco em:
- identidade única de cliente por CPF;
- cadastro em etapas configuráveis (wizard dinâmico);
- gestão de dependentes vinculados a um cliente principal;
- viagens com país destino e tipo de visto, vinculando múltiplos clientes;
- processos com checklist de etapas por (viagem, cliente), com progresso calculado;
- formulários dinâmicos por tipo de visto e respostas por (viagem, cliente, pergunta);
- controle financeiro com criação automática de registros e propagação de pagamento do principal para dependentes;
- parceiros indicadores com acompanhamento condicional;
- área do cliente autenticada por CPF (sessão, sem `auth.User`);
- painel administrativo com controle de acesso por perfil e módulo.

Arquitetura alvo:
- **backend:** Django 5.2;
- **banco principal:** PostgreSQL (produção); SQLite para dev/local (com limitações conhecidas de concorrência);
- **frontend:** templates Django + JS progressivo;
- **integrações externas:** serviço de CEP multi-fonte (ViaCEP, BrasilAPI, pycep-correios, brazilcep);
- **configuração de seeds:** variáveis de ambiente (`.env`) + arquivos JSON em `static/`.

---

## 2. Princípios arquiteturais

1. **Monólito modular primeiro.** Não fragmentar o domínio cedo demais.
2. **Identidade centralizada.** Cliente é único por CPF; perfis e vínculos se acumulam.
3. **Regras do domínio no backend.** Frontend melhora UX, mas não decide o que é permitido.
4. **Fluxos críticos com consistência transacional.** Usar `transaction.atomic()` quando o fluxo cria/atualiza múltiplos registros relacionados.
5. **Segurança por camadas.** Autorização e escopo no backend + templates apenas para exibir.
6. **Configuração é externa ou persistida.** Preferir modelos/admin para regras configuráveis; nada importante deve ficar hardcoded.
7. **Integrações são falíveis.** Tratar falhas com fallback e mensagens claras ao usuário.

---

## 3. Topologia de app/domínios

A organização do monólito reflete o domínio real do negócio em um app único:

- `system/` — domínio completo e infraestrutura: clientes, dependentes, viagens, processos, formulários dinâmicos, financeiro, parceiros, etapas de cadastro, autenticação dual (consultor via `auth.User` sincronizado + cliente via sessão/CPF), permissões por módulo/perfil, views de orquestração, área do cliente, administração, seeds e páginas estruturais.

---

## 4. Identidade, autenticação e modelo de acesso

### 4.1 Regra central de identidade
- Cada cliente deve ter **uma única identidade** no sistema.
- **CPF é o identificador único** de login e negócio (`ClienteConsultoria.cpf` com `unique=True`).
- É proibido duplicar cadastro para a mesma pessoa (incluindo na sessão temporária durante wizard de cadastro).

### 4.2 Autenticação dual

**Consultores/Assessores:**
- Login via `UsuarioConsultoria.email` + senha.
- Verificação em `UsuarioConsultoria` com `check_password()` (hash; fallback migratório de texto plano).
- Sincronização automática com `auth.User` via `_sync_consultant_user()` para usar `@login_required` e sessão Django.
- Opção "manter conectado" (2 semanas) ou expirar ao fechar navegador.

**Clientes:**
- Login via CPF (normalizado para 11 dígitos) ou e-mail.
- Não usa `auth.User`; dados armazenados na sessão: `cliente_id`, `cliente_nome`, `cliente_cpf`.
- Dependentes não podem fazer login (mensagem explicativa na tela).
- Senhas inválidas (`is_password_usable()`) exigem redefinição.

### 4.3 Dependentes com vínculo
- Dependentes são `ClienteConsultoria` com `cliente_principal` apontando para o titular.
- Dependente não faz login.
- Operações e listagens devem respeitar escopo por assessor no backend.
- Dados financeiros do titular não são exibidos para dependentes.

### 4.4 Permissões por perfil e módulo

Modelos: `Modulo`, `Perfil`, `UsuarioConsultoria` (em `system/models/permission_models.py`).

**Módulos definidos (11):** Clientes, Viagens, Processos, Formularios, Parceiros, Paises de Destino, Tipos de Visto, Tipos de Formulario de Visto, Financeiros, Relatorios, Usuarios.

**Perfis:** Administrador (acesso total), Atendente (acesso restrito).

Invariantes:
- Autorização deve ocorrer no backend nas views (não apenas via UI).
- Superuser/staff ou perfil "Administrador" gerencia tudo via `usuario_pode_gerenciar_todos()`.
- Atendentes veem/editam apenas dados vinculados ao seu assessor via `assessor_responsavel`.
- Verificação por módulo: `usuario_tem_acesso_modulo()`.
- Verificação por ownership: `usuario_pode_editar_cliente()`.

---

## 5. Domínios e regras canônicas

### 5.1 Cadastro em etapas (wizard dinâmico)

Modelos:
- `EtapaCadastroCliente` (ordem, nome, descrição, `campo_booleano` que mapeia flag do cliente).
- `CampoEtapaCliente` (campo configurável: nome, tipo, obrigatoriedade; `unique_together = ("etapa", "nome_campo")`).

Fluxo:
1. Etapas definem quais campos são visíveis/obrigatórios em cada passo.
2. View `cadastrar_cliente_view` navega em sequência; dados parciais na sessão (`cliente_dados_temporarios`).
3. Na etapa "Membros" (`campo_booleano='etapa_membros'`), dependentes são adicionados a `dependentes_temporarios` na sessão.
4. Ao finalizar, `_criar_cliente_do_banco()` cria principal + dependentes em `transaction.atomic()`.
5. Cada etapa concluída marca o campo booleano correspondente (ex.: `etapa_dados_pessoais=True`).
6. Opção "Finalizar e Criar Viagem" redireciona com cliente + dependentes pré-selecionados.

Invariantes:
- Validação considera apenas a etapa atual (não exigir campos de outras etapas).
- CPF é validado contra duplicidade na sessão e no banco.
- Dependente pode herdar dados do principal (endereço, dispensa senha).

### 5.2 Viagens e processos (checklist)

Modelos:
- `PaisDestino` (`nome` unique).
- `TipoVisto` (`unique_together = ("pais_destino", "nome")`).
- `Viagem` com M2M para clientes via `ClienteViagem` (through; `unique_together = ("viagem", "cliente")`). Cada `ClienteViagem` pode ter `tipo_visto` específico.
- `Processo` vinculado a `(viagem, cliente)` com `unique_together`.
- `StatusProcesso` (etapas reutilizáveis, opcionalmente vinculadas a tipo de visto).
- `ViagemStatusProcesso` (`unique_together = ("viagem", "status")`) — sincronizado automaticamente via signal.
- `EtapaProcesso` (checklist executado; `unique_together = ("processo", "status")`; com `concluida`, `prazo_dias`, `data_conclusao`).

Invariantes:
- Não duplicar processo para a mesma dupla (viagem, cliente).
- Não duplicar etapa/checklist para o mesmo par (processo, status).
- Progresso do processo deriva de contagem de etapas concluídas vs total.
- Status disponíveis por viagem são sincronizados automaticamente ao salvar viagem ou status de processo.

### 5.3 Formulários dinâmicos e respostas

Modelos:
- `FormularioVisto` (OneToOne com `TipoVisto`).
- `PerguntaFormulario` (tipos: texto, data, numero, booleano, selecao; `unique_together = ("formulario", "ordem")`).
- `OpcaoSelecao` (para perguntas tipo "selecao"; `unique_together = ("pergunta", "ordem")`).
- `RespostaFormulario` (`unique_together = ("viagem", "cliente", "pergunta")`; campos tipados: `resposta_texto`, `resposta_data`, `resposta_numero`, `resposta_booleano`, `resposta_selecao`).

Invariantes:
- Respostas respeitam o vínculo `(viagem, cliente, pergunta)`.
- Tipo de resposta deve ser compatível com `tipo_campo` da pergunta.
- Busca de formulário: tipo_visto do `ClienteViagem` > tipo_visto da `Viagem`.
- Clientes respondem na área do cliente; assessores visualizam/editam.

### 5.4 Financeiro

Modelos:
- `Financeiro` com viagem, cliente (opcional), assessor_responsavel, valor, data_pagamento, status e observações.
- `StatusFinanceiro` (TextChoices): `pendente`, `pago`, `cancelado`.

Regras de criação automática (via signals):
- Ao vincular clientes a uma viagem (`m2m_changed`), registros financeiros são criados automaticamente.
- O valor total vai para o **cliente principal** do grupo; dependentes recebem registros com valor zero.
- Se não há principal, o primeiro cliente recebe o registro.
- Se a viagem não tem clientes, cria registro com `cliente=None`.
- Duplicação de registros é evitada.

Propagação de pagamento (signal `propagate_payment_to_dependents`):
- Quando o registro do **cliente principal** é marcado como `PAGO`, todos os registros dos dependentes vinculados à mesma viagem são marcados como `PAGO` automaticamente.
- Ocorre apenas em atualização (não criação), apenas quando status=PAGO, e apenas se o cliente é principal.

Dar baixa:
- Restrito a administradores (`pode_gerenciar_todos`).
- Form permite definir `data_pagamento`, `status` e `observacoes`.

Dashboard financeiro:
- Totais de registros, pendentes, pagos; valores via `Sum`.
- Últimos 10 registros; restrito a administradores.

### 5.5 Parceiros

Modelos:
- `Partner` com CPF/CNPJ (opcionais), `email` unique, senha hash, segmento (agencia_viagem, consultoria_imigracao, advocacia, educacao, outros).
- `ClienteConsultoria.parceiro_indicador` indica quem indicou (acompanhamento condicional).

---

## 6. Signals do sistema

1. **`propagate_payment_to_dependents`** (post_save em `Financeiro`) — propaga status `PAGO` do principal para dependentes na mesma viagem.
2. **`criar_registro_financeiro`** (post_save em `Viagem`) — cria registros financeiros ao criar viagem com clientes.
3. **`criar_registro_financeiro_ao_adicionar_cliente`** (m2m_changed em `Viagem.clientes.through`) — cria/atualiza registros financeiros ao adicionar clientes.
4. **`sincronizar_status_viagem_post_save`** (post_save em `Viagem`) — sincroniza `ViagemStatusProcesso` disponíveis.
5. **`sincronizar_status_viagem_status`** (post_save em `StatusProcesso`) — atualiza viagens quando um status de processo muda.
6. **`ensure_initial_system_data`** (post_migrate) — carrega módulos, perfis e usuários do `.env`.
7. **`ensure_initial_domain_data`** (post_migrate) — carrega países, tipos de visto, parceiros, status de processo, formulários e etapas do `.env` e JSON.

---

## 7. Integrações externas

### 7.1 Consulta de CEP

Serviço: `system/services/cep.py` — `buscar_endereco_por_cep(cep)`.

Estratégia multi-fonte com fallback sequencial:
1. **ViaCEP** (API REST)
2. **BrasilAPI** (API REST)
3. **pycep-correios** (biblioteca Python)
4. **brazilcep** (biblioteca Python)

Regras:
- Falha em uma fonte tenta a próxima automaticamente.
- Resposta normalizada para formato padrão (`cep`, `street`, `district`, `city`, `uf`, `complement`).
- CEP inválido ou todas as fontes falhando deve resultar em mensagem clara ao usuário, sem travar o fluxo.
- Cada tentativa e falha é logada.

### 7.2 Sem gateway de pagamento

O financeiro é puramente de controle interno (baixa manual). Não há integração com Stripe ou outro gateway.

### 7.3 Importação legada de produção para teste (`criar_seeds_prod`)

Objetivo operacional:
- espelhar dados de produção no ambiente de teste local em uma carga única;
- sem sincronização incremental, sem agendamento e sem jobs periódicos.

Fluxo padrão esperado:
1. `python cleanup.py`
2. `python manage.py makemigrations`
3. `python manage.py migrate`
4. `python manage.py criar_superuser_admin`
5. `python manage.py criar_seeds_prod`

Configuração mínima obrigatória no `.env`:
- `LEGACY_DB_HOST`
- `LEGACY_DB_PORT`
- `LEGACY_DB_NAME`
- `LEGACY_DB_USER`
- `LEGACY_DB_PASSWORD`
- `LEGACY_IMPORT_SHARED_PASSWORD`

Regras de segurança e operação:
- Credenciais de SSH (`ssh -p ... user@host`) e de MySQL (`LEGACY_DB_USER/LEGACY_DB_PASSWORD`) são independentes.
- Nunca assumir que usuário/senha de SSH funcionam no MySQL.
- Erros de autenticação do MySQL (`1045`) devem ser tratados como problema de credencial/permissão remota, não como falha de mapeamento do import.
- O import deve ser idempotente por execução (upsert + deduplicação semântica, sem hard reset de domínio) e respeitar constraints de unicidade do sistema atual.
- O mapeamento legado de tipo de visto deve usar normalização semântica (acentos/hífens/pontuação) para evitar catálogos duplicados que quebrem o vínculo com formulários.
- A revalidação final do import deve comparar cobertura de formulários por tipo de visto efetivamente usado e completude mínima de perguntas com os JSONs de `static/forms_ini`.
- O `cleanup.py` deve ser estritamente não destrutivo para código-fonte: remover apenas `__pycache__`, migrations locais e `db.sqlite3`; é proibido strip de comentários/docstrings e encerramento indiscriminado de processos Python.
- Em execução operacional do agente, comandos `git` (status/diff/log/checkout/reset/rebase etc.) só podem ocorrer com solicitação explícita do usuário na tarefa atual.
- Execução e instalação de dependências para import devem ocorrer no `.venv` do projeto; não instalar drivers do legado no Python global.
- Diagnóstico mínimo obrigatório quando `criar_seeds_prod` falhar: `sys.executable`, presença de `mysql-connector-python`/`pymysql` no `.venv`, e confirmação de ausência desses pacotes no Python global.

---

## 8. Segurança e dados sensíveis

### 8.1 Dados tratados
O sistema lida com:
- dados cadastrais pessoais (nome, CPF, data de nascimento, nacionalidade);
- dados de endereço;
- dados de passaporte (número, país emissor, datas, autoridade emissora);
- dados de dependentes (incluindo menores);
- dados financeiros de assessoria.

### 8.2 Regras obrigatórias
- Coletar apenas o mínimo necessário.
- Restringir acesso por perfil e necessidade operacional.
- Backend filtra por `assessor_responsavel` e verifica módulos/perfil.
- Templates não decidem permissão; apenas exibem conforme contexto.
- Dados de passaporte são sensíveis e devem ter controle de acesso adequado.

### 8.3 Observação sobre exclusão/anonimização
A spec deve evoluir quando aparecerem requisitos legais explícitos (LGPD: anonimização, exclusão definitiva) não modelados hoje no código. Atualmente não há fluxo de exclusão definitiva implementado.

---

## 9. Mapeamento macro de telas e domínios

O sistema cobre, no mínimo, estes macroblocos funcionais:
- T01 Landing, login e acesso (consultor via e-mail + cliente via CPF)
- T02 Cadastro e onboarding por etapas (wizard dinâmico: dados pessoais, endereço, passaporte, membros/dependentes)
- T03 Área do cliente (dashboard, viagens vinculadas, formulários/respostas e status de processo)
- T04 Gestão de clientes (home com cards, listagem, visualização, edição, exclusão, dependentes)
- T05 Gestão de viagens (CRUD + clientes vinculados + formulários por viagem)
- T06 Gestão de países destino e tipos de visto (CRUD com verificação de exclusão)
- T07 Gestão de processos e checklist (CRUD + etapas, adicionar/remover, progresso)
- T08 Gestão de status de processo (CRUD configurável)
- T09 Formulários dinâmicos (tipos de formulário, perguntas, opções, respostas por viagem/cliente)
- T10 Gestão de parceiros (CRUD + indicação condicional)
- T11 Financeiro (home/dashboard, listagem com filtros, dar baixa)
- T12 Administração (CRUD de usuários, perfis e módulos)
- T13 Etapas de cadastro configuráveis (CRUD de etapas e campos)
- T14 Página de acesso negado (403)

Se uma feature nova não se encaixar claramente em um desses domínios, a modelagem precisa ser revisitada antes da implementação.

---

## 10. Fluxos críticos que exigem cuidado extra

1. Cadastro/edição de cliente quando CPF já existe (validação no banco e na sessão do wizard).
2. Criação/edição de dependente garantindo vínculo `cliente_principal` e escopo por assessor.
3. Onboarding transacional: principal + dependentes em `transaction.atomic()`.
4. Criação de `Processo` duplicado para a mesma dupla (viagem, cliente).
5. Adição/remoção/edição de `EtapaProcesso` preservando integridade do checklist (`unique_together`).
6. Persistência de `RespostaFormulario` respeitando vínculo (`viagem`, `cliente`, `pergunta`).
7. Persistência de resposta com tipo incompatível com `PerguntaFormulario.tipo_campo`.
8. Baixa/edição em `Financeiro` com permissões corretas no backend e propagação automática.
9. Signals de criação financeira ao vincular clientes: evitar duplicação e garantir valor no principal.
10. Sincronização de `ViagemStatusProcesso` ao salvar viagem ou status de processo.
11. Falha na consulta de CEP: manter cadastro em estado consistente.
12. Login de cliente: normalização de CPF, bloqueio de dependente, migração de senhas.
13. Import de produção em `criar_seeds_prod`: validar autenticação em banco legado, preservar constraints locais e evitar mistura com seed de demonstração.
14. Falha de dependência no import legado: validar escopo de instalação (`.venv` vs global) antes de alterar mapeamentos de domínio.

---

## 11. Armadilhas conhecidas

- Confiar apenas em bloqueio visual no frontend para permissões/escopo.
- Misturar regra financeira com renderização de template.
- Permitir que dependente acesse dados financeiros/administrativos do titular fora do escopo.
- Persistir respostas fora do vínculo `(viagem, cliente, pergunta)` ou ignorar constraints.
- Prosseguir com escrita após falha de pré-condições/constraints (falhar cedo).
- N+1 queries em listagens e páginas que agregam relações.
- Criar dois clientes para o mesmo CPF (incluindo via sessão temporária do wizard).
- Expor dados de passaporte sem controle de acesso adequado.
- Ignorar fallback do serviço de CEP e deixar o fluxo travar sem orientação.
- Assumir que signals financeiros cobrem todos os cenários de vínculo sem verificar edge cases.
- Testar concorrência só em SQLite e assumir que produção está coberta.
- Executar rotina de limpeza que altere código-fonte (ex.: strip de comentários/docstrings) ou finalize processos Python fora do escopo do projeto.
- Executar comandos `git` sem solicitação explícita do usuário na tarefa atual.

---

## 12. Definição mínima de pronto para mudanças sensíveis

Uma mudança é considerada pronta quando:
1. respeita esta spec e o `AGENTS.md`;
2. não quebra unicidade/relacionamentos (CPF, `cliente_principal`, `Processo`, `EtapaProcesso`, `RespostaFormulario`);
3. mantém autorização correta no backend (especialmente em financeiro, processos, viagens e administração por módulos/perfis);
4. valida campos da etapa atual em fluxos de cadastro;
5. trata falhas de integrações (CEP) sem "meio estado" de cadastro;
6. possui testes adequados ao risco;
7. não introduz N+1 queries em listagens ou dashboards.

---

## 13. Changelog da spec

- **[2026-03-19]** Criação/primeira consolidação da spec do Visary.
- **[2026-03-19]** Consolidação completa: mapeamento exaustivo de 18 models, 113 URLs, 7 signals, sistema de autenticação dual, wizard de cadastro, formulários dinâmicos, fluxo financeiro com propagação, permissões por módulo/perfil, integrações de CEP multi-fonte e macroblocos de telas.
- **[2026-03-20]** Adicionada política explícita de importação legada (`criar_seeds_prod`): carga total para teste, variáveis `LEGACY_DB_*`, separação entre credenciais SSH e MySQL, e diagnóstico operacional para erro de autenticação remota.
- **[2026-03-20]** Reforçada política de ambiente para import legado: dependências obrigatórias no `.venv`, proibição de instalação no Python global e checklist de diagnóstico de execução.
- **[2026-03-20]** Definida política de segurança do `cleanup.py`: limpeza apenas de artefatos locais (`__pycache__`, migrations locais e `db.sqlite3`), sem mutação de código-fonte e sem encerramento indiscriminado de processos Python.
- **[2026-03-20]** Definida regra de deduplicação semântica para `TipoVisto` no import legado e revalidação obrigatória de formulários modularizados com base em `static/forms_ini`.
