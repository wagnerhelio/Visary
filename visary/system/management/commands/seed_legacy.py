import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from system.models import (
    ClienteConsultoria,
    ClienteViagem,
    EtapaProcesso,
    Financeiro,
    FormularioVisto,
    OpcaoSelecao,
    PaisDestino,
    Partner,
    PerguntaFormulario,
    Processo,
    RespostaFormulario,
    StatusProcesso,
    StatusFinanceiro,
    TipoVisto,
    UsuarioConsultoria,
    Viagem,
)
from system.services.legacy_markers import extract_legacy_meta, upsert_legacy_meta


def normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_semantic_key(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def question_starts_with_key(question: str, key: str) -> bool:
    question = (question or "").strip()
    key = (key or "").strip()
    if not question or not key:
        return False
    return (
        question == key
        or question.startswith(f"{key} ")
        or question.startswith(f"{key}?")
        or question.startswith(f"{key}:")
    )


def normalize_cpf(value: str | None) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits if len(digits) == 11 else ""


def format_cpf(digits: str) -> str:
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


def synthetic_cpf(legacy_cliente_id: int) -> str:
    return format_cpf(f"9{int(legacy_cliente_id):010d}")


def parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return value
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_decimal(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    raw = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def parse_decimal_strict(value):
    if value in (None, ""):
        return None
    raw = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    if not re.fullmatch(r"[-+]?\d+(\.\d+)?", raw):
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def parse_bool(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "sim", "yes", "y"}:
        return True
    if text in {"0", "false", "f", "nao", "não", "no", "n"}:
        return False
    return None


class Command(BaseCommand):
    help = "Importa dados do banco legado para clientes, viagens, processos, formularios e financeiro."

    def handle(self, *args, **options):
        legacy = self._load_legacy_data()
        blocking = self._detect_blocking_anomalies(legacy)
        if blocking:
            raise CommandError(
                "Anomalias bloqueantes detectadas no legado:\n- " + "\n- ".join(blocking)
            )

        actor = self._get_actor_user()
        assessor_default = UsuarioConsultoria.objects.filter(ativo=True).order_by("id").first()
        if not assessor_default:
            raise CommandError(
                "Nao existe UsuarioConsultoria ativo para vincular assessor_responsavel. "
                "Rode seed_usuarios_consultoria antes de seed_legacy."
            )

        with transaction.atomic():
            pais_map = self._import_paises(legacy, actor)
            tipo_map = self._import_tipos_visto(legacy, pais_map, actor)
            parceiro_map = self._import_parceiros(legacy, actor)
            cliente_map, cliente_issues = self._import_clientes(
                legacy,
                assessor_default,
                actor,
            )
            self._import_dependentes(legacy, cliente_map)
            viagem_map = self._import_viagens(
                legacy,
                cliente_map,
                tipo_map,
                pais_map,
                parceiro_map,
                assessor_default,
                actor,
            )
            parceiro_links = self._collect_legacy_partner_links(legacy)
            parceiros_linked_count = self._link_clientes_parceiros(
                cliente_map,
                parceiro_map,
                parceiro_links,
            )
            processo_map = self._import_processos(
                legacy,
                cliente_map,
                viagem_map,
                tipo_map,
                assessor_default,
                actor,
            )
            etapas_count = self._import_etapas_processo(
                legacy,
                processo_map,
                tipo_map,
            )
            financeiro_count = self._import_financeiro(
                legacy,
                processo_map,
                assessor_default,
                actor,
            )
            respostas_count = self._import_respostas_formulario(
                legacy,
                processo_map,
                tipo_map,
            )

        self._print_validation_report(
            legacy=legacy,
            cliente_map=cliente_map,
            processo_map=processo_map,
            viagem_map=viagem_map,
            cliente_issues=cliente_issues,
            etapas_count=etapas_count,
            parceiros_linked_count=parceiros_linked_count,
            financeiro_count=financeiro_count,
            respostas_count=respostas_count,
        )

    def _get_legacy_connection(self):
        try:
            import pymysql
        except ImportError as exc:
            raise CommandError("pymysql nao instalado no .venv.") from exc

        env = {
            "host": os.environ.get("LEGACY_DB_HOST"),
            "port": int(os.environ.get("LEGACY_DB_PORT", "3306")),
            "database": os.environ.get("LEGACY_DB_NAME"),
            "user": os.environ.get("LEGACY_DB_USER"),
            "password": os.environ.get("LEGACY_DB_PASSWORD"),
        }
        missing = [key for key, value in env.items() if not value and key != "port"]
        if missing:
            raise CommandError(f"Variaveis LEGACY_DB_* ausentes: {', '.join(missing)}")

        try:
            return pymysql.connect(
                host=env["host"],
                port=env["port"],
                user=env["user"],
                password=env["password"],
                database=env["database"],
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
            )
        except Exception as exc:
            raise CommandError(f"Falha na conexao ao legado: {exc}") from exc

    def _load_legacy_data(self):
        conn = self._get_legacy_connection()
        cursor = conn.cursor()

        queries = {
            "clientes": """
                SELECT
                    c.*, u.email AS user_email, u.name AS user_name, u.password AS user_password,
                    ur.email AS responsavel_email, ur.name AS responsavel_name
                FROM clientes c
                LEFT JOIN users u ON u.id = c.usuario_id
                LEFT JOIN users ur ON ur.id = c.usuario_responsavel_id
                WHERE c.deleted_at IS NULL
            """,
            "familiares_clientes": "SELECT * FROM familiares_clientes",
            "processos": "SELECT * FROM processos WHERE deleted_at IS NULL",
            "processo_clientes": "SELECT * FROM processo_clientes",
            "cronograma_processos": "SELECT * FROM cronograma_processos WHERE deleted_at IS NULL",
            "situacao_processos": "SELECT * FROM situacao_processos",
            "passaportes": "SELECT * FROM passaportes WHERE deleted_at IS NULL",
            "informacoes_adicionais_viagems": "SELECT * FROM informacoes_adicionais_viagems WHERE deleted_at IS NULL",
            "informacoes_educacionais": "SELECT * FROM informacoes_educacionais WHERE deleted_at IS NULL",
            "dados_escolas": "SELECT * FROM dados_escolas WHERE deleted_at IS NULL",
            "dados_financeiros": "SELECT * FROM dados_financeiros WHERE deleted_at IS NULL",
            "dados_viagem_anteriores": "SELECT * FROM dados_viagem_anteriores WHERE deleted_at IS NULL",
            "dados_vistos_anteriores": "SELECT * FROM dados_vistos_anteriores WHERE deleted_at IS NULL",
            "saude_historico_imigracionals": "SELECT * FROM saude_historico_imigracionals WHERE deleted_at IS NULL",
            "pais": "SELECT * FROM pais WHERE deleted_at IS NULL",
            "tipo_vistos": "SELECT * FROM tipo_vistos WHERE deleted_at IS NULL",
            "pais_tipo_visto": "SELECT * FROM pais_tipo_visto",
            "parceiros": """
                SELECT p.*, u.email AS user_email, u.name AS user_name
                FROM parceiros p
                LEFT JOIN users u ON u.id = p.usuario_id
                WHERE p.deleted_at IS NULL
            """,
            "entradas": "SELECT * FROM entradas WHERE deleted_at IS NULL",
        }

        data = {}
        for key, sql in queries.items():
            cursor.execute(sql)
            data[key] = cursor.fetchall()
        conn.close()
        return data

    def _detect_blocking_anomalies(self, legacy):
        anomalies = []
        cpfs = [normalize_cpf(item.get("cpf")) for item in legacy["clientes"]]
        cpf_counter = Counter([cpf for cpf in cpfs if cpf])
        duplicates = [cpf for cpf, count in cpf_counter.items() if count > 1]
        missing = len([cpf for cpf in cpfs if not cpf])
        if missing:
            anomalies.append(f"{missing} clientes sem CPF valido (sera necessario CPF sintetico).")
        if duplicates:
            anomalies.append(
                f"{len(duplicates)} CPFs duplicados no legado (sera necessario CPF sintetico em parte dos registros)."
            )
        if not legacy["processos"]:
            anomalies.append("Tabela processos sem dados para importar.")
        return [] if len(anomalies) <= 2 else anomalies

    def _get_actor_user(self):
        user_model = get_user_model()
        user = user_model.objects.filter(is_superuser=True).order_by("id").first()
        if user:
            return user
        user, _ = user_model.objects.get_or_create(
            username="legacy-import",
            defaults={
                "email": "legacy-import@visary.local",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        return user

    def _import_paises(self, legacy, actor):
        def resolve_semantic_country(nome):
            target = normalize_text(nome)
            if not target:
                return None
            for pais in PaisDestino.objects.all():
                if normalize_text(pais.nome) == target:
                    return pais
            return None

        by_id = {}
        for row in legacy["pais"]:
            nome = str(row.get("nome") or "").strip()
            if not nome:
                continue
            semantic_country = resolve_semantic_country(nome)
            if semantic_country:
                pais = semantic_country
            else:
                pais, _ = PaisDestino.objects.get_or_create(
                    nome=nome,
                    defaults={
                        "codigo_iso": (row.get("sigla") or "")[:3],
                        "ativo": True,
                        "criado_por": actor,
                    },
                )
            pais.codigo_iso = (row.get("sigla") or pais.codigo_iso or "")[:3]
            pais.ativo = True
            pais.criado_por = actor
            pais.save()
            by_id[int(row["id"])] = pais
        return by_id

    def _import_tipos_visto(self, legacy, pais_map, actor):
        def resolve_semantic_tipo(pais, nome):
            target = normalize_text(nome)
            target_compact = normalize_semantic_key(nome)
            if not target:
                return None
            candidates = list(TipoVisto.objects.filter(pais_destino=pais))
            if not candidates:
                return None
            with_form = [
                candidate
                for candidate in candidates
                if FormularioVisto.objects.filter(tipo_visto=candidate, ativo=True).exists()
            ]
            pool = with_form or candidates
            for candidate in pool:
                if normalize_text(candidate.nome) == target:
                    return candidate
                if normalize_semantic_key(candidate.nome) == target_compact:
                    return candidate
            return None

        tipo_by_id = {}
        tipo_legacy = {int(item["id"]): item for item in legacy["tipo_vistos"]}
        for relation in legacy["pais_tipo_visto"]:
            pais_id = int(relation["pais_id"])
            tipo_id = int(relation["tipo_visto_id"])
            pais = pais_map.get(pais_id)
            tipo_row = tipo_legacy.get(tipo_id)
            if not pais or not tipo_row:
                continue
            nome = str(tipo_row.get("nome") or "").strip()
            if not nome:
                continue
            existing_semantic = resolve_semantic_tipo(pais, nome)
            if existing_semantic:
                tipo_by_id[tipo_id] = existing_semantic
                continue
            tipo, _ = TipoVisto.objects.get_or_create(
                pais_destino=pais,
                nome=nome,
                defaults={
                    "descricao": str(tipo_row.get("observacao") or ""),
                    "ativo": True,
                    "criado_por": actor,
                },
            )
            tipo.descricao = str(tipo_row.get("observacao") or tipo.descricao or "")
            tipo.ativo = True
            tipo.criado_por = actor
            tipo.save()
            tipo_by_id[tipo_id] = tipo
        return tipo_by_id

    def _parse_legacy_percentage(self, value) -> int:
        if value in (None, ""):
            return 0
        text = str(value).strip().replace("%", "")
        try:
            percentage = int(float(text))
        except ValueError:
            return 0
        return max(0, min(100, percentage))

    def _find_by_exact_marker(self, model_class, marker):
        for instance in model_class.objects.filter(observacoes__contains=marker.split("=")[0]):
            for line in str(instance.observacoes or "").splitlines():
                if line.strip() == marker:
                    return instance
        return None

    def _import_parceiros(self, legacy, actor):
        partner_map = {}
        for row in legacy["parceiros"]:
            partner_id = int(row["id"])
            email = str(row.get("user_email") or "").strip().lower()
            if not email:
                email = f"legacy-partner-{partner_id}@visary.local"
            partner, _ = Partner.objects.get_or_create(
                email=email,
                defaults={
                    "nome_responsavel": str(row.get("user_name") or row.get("empresa") or f"Parceiro {partner_id}"),
                    "nome_empresa": str(row.get("empresa") or ""),
                    "senha": "placeholder",
                    "segmento": self._normalize_segment(str(row.get("segmento") or "")),
                    "telefone": str(row.get("telefone") or ""),
                    "cidade": str(row.get("cidade") or ""),
                    "estado": str(row.get("estado") or "")[:2],
                    "criado_por": actor,
                },
            )
            partner.nome_responsavel = str(row.get("user_name") or partner.nome_responsavel)
            partner.nome_empresa = str(row.get("empresa") or "")
            partner.segmento = self._normalize_segment(str(row.get("segmento") or ""))
            partner.telefone = str(row.get("telefone") or "")
            partner.cidade = str(row.get("cidade") or "")
            partner.estado = str(row.get("estado") or "")[:2]
            partner.ativo = True
            partner.criado_por = actor
            partner.set_password(f"legacy-partner-{partner_id}")
            partner.save()
            partner_map[partner_id] = partner
        return partner_map

    def _normalize_segment(self, value: str) -> str:
        key = normalize_text(value).replace(" ", "_")
        allowed = {"agencia_viagem", "consultoria_imigracao", "advocacia", "educacao", "outros"}
        return key if key in allowed else "outros"

    def _build_assessor_lookup(self):
        assessores = UsuarioConsultoria.objects.filter(ativo=True).order_by("id")
        by_email = {}
        by_name = {}
        for assessor in assessores:
            email = str(assessor.email or "").strip().lower()
            nome = normalize_text(assessor.nome or "")
            if email:
                by_email[email] = assessor
            if nome:
                by_name[nome] = assessor
        return by_email, by_name

    def _resolve_assessor_for_cliente_row(self, row, assessor_default, by_email, by_name):
        responsavel_email = str(row.get("responsavel_email") or "").strip().lower()
        if responsavel_email and responsavel_email in by_email:
            return by_email[responsavel_email]

        responsavel_name = normalize_text(row.get("responsavel_name") or "")
        if responsavel_name and responsavel_name in by_name:
            return by_name[responsavel_name]

        for alias in ("raquel", "yan", "juliana"):
            if alias in responsavel_name:
                for nome_key, assessor in by_name.items():
                    if alias in nome_key:
                        return assessor

        return assessor_default

    def _import_clientes(self, legacy, assessor_default, actor):
        clientes = legacy["clientes"]
        by_email, by_name = self._build_assessor_lookup()
        cpf_counter = Counter()
        for row in clientes:
            cpf = normalize_cpf(row.get("cpf"))
            if cpf:
                cpf_counter[cpf] += 1

        cpf_seen = set()
        existing = ClienteConsultoria.objects.select_related("assessor_responsavel").all()
        by_legacy_id = {}
        for cliente in existing:
            meta = extract_legacy_meta(cliente.observacoes)
            if meta.get("legacy_cliente_id"):
                by_legacy_id[int(meta["legacy_cliente_id"])] = cliente

        cliente_map = {}
        issue_map = {}

        for row in clientes:
            legacy_id = int(row["id"])
            raw_cpf = normalize_cpf(row.get("cpf"))
            issues = []

            use_cpf = raw_cpf
            if not raw_cpf:
                use_cpf = synthetic_cpf(legacy_id)
                issues.append("CPF ausente no legado. CPF sintetico gerado.")
            elif cpf_counter[raw_cpf] > 1:
                if raw_cpf in cpf_seen:
                    use_cpf = synthetic_cpf(legacy_id)
                    issues.append(f"CPF duplicado no legado ({format_cpf(raw_cpf)}). CPF sintetico gerado.")
                else:
                    issues.append(f"CPF duplicado no legado ({format_cpf(raw_cpf)}). Este registro manteve o CPF original.")

            cpf_seen.add(raw_cpf)
            cpf_formatted = format_cpf(use_cpf)

            first_name = str(row.get("nome") or "").strip()
            last_name = str(row.get("sobrenome") or "").strip()
            if not first_name and not last_name:
                first_name = f"Cliente legado #{legacy_id}"

            cliente = by_legacy_id.get(legacy_id)
            if not cliente:
                cliente = ClienteConsultoria.objects.filter(cpf=cpf_formatted).first()

            if not cliente:
                cliente = ClienteConsultoria(
                    assessor_responsavel=assessor_default,
                    criado_por=actor,
                    nome=first_name,
                    sobrenome=last_name,
                    cpf=cpf_formatted,
                    data_nascimento=parse_date(row.get("nascimento")) or datetime(1990, 1, 1).date(),
                    nacionalidade=str(row.get("nacionalidade") or "Nao informado"),
                    telefone=str(row.get("telefone") or "000000000"),
                    senha=str(row.get("user_password") or "legacy-import"),
                )

            cliente.nome = first_name
            cliente.sobrenome = last_name
            cliente.cpf = cpf_formatted
            cliente.data_nascimento = parse_date(row.get("nascimento")) or cliente.data_nascimento
            cliente.nacionalidade = str(row.get("nacionalidade") or cliente.nacionalidade)
            cliente.telefone = str(row.get("telefone") or cliente.telefone)
            cliente.telefone_secundario = str(row.get("telefone_secundario") or "")[:20]
            cliente.email = str(row.get("user_email") or "").lower()
            cliente.cep = str(row.get("cep") or "")[:9]
            cliente.logradouro = str(row.get("endereco") or "")
            cliente.complemento = str(row.get("complemento") or "")
            cliente.bairro = str(row.get("bairro") or "")
            cliente.cidade = str(row.get("cidade") or "")
            cliente.uf = str(row.get("estado") or "")[:2]
            cliente.assessor_responsavel = self._resolve_assessor_for_cliente_row(
                row,
                assessor_default,
                by_email,
                by_name,
            )
            cliente.criado_por = actor
            if row.get("user_password"):
                cliente.senha = str(row["user_password"])

            meta = {
                "source": "legacy",
                "legacy_cliente_id": legacy_id,
                "imported": True,
                "status": "problem" if issues else "ok",
                "issues": issues,
            }
            cliente.observacoes = upsert_legacy_meta(cliente.observacoes, meta)
            cliente.save()

            cliente_map[legacy_id] = cliente
            issue_map[legacy_id] = issues

        return cliente_map, issue_map

    def _import_dependentes(self, legacy, cliente_map):
        for row in legacy["familiares_clientes"]:
            principal = cliente_map.get(int(row["id_cliente_principal"]))
            dependente = cliente_map.get(int(row["id_cliente_familiar"]))
            if not principal or not dependente or principal.pk == dependente.pk:
                continue
            if dependente.cliente_principal_id != principal.pk:
                dependente.cliente_principal = principal
                dependente.save(update_fields=["cliente_principal", "atualizado_em"])

    def _build_process_groups(self, legacy):
        process_ids = {int(process_row["id"]) for process_row in legacy["processos"]}
        child_to_principal = {}
        for row in legacy["processo_clientes"]:
            child_id = int(row["id_processo_cliente"])
            principal_id = int(row["id_processo_principal"])
            if child_id in process_ids:
                child_to_principal[child_id] = principal_id
        normalized = {}
        for process_id in process_ids:
            principal_id = child_to_principal.get(process_id, process_id)
            normalized[process_id] = principal_id if principal_id in process_ids else process_id
        return normalized

    def _import_viagens(self, legacy, cliente_map, tipo_map, pais_map, parceiro_map, assessor_default, actor):
        groups = self._build_process_groups(legacy)
        processos_by_id = {int(row["id"]): row for row in legacy["processos"]}
        group_rows = {}
        for process_id, principal_id in groups.items():
            if process_id not in processos_by_id:
                continue
            if principal_id not in group_rows:
                group_rows[principal_id] = processos_by_id[process_id]

        viagem_map = {}
        for group_id, process_row in group_rows.items():
            pais = pais_map.get(int(process_row["pais_id"]))
            tipo = tipo_map.get(int(process_row["tipo_visto_id"]))
            cliente_principal = cliente_map.get(int(process_row["cliente_id"]))
            assessor_viagem = (
                cliente_principal.assessor_responsavel
                if cliente_principal and cliente_principal.assessor_responsavel_id
                else assessor_default
            )
            if not pais or not tipo:
                continue
            marker = f"LEGACY_TRAVEL_GROUP_ID={group_id}"
            viagem = self._find_by_exact_marker(Viagem, marker)
            if not viagem:
                viagem = Viagem.objects.create(
                    assessor_responsavel=assessor_viagem,
                    pais_destino=pais,
                    tipo_visto=tipo,
                    data_prevista_viagem=parse_date(process_row.get("data_prevista_viagem")) or datetime(2030, 1, 1).date(),
                    data_prevista_retorno=parse_date(process_row.get("data_prevista_retorno")) or datetime(2030, 1, 2).date(),
                    valor_assessoria=Decimal("0"),
                    criado_por=actor,
                    observacoes=marker,
                )
            else:
                viagem.assessor_responsavel = assessor_viagem
                viagem.pais_destino = pais
                viagem.tipo_visto = tipo
                viagem.data_prevista_viagem = parse_date(process_row.get("data_prevista_viagem")) or viagem.data_prevista_viagem
                viagem.data_prevista_retorno = parse_date(process_row.get("data_prevista_retorno")) or viagem.data_prevista_retorno
                viagem.criado_por = actor
                if marker not in (viagem.observacoes or ""):
                    viagem.observacoes = f"{marker}\n{viagem.observacoes or ''}".strip()
                viagem.save()

            viagem_map[group_id] = viagem

        return viagem_map

    def _import_processos(self, legacy, cliente_map, viagem_map, tipo_map, assessor_default, actor):
        groups = self._build_process_groups(legacy)
        processo_map = {}
        for row in legacy["processos"]:
            process_id = int(row["id"])
            group_id = groups[process_id]
            viagem = viagem_map.get(group_id)
            cliente = cliente_map.get(int(row["cliente_id"]))
            if not viagem or not cliente:
                continue
            assessor_processo = (
                cliente.assessor_responsavel
                if cliente.assessor_responsavel_id
                else assessor_default
            )

            marker = f"LEGACY_PROCESS_ID={process_id}"
            processo = self._find_by_exact_marker(Processo, marker)
            if not processo:
                processo, _ = Processo.objects.get_or_create(
                    viagem=viagem,
                    cliente=cliente,
                    defaults={
                        "assessor_responsavel": assessor_processo,
                        "criado_por": actor,
                        "observacoes": marker,
                    },
                )
            if marker not in (processo.observacoes or ""):
                processo.observacoes = f"{marker}\n{processo.observacoes or ''}".strip()
            processo.assessor_responsavel = assessor_processo
            processo.criado_por = actor
            processo.save()

            tipo = tipo_map.get(int(row["tipo_visto_id"]))
            ClienteViagem.objects.update_or_create(
                viagem=viagem,
                cliente=cliente,
                defaults={"tipo_visto": tipo},
            )
            processo_map[process_id] = processo
        return processo_map

    def _collect_legacy_partner_links(self, legacy):
        links = {}
        for row in legacy["processos"]:
            cliente_id = row.get("cliente_id")
            parceiro_id = row.get("parceiro_id")
            if not cliente_id or not parceiro_id:
                continue
            cliente_id = int(cliente_id)
            parceiro_id = int(parceiro_id)
            links.setdefault(cliente_id, parceiro_id)
        return links

    def _link_clientes_parceiros(self, cliente_map, parceiro_map, parceiro_links):
        linked = 0
        for legacy_cliente_id, legacy_parceiro_id in parceiro_links.items():
            cliente = cliente_map.get(legacy_cliente_id)
            parceiro = parceiro_map.get(legacy_parceiro_id)
            if not cliente or not parceiro:
                continue
            if cliente.parceiro_indicador_id != parceiro.pk:
                cliente.parceiro_indicador = parceiro
                cliente.save(update_fields=["parceiro_indicador", "atualizado_em"])
            linked += 1
        return linked

    def _legacy_cronograma_maps(self, legacy):
        situacao_by_id = {
            int(row["id"]): normalize_text(row.get("nome"))
            for row in legacy["situacao_processos"]
            if row.get("id") is not None
        }
        cronograma_by_process = defaultdict(list)
        for row in legacy["cronograma_processos"]:
            process_id = row.get("processo_id")
            situacao_id = row.get("situacao_id")
            if not process_id or not situacao_id:
                continue
            cronograma_by_process[int(process_id)].append(row)
        for process_id in cronograma_by_process:
            cronograma_by_process[process_id].sort(
                key=lambda item: (
                    int(item.get("id") or 0),
                )
            )
        return situacao_by_id, cronograma_by_process

    def _build_expected_stage_state(self, statuses, status_by_name, cron_rows, situacao_by_id, fallback_conclusao_date):
        state = {}
        mapped_rows = []

        for cron_row in cron_rows:
            situacao_name = situacao_by_id.get(int(cron_row.get("situacao_id") or 0))
            if not situacao_name:
                continue
            status = status_by_name.get(situacao_name)
            if not status:
                continue

            prazo_dias_raw = str(cron_row.get("dias_prazo_finalizacao") or "").strip()
            prazo_dias = int(prazo_dias_raw) if prazo_dias_raw.isdigit() else status.prazo_padrao_dias
            concluida = cron_row.get("data_finalizacao") is not None
            data_conclusao = parse_date(cron_row.get("data_finalizacao")) if concluida else None

            state[status.pk] = {
                "concluida": concluida,
                "prazo_dias": prazo_dias,
                "data_conclusao": data_conclusao,
            }
            mapped_rows.append((status, concluida))

        if mapped_rows:
            current_status, current_done = mapped_rows[-1]
            if normalize_text(current_status.nome) != "processo cancelado":
                for status in statuses:
                    if status.ordem < current_status.ordem:
                        base_state = state.get(status.pk, {})
                        state[status.pk] = {
                            "concluida": True,
                            "prazo_dias": base_state.get("prazo_dias", status.prazo_padrao_dias),
                            "data_conclusao": base_state.get("data_conclusao") or fallback_conclusao_date,
                        }
                current_base = state.get(current_status.pk, {})
                state[current_status.pk] = {
                    "concluida": current_done,
                    "prazo_dias": current_base.get("prazo_dias", current_status.prazo_padrao_dias),
                    "data_conclusao": current_base.get("data_conclusao") or (fallback_conclusao_date if current_done else None),
                }

        return state

    def _build_status_name_map(self, tipo):
        statuses = list(StatusProcesso.objects.filter(ativo=True, tipo_visto=tipo).order_by("ordem", "id"))
        if not statuses:
            statuses = list(StatusProcesso.objects.filter(ativo=True, tipo_visto__isnull=True).order_by("ordem", "id"))
        by_name = {normalize_text(status.nome): status for status in statuses}
        return statuses, by_name

    def _import_etapas_processo(self, legacy, processo_map, tipo_map):
        updated = 0
        situacao_by_id, cronograma_by_process = self._legacy_cronograma_maps(legacy)
        for row in legacy["processos"]:
            process_id = int(row["id"])
            processo = processo_map.get(process_id)
            if not processo:
                continue

            tipo_visto_id = row.get("tipo_visto_id")
            if not tipo_visto_id:
                continue
            tipo = tipo_map.get(int(tipo_visto_id))
            if not tipo:
                continue

            statuses, status_by_name = self._build_status_name_map(tipo)
            if not statuses:
                continue

            cron_rows = cronograma_by_process.get(process_id, [])
            fallback_conclusao_date = parse_date(row.get("updated_at"))
            cronograma_state_by_status = self._build_expected_stage_state(
                statuses=statuses,
                status_by_name=status_by_name,
                cron_rows=cron_rows,
                situacao_by_id=situacao_by_id,
                fallback_conclusao_date=fallback_conclusao_date,
            )

            percentage = self._parse_legacy_percentage(row.get("percet_conclusao"))
            concluida_count = int(round((percentage / 100) * len(statuses)))
            concluida_count = max(0, min(len(statuses), concluida_count))

            for index, status in enumerate(statuses):
                if cron_rows:
                    stage_state = cronograma_state_by_status.get(
                        status.pk,
                        {
                            "concluida": False,
                            "prazo_dias": status.prazo_padrao_dias,
                            "data_conclusao": None,
                        },
                    )
                else:
                    stage_state = {
                        "concluida": index < concluida_count,
                        "prazo_dias": status.prazo_padrao_dias,
                        "data_conclusao": fallback_conclusao_date if index < concluida_count else None,
                    }

                EtapaProcesso.objects.update_or_create(
                    processo=processo,
                    status=status,
                    defaults={
                        "concluida": stage_state["concluida"],
                        "prazo_dias": stage_state["prazo_dias"],
                        "data_conclusao": stage_state["data_conclusao"],
                        "ordem": status.ordem,
                    },
                )
                updated += 1
        return updated

    def _import_financeiro(self, legacy, processo_map, assessor_default, actor):
        created_or_updated = 0
        for row in legacy["entradas"]:
            processo_id = row.get("processo_id")
            if not processo_id:
                continue
            processo = processo_map.get(int(processo_id))
            if not processo:
                continue

            marker = f"LEGACY_FINANCE_ENTRY_ID={int(row['id'])}"
            financeiro = self._find_by_exact_marker(Financeiro, marker)
            status = StatusFinanceiro.PAGO if parse_bool(row.get("pago")) else StatusFinanceiro.PENDENTE
            if not financeiro:
                financeiro, _ = Financeiro.objects.update_or_create(
                    viagem=processo.viagem,
                    cliente=processo.cliente,
                    defaults={
                        "assessor_responsavel": processo.assessor_responsavel,
                        "valor": parse_decimal(row.get("valor")),
                        "data_pagamento": parse_date(row.get("data")) if status == StatusFinanceiro.PAGO else None,
                        "status": status,
                        "observacoes": marker,
                        "criado_por": actor,
                    },
                )
            else:
                financeiro.assessor_responsavel = processo.assessor_responsavel
                financeiro.valor = parse_decimal(row.get("valor"))
                financeiro.data_pagamento = parse_date(row.get("data")) if status == StatusFinanceiro.PAGO else None
                financeiro.status = status
                financeiro.criado_por = actor
                if marker not in (financeiro.observacoes or ""):
                    financeiro.observacoes = f"{marker}\n{financeiro.observacoes or ''}".strip()
                financeiro.save()
            created_or_updated += 1
        return created_or_updated

    def _legacy_process_payload_maps(self, legacy):
        tables = [
            "passaportes",
            "informacoes_adicionais_viagems",
            "informacoes_educacionais",
            "dados_escolas",
            "dados_financeiros",
            "dados_viagem_anteriores",
            "dados_vistos_anteriores",
            "saude_historico_imigracionals",
        ]
        payload = {table: {} for table in tables}
        for table in tables:
            for row in legacy[table]:
                process_id = int(row["processo_id"])
                payload[table].setdefault(process_id, row)
        return payload

    def _extract_answer_value(self, question_text, context):
        q = normalize_text(question_text)
        cliente = context["cliente"]
        processo = context["processo"]
        passaporte = context.get("passaportes", {})
        escola = context.get("dados_escolas", {})
        financeiro = context.get("dados_financeiros", {})

        checks = [
            ("sobrenome", cliente.get("sobrenome")),
            ("nome", cliente.get("nome")),
            ("sexo", cliente.get("sexo")),
            ("estado civil", cliente.get("estado_civil")),
            ("data de nascimento", cliente.get("nascimento")),
            ("cidade natal", cliente.get("cidade_natal")),
            ("pais natal", cliente.get("pais_natal")),
            ("cpf", cliente.get("cpf")),
            ("endereco", cliente.get("endereco")),
            ("bairro", cliente.get("bairro")),
            ("cidade", cliente.get("cidade")),
            ("estado", cliente.get("estado")),
            ("cep", cliente.get("cep")),
            ("email", cliente.get("user_email")),
            ("telefone primario", cliente.get("telefone")),
            ("telefone secundario", cliente.get("telefone_secundario")),
            ("motivo da viagem", processo.get("motivo_viagem")),
            ("data de chegada", processo.get("data_prevista_viagem")),
            ("data da saida", processo.get("data_prevista_retorno")),
            ("quem custeara", financeiro.get("quem_custeara")),
            ("nome da escola", escola.get("nome")),
            ("curso", escola.get("curso")),
            ("endereco da escola", escola.get("endereco")),
            ("cidade da escola", escola.get("cidade")),
            ("estado da escola", escola.get("estado")),
            ("numero da sevis", escola.get("numero_sevis")),
            ("tipo de passaporte", passaporte.get("tipo_passaporte")),
            ("numero do passaporte", passaporte.get("numero")),
            ("orgao emissor", passaporte.get("orgao_emissor") or cliente.get("orgao_emissor")),
            ("pais emissor", passaporte.get("pais_emissor")),
            ("data emissao", passaporte.get("data_emissao")),
            ("data validade", passaporte.get("data_validade")),
            ("cidade emissao", passaporte.get("cidade_emissao")),
        ]

        for key, value in checks:
            if question_starts_with_key(q, key) and value not in (None, ""):
                return value

        generic_sources = [cliente, processo, passaporte, escola, financeiro]
        question_key = normalize_semantic_key(q)
        for source in generic_sources:
            if not isinstance(source, dict):
                continue
            for raw_key, raw_value in source.items():
                if raw_value in (None, ""):
                    continue
                key_norm = normalize_text(raw_key)
                if not key_norm:
                    continue
                key_semantic = normalize_semantic_key(raw_key)
                if key_norm == q or (question_key and key_semantic == question_key):
                    return raw_value
        return None

    def _import_respostas_formulario(self, legacy, processo_map, tipo_map):
        payload_maps = self._legacy_process_payload_maps(legacy)
        legacy_clientes_by_id = {
            int(item["id"]): item
            for item in legacy["clientes"]
            if item.get("id") is not None
        }
        total = 0
        for legacy_process in legacy["processos"]:
            process_id = int(legacy_process["id"])
            processo = processo_map.get(process_id)
            if not processo:
                continue

            tipo_visto_id = legacy_process.get("tipo_visto_id")
            if not tipo_visto_id:
                continue

            tipo = tipo_map.get(int(tipo_visto_id))
            if not tipo:
                continue
            formulario = FormularioVisto.objects.filter(tipo_visto=tipo, ativo=True).first()
            if not formulario:
                continue

            cliente_id = legacy_process.get("cliente_id")
            if not cliente_id:
                continue
            cliente_legacy = legacy_clientes_by_id.get(int(cliente_id))
            if not cliente_legacy:
                continue

            context = {
                "cliente": cliente_legacy,
                "processo": legacy_process,
            }
            for table_name, table_map in payload_maps.items():
                context[table_name] = table_map.get(process_id, {})

            perguntas = PerguntaFormulario.objects.filter(formulario=formulario, ativo=True).order_by("ordem")
            RespostaFormulario.objects.filter(
                viagem=processo.viagem,
                cliente=processo.cliente,
                pergunta__in=perguntas,
            ).delete()
            for pergunta in perguntas:
                answer = self._extract_answer_value(pergunta.pergunta, context)
                if answer in (None, ""):
                    continue

                defaults = {
                    "resposta_texto": "",
                    "resposta_data": None,
                    "resposta_numero": None,
                    "resposta_booleano": None,
                    "resposta_selecao": None,
                }

                if pergunta.tipo_campo == "data":
                    parsed_date = parse_date(answer)
                    if not parsed_date:
                        continue
                    defaults["resposta_data"] = parsed_date
                elif pergunta.tipo_campo == "numero":
                    parsed_number = parse_decimal_strict(answer)
                    if parsed_number is None:
                        continue
                    defaults["resposta_numero"] = parsed_number
                elif pergunta.tipo_campo == "booleano":
                    parsed_bool = parse_bool(answer)
                    if parsed_bool is None:
                        continue
                    defaults["resposta_booleano"] = parsed_bool
                elif pergunta.tipo_campo == "selecao":
                    selected = self._match_option(pergunta, answer)
                    if selected:
                        defaults["resposta_selecao"] = selected
                    else:
                        continue
                else:
                    defaults["resposta_texto"] = str(answer)

                RespostaFormulario.objects.update_or_create(
                    viagem=processo.viagem,
                    cliente=processo.cliente,
                    pergunta=pergunta,
                    defaults=defaults,
                )
                total += 1
        return total

    def _match_option(self, pergunta, value):
        needle = normalize_text(value)
        if not needle:
            return None
        options = OpcaoSelecao.objects.filter(pergunta=pergunta, ativo=True).order_by("ordem")
        exact = None
        partial = None
        for option in options:
            text = normalize_text(option.texto)
            if text == needle:
                exact = option
                break
            if needle in text and partial is None:
                partial = option
        return exact or partial

    def _strict_sql_orm_validation(self, legacy, cliente_map, processo_map):
        legacy_process_map = {
            int(row["id"]): row
            for row in legacy["processos"]
            if row.get("id") is not None
        }
        payload_maps = self._legacy_process_payload_maps(legacy)
        legacy_client_map = {
            int(row["id"]): row
            for row in legacy["clientes"]
            if row.get("id") is not None
        }
        situacao_by_id, cronograma_by_process = self._legacy_cronograma_maps(legacy)

        stage_mismatches = []
        for process_id, processo in processo_map.items():
            legacy_row = legacy_process_map.get(process_id)
            if not legacy_row:
                stage_mismatches.append(f"Processo legado {process_id} nao encontrado para comparar etapas")
                continue

            tipo_legacy_id = legacy_row.get("tipo_visto_id")
            if not tipo_legacy_id:
                continue

            tipo_viagem = processo.viagem.tipo_visto
            statuses, status_by_name = self._build_status_name_map(tipo_viagem)
            if not statuses:
                continue

            cronograma_state_by_status = {}
            cron_rows = cronograma_by_process.get(process_id, [])
            fallback_conclusao_date = parse_date(legacy_row.get("updated_at"))
            cronograma_state_by_status = self._build_expected_stage_state(
                statuses=statuses,
                status_by_name=status_by_name,
                cron_rows=cron_rows,
                situacao_by_id=situacao_by_id,
                fallback_conclusao_date=fallback_conclusao_date,
            )

            percentage = self._parse_legacy_percentage(legacy_row.get("percet_conclusao"))
            concluida_count = int(round((percentage / 100) * len(statuses)))
            concluida_count = max(0, min(len(statuses), concluida_count))

            for index, status in enumerate(statuses):
                if cron_rows:
                    expected_done = cronograma_state_by_status.get(status.pk, {}).get("concluida", False)
                else:
                    expected_done = index < concluida_count
                etapa = EtapaProcesso.objects.filter(processo=processo, status=status).first()
                if not etapa:
                    stage_mismatches.append(
                        f"Processo {process_id}: etapa '{status.nome}' ausente no ORM"
                    )
                    continue
                if etapa.concluida != expected_done:
                    stage_mismatches.append(
                        f"Processo {process_id}: etapa '{status.nome}' esperado={expected_done} orm={etapa.concluida}"
                    )

        partner_mismatches = []
        legacy_partner_by_id = {
            int(row["id"]): str(row.get("user_email") or "").strip().lower()
            for row in legacy["parceiros"]
            if row.get("id") is not None
        }
        expected_links = self._collect_legacy_partner_links(legacy)
        for legacy_cliente_id, legacy_partner_id in expected_links.items():
            cliente = cliente_map.get(legacy_cliente_id)
            if not cliente or not cliente.parceiro_indicador_id:
                partner_mismatches.append(
                    f"Cliente legado {legacy_cliente_id}: parceiro ausente no ORM"
                )
                continue
            expected_email = legacy_partner_by_id.get(legacy_partner_id)
            current_email = str(cliente.parceiro_indicador.email or "").strip().lower()
            if expected_email and expected_email != current_email:
                partner_mismatches.append(
                    f"Cliente legado {legacy_cliente_id}: parceiro esperado={expected_email} orm={current_email}"
                )

        form_mismatches = []
        critical_form_aliases = (
            "orgao emissor",
            "numero do passaporte",
            "pais emissor",
            "data emissao",
            "data validade",
            "cidade emissao",
        )
        for process_id, processo in processo_map.items():
            legacy_row = legacy_process_map.get(process_id)
            if not legacy_row:
                continue
            expected_concluded_form = parse_bool(legacy_row.get("conclusao_formulario")) is True
            orm_qs = RespostaFormulario.objects.filter(
                viagem=processo.viagem,
                cliente=processo.cliente,
            )
            orm_response_count = orm_qs.count()
            if expected_concluded_form and orm_response_count == 0:
                form_mismatches.append(
                    f"Processo {process_id}: legado conclusao_formulario=1 mas ORM sem respostas"
                )

            formulario = FormularioVisto.objects.filter(tipo_visto=processo.viagem.tipo_visto, ativo=True).first()
            legacy_cliente = legacy_client_map.get(int(legacy_row.get("cliente_id") or 0))
            if not formulario or not legacy_cliente:
                continue

            context = {
                "cliente": legacy_cliente,
                "processo": legacy_row,
            }
            for table_name, table_map in payload_maps.items():
                context[table_name] = table_map.get(process_id, {})

            for pergunta in PerguntaFormulario.objects.filter(formulario=formulario, ativo=True).order_by("ordem"):
                question_key = normalize_text(pergunta.pergunta)
                if not any(alias in question_key for alias in critical_form_aliases):
                    continue
                expected_value = self._extract_answer_value(pergunta.pergunta, context)
                if expected_value in (None, ""):
                    continue
                resposta = orm_qs.filter(pergunta=pergunta).first()
                if not resposta:
                    form_mismatches.append(
                        f"Processo {process_id}: pergunta '{pergunta.pergunta}' sem resposta no ORM"
                    )
                    continue

                if pergunta.tipo_campo == "data":
                    expected_date = parse_date(expected_value)
                    if expected_date and resposta.resposta_data != expected_date:
                        form_mismatches.append(
                            f"Processo {process_id}: pergunta '{pergunta.pergunta}' data esperada={expected_date} orm={resposta.resposta_data}"
                        )
                elif pergunta.tipo_campo == "numero":
                    expected_number = parse_decimal_strict(expected_value)
                    if expected_number is not None and resposta.resposta_numero != expected_number:
                        form_mismatches.append(
                            f"Processo {process_id}: pergunta '{pergunta.pergunta}' numero esperado={expected_number} orm={resposta.resposta_numero}"
                        )
                elif pergunta.tipo_campo == "booleano":
                    expected_bool = parse_bool(expected_value)
                    if expected_bool is not None and resposta.resposta_booleano != expected_bool:
                        form_mismatches.append(
                            f"Processo {process_id}: pergunta '{pergunta.pergunta}' booleano esperado={expected_bool} orm={resposta.resposta_booleano}"
                        )
                elif pergunta.tipo_campo == "selecao":
                    expected_option = self._match_option(pergunta, expected_value)
                    if expected_option and resposta.resposta_selecao_id != expected_option.pk:
                        form_mismatches.append(
                            f"Processo {process_id}: pergunta '{pergunta.pergunta}' selecao esperada={expected_option.texto} orm={resposta.get_resposta_display()}"
                        )
                else:
                    expected_text_key = normalize_semantic_key(expected_value)
                    actual_text_key = normalize_semantic_key(resposta.resposta_texto)
                    if expected_text_key and actual_text_key and expected_text_key != actual_text_key:
                        form_mismatches.append(
                            f"Processo {process_id}: pergunta '{pergunta.pergunta}' texto esperado={expected_value} orm={resposta.resposta_texto}"
                        )

        return {
            "stage_mismatches": stage_mismatches,
            "partner_mismatches": partner_mismatches,
            "form_mismatches": form_mismatches,
        }

    def _print_validation_report(
        self,
        legacy,
        cliente_map,
        processo_map,
        viagem_map,
        cliente_issues,
        etapas_count,
        parceiros_linked_count,
        financeiro_count,
        respostas_count,
    ):
        issues_total = sum(1 for _, issues in cliente_issues.items() if issues)
        legacy_clients = len(legacy["clientes"])
        legacy_processes = len(legacy["processos"])
        legacy_groups = len(set(self._build_process_groups(legacy).values()))

        self.stdout.write("\n================= VALIDACAO LEGADO -> VISARY =================")
        self.stdout.write(f"SQL legado clientes: {legacy_clients}")
        self.stdout.write(f"ORM importados clientes: {len(cliente_map)}")
        self.stdout.write(f"SQL legado processos: {legacy_processes}")
        self.stdout.write(f"ORM importados processos: {len(processo_map)}")
        self.stdout.write(f"SQL legado grupos de viagem: {legacy_groups}")
        self.stdout.write(f"ORM importadas viagens: {len(viagem_map)}")
        self.stdout.write(f"ORM etapas de processo atualizadas/criadas: {etapas_count}")
        self.stdout.write(f"Clientes com parceiro legado vinculado: {parceiros_linked_count}")
        self.stdout.write(f"ORM financeiro atualizados/criados: {financeiro_count}")
        self.stdout.write(f"ORM respostas de formulario atualizadas/criadas: {respostas_count}")
        self.stdout.write(f"Clientes com inconsistencia de CPF marcada: {issues_total}")
        assessor_counter = Counter(
            cliente.assessor_responsavel.nome
            for cliente in cliente_map.values()
            if cliente.assessor_responsavel_id
        )
        for assessor_nome, quantidade in assessor_counter.items():
            self.stdout.write(f"Clientes vinculados ao assessor {assessor_nome}: {quantidade}")

        strict_report = self._strict_sql_orm_validation(
            legacy=legacy,
            cliente_map=cliente_map,
            processo_map=processo_map,
        )
        stage_issues = strict_report["stage_mismatches"]
        partner_issues = strict_report["partner_mismatches"]
        form_issues = strict_report["form_mismatches"]

        self.stdout.write(f"Validacao rigorosa etapas (divergencias): {len(stage_issues)}")
        self.stdout.write(f"Validacao rigorosa parceiros (divergencias): {len(partner_issues)}")
        self.stdout.write(f"Validacao rigorosa formularios (divergencias): {len(form_issues)}")
        for line in stage_issues[:5]:
            self.stdout.write(f" - {line}")
        for line in partner_issues[:5]:
            self.stdout.write(f" - {line}")
        for line in form_issues[:5]:
            self.stdout.write(f" - {line}")

        if (
            len(cliente_map) == legacy_clients
            and len(processo_map) == legacy_processes
            and len(viagem_map) == legacy_groups
            and not stage_issues
            and not partner_issues
            and not form_issues
        ):
            self.stdout.write(self.style.SUCCESS("OK: importacao principal consistente com legado."))
        else:
            raise CommandError(
                "Validacao rigorosa falhou: divergencias encontradas entre SQL legado e ORM. "
                "Revise o relatorio detalhado acima."
            )
