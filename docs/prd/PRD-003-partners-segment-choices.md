# PRD-003: Corrigir choices de segmento em parceiros
## Resumo
Corrigir erro `AttributeError` ao acessar `/partners/` causado por uso de `Partner.SEGMENT_CHOICES`.

## Problema atual
A view de parceiros tenta acessar `SEGMENT_CHOICES` como atributo da classe `Partner`, mas as choices estao declaradas no modulo do model e no campo `segment`. Isso quebra `/partners/` e `/partners/listar/`.

## Objetivo
Renderizar as telas de parceiros sem erro e manter o filtro de segmento usando as choices reais do campo `segment`.

## Contexto consultado
- Context7: indisponivel nesta sessao.
- Web: Django docs, Model field reference e Model `_meta` API. A correcao usa introspeccao do campo via `Partner._meta.get_field("segment").choices`.

## Dependencias adicionadas
- nenhuma

## Escopo / Fora do escopo
- Escopo: view de parceiros e teste de regressao.
- Fora do escopo: alteracoes no modelo, migrations, layout e seeds.

## Arquivos impactados
- `system/views/partners_views.py`
- `system/tests/test_partners_views.py`

## Riscos e edge cases
- O template usa `segmentos`, entao a view deve enviar esse nome de contexto.
- `/partners/` e `/partners/listar/` compartilham a mesma fonte de choices.

## Regras e restricoes
- Corrigir com menor mudanca correta.
- TDD: teste falhando reproduzindo o erro antes da correcao, depois green.
- Sem nova dependencia.

## Criterios de aceite
- [x] GET em `/partners/` deve retornar 200 para usuario autenticado com permissao.
- [x] GET em `/partners/listar/` deve retornar 200 para usuario autenticado com permissao.
- [x] O contexto deve expor `segmentos` com as choices do campo `Partner.segment`.
- [x] A suite Django deve passar.

## Plano
- [x] 1. Reproduzir erro com teste de regressao.
- [x] 2. Corrigir view para usar `Partner._meta.get_field("segment").choices`.
- [x] 3. Ajustar chave de contexto para `segmentos`.
- [x] 4. Rodar teste focado e suite completa.

## Comandos de validacao
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_partners_views --verbosity 2`
- `.\.venv\Scripts\python.exe manage.py check`
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2`
- `.\.venv\Scripts\python.exe manage.py showmigrations`

## Implementado
- Criado teste de regressao cobrindo `home_partners` e `list_partners`.
- Criado helper `_segment_choices()` em `system/views/partners_views.py`.
- Substituido `Partner.SEGMENT_CHOICES` por `Partner._meta.get_field("segment").choices`.
- Contexto passa `segmentos`, que e o nome usado pelos templates.

## Desvios do plano
- nenhum
