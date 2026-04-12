import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from system.models import (
    ConsultancyClient,
    ConsultancyUser,
    DestinationCountry,
    FinancialRecord,
    FinancialStatus,
    FormAnswer,
    FormQuestion,
    Partner,
    Process,
    ProcessStage,
    ProcessStatus,
    SelectOption,
    Trip,
    TripClient,
    VisaForm,
    VisaType,
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
        default_advisor = ConsultancyUser.objects.filter(is_active=True).order_by("id").first()
        if not default_advisor:
            raise CommandError(
                "Nao existe ConsultancyUser ativo para vincular assigned_advisor. "
                "Rode seed_consultancy_users antes de seed_legacy."
            )

        with transaction.atomic():
            country_map = self._import_countries(legacy, actor)
            visa_type_map = self._import_visa_types(legacy, country_map, actor)
            partner_map = self._import_partners(legacy, actor)
            client_map, client_issues = self._import_clients(
                legacy,
                default_advisor,
                actor,
            )
            self._import_dependents(legacy, client_map)
            trip_map = self._import_trips(
                legacy,
                client_map,
                visa_type_map,
                country_map,
                partner_map,
                default_advisor,
                actor,
            )
            partner_links = self._collect_legacy_partner_links(legacy)
            partners_linked_count = self._link_clients_partners(
                client_map,
                partner_map,
                partner_links,
            )
            process_map = self._import_processes(
                legacy,
                client_map,
                trip_map,
                visa_type_map,
                default_advisor,
                actor,
            )
            stages_count = self._import_process_stages(
                legacy,
                process_map,
                visa_type_map,
            )
            financial_count = self._import_financial(
                legacy,
                process_map,
                default_advisor,
                actor,
            )
            answers_count = self._import_form_answers(
                legacy,
                process_map,
                visa_type_map,
            )

        self._print_validation_report(
            legacy=legacy,
            client_map=client_map,
            process_map=process_map,
            trip_map=trip_map,
            client_issues=client_issues,
            stages_count=stages_count,
            partners_linked_count=partners_linked_count,
            financial_count=financial_count,
            answers_count=answers_count,
        )

    def _get_legacy_connection(self):
        try:
            import pymysql
        except ImportError as exc:
            raise CommandError("pymysql nao instalado no .venv.") from exc

        env = {
            "host": settings.LEGACY_DB_HOST or None,
            "port": int(settings.LEGACY_DB_PORT or "3306"),
            "database": settings.LEGACY_DB_NAME or None,
            "user": settings.LEGACY_DB_USER or None,
            "password": settings.LEGACY_DB_PASSWORD or None,
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

    def _import_countries(self, legacy, actor):
        def resolve_semantic_country(raw_name):
            target = normalize_text(raw_name)
            if not target:
                return None
            for country in DestinationCountry.objects.all():
                if normalize_text(country.name) == target:
                    return country
            return None

        by_id = {}
        for row in legacy["pais"]:
            raw_name = str(row.get("nome") or "").strip()
            if not raw_name:
                continue
            semantic_country = resolve_semantic_country(raw_name)
            if semantic_country:
                country = semantic_country
            else:
                country, _ = DestinationCountry.objects.get_or_create(
                    name=raw_name,
                    defaults={
                        "iso_code": (row.get("sigla") or "")[:3],
                        "is_active": True,
                        "created_by": actor,
                    },
                )
            country.iso_code = (row.get("sigla") or country.iso_code or "")[:3]
            country.is_active = True
            country.created_by = actor
            country.save()
            by_id[int(row["id"])] = country
        return by_id

    def _import_visa_types(self, legacy, country_map, actor):
        def resolve_semantic_visa_type(country, raw_name):
            target = normalize_text(raw_name)
            target_compact = normalize_semantic_key(raw_name)
            if not target:
                return None
            candidates = list(VisaType.objects.filter(destination_country=country))
            if not candidates:
                return None
            with_form = [
                c for c in candidates
                if VisaForm.objects.filter(visa_type=c, is_active=True).exists()
            ]
            pool = with_form or candidates
            for c in pool:
                if normalize_text(c.name) == target:
                    return c
                if normalize_semantic_key(c.name) == target_compact:
                    return c
            return None

        vt_by_id = {}
        vt_legacy = {int(item["id"]): item for item in legacy["tipo_vistos"]}
        for relation in legacy["pais_tipo_visto"]:
            country_id = int(relation["pais_id"])
            vt_id = int(relation["tipo_visto_id"])
            country = country_map.get(country_id)
            vt_row = vt_legacy.get(vt_id)
            if not country or not vt_row:
                continue
            raw_name = str(vt_row.get("nome") or "").strip()
            if not raw_name:
                continue
            existing = resolve_semantic_visa_type(country, raw_name)
            if existing:
                vt_by_id[vt_id] = existing
                continue
            vt, _ = VisaType.objects.get_or_create(
                destination_country=country,
                name=raw_name,
                defaults={
                    "description": str(vt_row.get("observacao") or ""),
                    "is_active": True,
                    "created_by": actor,
                },
            )
            vt.description = str(vt_row.get("observacao") or vt.description or "")
            vt.is_active = True
            vt.created_by = actor
            vt.save()
            vt_by_id[vt_id] = vt
        return vt_by_id

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
        for instance in model_class.objects.filter(notes__contains=marker.split("=")[0]):
            for line in str(instance.notes or "").splitlines():
                if line.strip() == marker:
                    return instance
        return None

    def _import_partners(self, legacy, actor):
        partner_map = {}
        for row in legacy["parceiros"]:
            partner_id = int(row["id"])
            email = str(row.get("user_email") or "").strip().lower()
            if not email:
                email = f"legacy-partner-{partner_id}@visary.local"
            partner, _ = Partner.objects.get_or_create(
                email=email,
                defaults={
                    "contact_name": str(row.get("user_name") or row.get("empresa") or f"Parceiro {partner_id}"),
                    "company_name": str(row.get("empresa") or ""),
                    "password": "placeholder",
                    "segment": self._normalize_segment(str(row.get("segmento") or "")),
                    "phone": str(row.get("telefone") or ""),
                    "city": str(row.get("cidade") or ""),
                    "state": str(row.get("estado") or "")[:2],
                    "created_by": actor,
                },
            )
            partner.contact_name = str(row.get("user_name") or partner.contact_name)
            partner.company_name = str(row.get("empresa") or "")
            partner.segment = self._normalize_segment(str(row.get("segmento") or ""))
            partner.phone = str(row.get("telefone") or "")
            partner.city = str(row.get("cidade") or "")
            partner.state = str(row.get("estado") or "")[:2]
            partner.is_active = True
            partner.created_by = actor
            partner.set_password(f"legacy-partner-{partner_id}")
            partner.save()
            partner_map[partner_id] = partner
        return partner_map

    def _normalize_segment(self, value: str) -> str:
        key = normalize_text(value).replace(" ", "_")
        allowed = {"travel_agency", "immigration_consulting", "law", "education", "other"}
        legacy_map = {
            "agencia_viagem": "travel_agency",
            "consultoria_imigracao": "immigration_consulting",
            "advocacia": "law",
            "educacao": "education",
            "outros": "other",
        }
        mapped = legacy_map.get(key, key)
        return mapped if mapped in allowed else "other"

    def _build_advisor_lookup(self):
        advisors = ConsultancyUser.objects.filter(is_active=True).order_by("id")
        by_email = {}
        by_name = {}
        for advisor in advisors:
            email = str(advisor.email or "").strip().lower()
            name_key = normalize_text(advisor.name or "")
            if email:
                by_email[email] = advisor
            if name_key:
                by_name[name_key] = advisor
        return by_email, by_name

    def _resolve_advisor_for_client_row(self, row, default_advisor, by_email, by_name):
        responsible_email = str(row.get("responsavel_email") or "").strip().lower()
        if responsible_email and responsible_email in by_email:
            return by_email[responsible_email]

        responsible_name = normalize_text(row.get("responsavel_name") or "")
        if responsible_name and responsible_name in by_name:
            return by_name[responsible_name]

        for alias in ("raquel", "yan", "juliana"):
            if alias in responsible_name:
                for name_key, advisor in by_name.items():
                    if alias in name_key:
                        return advisor

        return default_advisor

    def _import_clients(self, legacy, default_advisor, actor):
        clientes = legacy["clientes"]
        by_email, by_name = self._build_advisor_lookup()
        cpf_counter = Counter()
        for row in clientes:
            cpf = normalize_cpf(row.get("cpf"))
            if cpf:
                cpf_counter[cpf] += 1

        cpf_seen = set()
        existing = ConsultancyClient.objects.select_related("assigned_advisor").all()
        by_legacy_id = {}
        for client in existing:
            meta = extract_legacy_meta(client.notes)
            if meta.get("legacy_cliente_id"):
                by_legacy_id[int(meta["legacy_cliente_id"])] = client

        client_map = {}
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

            client = by_legacy_id.get(legacy_id)
            if not client:
                client = ConsultancyClient.objects.filter(cpf=cpf_formatted).first()

            if not client:
                client = ConsultancyClient(
                    assigned_advisor=default_advisor,
                    created_by=actor,
                    first_name=first_name,
                    last_name=last_name,
                    cpf=cpf_formatted,
                    birth_date=parse_date(row.get("nascimento")) or datetime(1990, 1, 1).date(),
                    nationality=str(row.get("nacionalidade") or "Nao informado"),
                    phone=str(row.get("telefone") or "000000000"),
                    password=str(row.get("user_password") or "legacy-import"),
                )

            client.first_name = first_name
            client.last_name = last_name
            client.cpf = cpf_formatted
            client.birth_date = parse_date(row.get("nascimento")) or client.birth_date
            client.nationality = str(row.get("nacionalidade") or client.nationality)
            client.phone = str(row.get("telefone") or client.phone)
            client.secondary_phone = str(row.get("telefone_secundario") or "")[:20]
            client.email = str(row.get("user_email") or "").lower()
            client.zip_code = str(row.get("cep") or "")[:9]
            client.street = str(row.get("endereco") or "")
            client.complement = str(row.get("complemento") or "")
            client.district = str(row.get("bairro") or "")
            client.city = str(row.get("cidade") or "")
            client.state = str(row.get("estado") or "")[:2]
            client.assigned_advisor = self._resolve_advisor_for_client_row(
                row,
                default_advisor,
                by_email,
                by_name,
            )
            client.created_by = actor
            if row.get("user_password"):
                client.password = str(row["user_password"])

            meta = {
                "source": "legacy",
                "legacy_cliente_id": legacy_id,
                "imported": True,
                "status": "problem" if issues else "ok",
                "issues": issues,
            }
            client.notes = upsert_legacy_meta(client.notes, meta)
            client.save()

            client_map[legacy_id] = client
            issue_map[legacy_id] = issues

        return client_map, issue_map

    def _import_dependents(self, legacy, client_map):
        for row in legacy["familiares_clientes"]:
            principal = client_map.get(int(row["id_cliente_principal"]))
            dependent = client_map.get(int(row["id_cliente_familiar"]))
            if not principal or not dependent or principal.pk == dependent.pk:
                continue
            if dependent.primary_client_id != principal.pk:
                dependent.primary_client = principal
                dependent.save(update_fields=["primary_client", "updated_at"])

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

    def _import_trips(self, legacy, client_map, visa_type_map, country_map, partner_map, default_advisor, actor):
        groups = self._build_process_groups(legacy)
        processes_by_id = {int(row["id"]): row for row in legacy["processos"]}
        group_rows = {}
        for process_id, principal_id in groups.items():
            if process_id not in processes_by_id:
                continue
            if principal_id not in group_rows:
                group_rows[principal_id] = processes_by_id[process_id]

        trip_map = {}
        for group_id, process_row in group_rows.items():
            country = country_map.get(int(process_row["pais_id"]))
            vt = visa_type_map.get(int(process_row["tipo_visto_id"]))
            principal_client = client_map.get(int(process_row["cliente_id"]))
            trip_advisor = (
                principal_client.assigned_advisor
                if principal_client and principal_client.assigned_advisor_id
                else default_advisor
            )
            if not country or not vt:
                continue
            marker = f"LEGACY_TRAVEL_GROUP_ID={group_id}"
            trip = self._find_by_exact_marker(Trip, marker)
            if not trip:
                trip = Trip.objects.create(
                    assigned_advisor=trip_advisor,
                    destination_country=country,
                    visa_type=vt,
                    planned_departure_date=parse_date(process_row.get("data_prevista_viagem")) or datetime(2030, 1, 1).date(),
                    planned_return_date=parse_date(process_row.get("data_prevista_retorno")) or datetime(2030, 1, 2).date(),
                    advisory_fee=Decimal("0"),
                    created_by=actor,
                    notes=marker,
                )
            else:
                trip.assigned_advisor = trip_advisor
                trip.destination_country = country
                trip.visa_type = vt
                trip.planned_departure_date = parse_date(process_row.get("data_prevista_viagem")) or trip.planned_departure_date
                trip.planned_return_date = parse_date(process_row.get("data_prevista_retorno")) or trip.planned_return_date
                trip.created_by = actor
                if marker not in (trip.notes or ""):
                    trip.notes = f"{marker}\n{trip.notes or ''}".strip()
                trip.save()

            trip_map[group_id] = trip

        return trip_map

    def _import_processes(self, legacy, client_map, trip_map, visa_type_map, default_advisor, actor):
        groups = self._build_process_groups(legacy)
        process_map = {}
        for row in legacy["processos"]:
            process_id = int(row["id"])
            group_id = groups[process_id]
            trip = trip_map.get(group_id)
            client = client_map.get(int(row["cliente_id"]))
            if not trip or not client:
                continue
            process_advisor = (
                client.assigned_advisor
                if client.assigned_advisor_id
                else default_advisor
            )

            marker = f"LEGACY_PROCESS_ID={process_id}"
            process = self._find_by_exact_marker(Process, marker)
            if not process:
                process, _ = Process.objects.get_or_create(
                    trip=trip,
                    client=client,
                    defaults={
                        "assigned_advisor": process_advisor,
                        "created_by": actor,
                        "notes": marker,
                    },
                )
            if marker not in (process.notes or ""):
                process.notes = f"{marker}\n{process.notes or ''}".strip()
            process.assigned_advisor = process_advisor
            process.created_by = actor
            process.save()

            vt = visa_type_map.get(int(row["tipo_visto_id"]))
            TripClient.objects.update_or_create(
                trip=trip,
                client=client,
                defaults={"visa_type": vt},
            )
            process_map[process_id] = process
        return process_map

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

    def _link_clients_partners(self, client_map, partner_map, partner_links):
        linked = 0
        for legacy_client_id, legacy_partner_id in partner_links.items():
            client = client_map.get(legacy_client_id)
            partner = partner_map.get(legacy_partner_id)
            if not client or not partner:
                continue
            if client.referring_partner_id != partner.pk:
                client.referring_partner = partner
                client.save(update_fields=["referring_partner", "updated_at"])
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

    def _build_expected_stage_state(self, statuses, status_by_name, cron_rows, situacao_by_id, fallback_date):
        state = {}
        mapped_rows = []

        for cron_row in cron_rows:
            situacao_name = situacao_by_id.get(int(cron_row.get("situacao_id") or 0))
            if not situacao_name:
                continue
            status = status_by_name.get(situacao_name)
            if not status:
                continue

            raw_days = str(cron_row.get("dias_prazo_finalizacao") or "").strip()
            days = int(raw_days) if raw_days.isdigit() else status.default_deadline_days
            done = cron_row.get("data_finalizacao") is not None
            completion = parse_date(cron_row.get("data_finalizacao")) if done else None

            state[status.pk] = {
                "completed": done,
                "deadline_days": days,
                "completion_date": completion,
            }
            mapped_rows.append((status, done))

        if mapped_rows:
            current_status, current_done = mapped_rows[-1]
            if normalize_text(current_status.name) != "processo cancelado":
                for status in statuses:
                    if status.order < current_status.order:
                        base = state.get(status.pk, {})
                        state[status.pk] = {
                            "completed": True,
                            "deadline_days": base.get("deadline_days", status.default_deadline_days),
                            "completion_date": base.get("completion_date") or fallback_date,
                        }
                current_base = state.get(current_status.pk, {})
                state[current_status.pk] = {
                    "completed": current_done,
                    "deadline_days": current_base.get("deadline_days", current_status.default_deadline_days),
                    "completion_date": current_base.get("completion_date") or (fallback_date if current_done else None),
                }

        return state

    def _build_status_name_map(self, visa_type):
        statuses = list(ProcessStatus.objects.filter(is_active=True, visa_type=visa_type).order_by("order", "id"))
        if not statuses:
            statuses = list(ProcessStatus.objects.filter(is_active=True, visa_type__isnull=True).order_by("order", "id"))
        by_name = {normalize_text(s.name): s for s in statuses}
        return statuses, by_name

    def _import_process_stages(self, legacy, process_map, visa_type_map):
        updated = 0
        situacao_by_id, cronograma_by_process = self._legacy_cronograma_maps(legacy)
        for row in legacy["processos"]:
            process_id = int(row["id"])
            process = process_map.get(process_id)
            if not process:
                continue

            vt_id = row.get("tipo_visto_id")
            if not vt_id:
                continue
            vt = visa_type_map.get(int(vt_id))
            if not vt:
                continue

            statuses, status_by_name = self._build_status_name_map(vt)
            if not statuses:
                continue

            cron_rows = cronograma_by_process.get(process_id, [])
            fallback_date = parse_date(row.get("updated_at"))
            stage_state_by_status = self._build_expected_stage_state(
                statuses=statuses,
                status_by_name=status_by_name,
                cron_rows=cron_rows,
                situacao_by_id=situacao_by_id,
                fallback_date=fallback_date,
            )

            percentage = self._parse_legacy_percentage(row.get("percet_conclusao"))
            done_count = int(round((percentage / 100) * len(statuses)))
            done_count = max(0, min(len(statuses), done_count))

            for index, status in enumerate(statuses):
                if cron_rows:
                    stage_state = stage_state_by_status.get(
                        status.pk,
                        {
                            "completed": False,
                            "deadline_days": status.default_deadline_days,
                            "completion_date": None,
                        },
                    )
                else:
                    stage_state = {
                        "completed": index < done_count,
                        "deadline_days": status.default_deadline_days,
                        "completion_date": fallback_date if index < done_count else None,
                    }

                ProcessStage.objects.update_or_create(
                    process=process,
                    status=status,
                    defaults={
                        "completed": stage_state["completed"],
                        "deadline_days": stage_state["deadline_days"],
                        "completion_date": stage_state["completion_date"],
                        "order": status.order,
                    },
                )
                updated += 1
        return updated

    def _import_financial(self, legacy, process_map, default_advisor, actor):
        created_or_updated = 0
        for row in legacy["entradas"]:
            process_id = row.get("processo_id")
            if not process_id:
                continue
            process = process_map.get(int(process_id))
            if not process:
                continue

            marker = f"LEGACY_FINANCE_ENTRY_ID={int(row['id'])}"
            record = self._find_by_exact_marker(FinancialRecord, marker)
            status = FinancialStatus.PAID if parse_bool(row.get("pago")) else FinancialStatus.PENDING
            if not record:
                record, _ = FinancialRecord.objects.update_or_create(
                    trip=process.trip,
                    client=process.client,
                    defaults={
                        "assigned_advisor": process.assigned_advisor,
                        "amount": parse_decimal(row.get("valor")),
                        "payment_date": parse_date(row.get("data")) if status == FinancialStatus.PAID else None,
                        "status": status,
                        "notes": marker,
                        "created_by": actor,
                    },
                )
            else:
                record.assigned_advisor = process.assigned_advisor
                record.amount = parse_decimal(row.get("valor"))
                record.payment_date = parse_date(row.get("data")) if status == FinancialStatus.PAID else None
                record.status = status
                record.created_by = actor
                if marker not in (record.notes or ""):
                    record.notes = f"{marker}\n{record.notes or ''}".strip()
                record.save()
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

    def _import_form_answers(self, legacy, process_map, visa_type_map):
        payload_maps = self._legacy_process_payload_maps(legacy)
        legacy_clients_by_id = {
            int(item["id"]): item
            for item in legacy["clientes"]
            if item.get("id") is not None
        }
        total = 0
        for legacy_process in legacy["processos"]:
            process_id = int(legacy_process["id"])
            process = process_map.get(process_id)
            if not process:
                continue

            vt_id = legacy_process.get("tipo_visto_id")
            if not vt_id:
                continue

            vt = visa_type_map.get(int(vt_id))
            if not vt:
                continue
            form = VisaForm.objects.filter(visa_type=vt, is_active=True).first()
            if not form:
                continue

            client_id = legacy_process.get("cliente_id")
            if not client_id:
                continue
            legacy_client = legacy_clients_by_id.get(int(client_id))
            if not legacy_client:
                continue

            context = {
                "cliente": legacy_client,
                "processo": legacy_process,
            }
            for table_name, table_map in payload_maps.items():
                context[table_name] = table_map.get(process_id, {})

            questions = FormQuestion.objects.filter(form=form, is_active=True).order_by("order")
            FormAnswer.objects.filter(
                trip=process.trip,
                client=process.client,
                question__in=questions,
            ).delete()
            for question in questions:
                answer = self._extract_answer_value(question.question, context)
                if answer in (None, ""):
                    continue

                defaults = {
                    "answer_text": "",
                    "answer_date": None,
                    "answer_number": None,
                    "answer_boolean": None,
                    "answer_select": None,
                }

                if question.field_type == "date":
                    parsed_date = parse_date(answer)
                    if not parsed_date:
                        continue
                    defaults["answer_date"] = parsed_date
                elif question.field_type == "number":
                    parsed_number = parse_decimal_strict(answer)
                    if parsed_number is None:
                        continue
                    defaults["answer_number"] = parsed_number
                elif question.field_type == "boolean":
                    parsed_bool = parse_bool(answer)
                    if parsed_bool is None:
                        continue
                    defaults["answer_boolean"] = parsed_bool
                elif question.field_type == "select":
                    selected = self._match_option(question, answer)
                    if selected:
                        defaults["answer_select"] = selected
                    else:
                        continue
                else:
                    defaults["answer_text"] = str(answer)

                FormAnswer.objects.update_or_create(
                    trip=process.trip,
                    client=process.client,
                    question=question,
                    defaults=defaults,
                )
                total += 1
        return total

    def _match_option(self, question, value):
        needle = normalize_text(value)
        if not needle:
            return None
        options = SelectOption.objects.filter(question=question, is_active=True).order_by("order")
        exact = None
        partial = None
        for option in options:
            option_text = normalize_text(option.text)
            if option_text == needle:
                exact = option
                break
            if needle in option_text and partial is None:
                partial = option
        return exact or partial

    def _strict_sql_orm_validation(self, legacy, client_map, process_map):
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
        for process_id, process in process_map.items():
            legacy_row = legacy_process_map.get(process_id)
            if not legacy_row:
                stage_mismatches.append(f"Processo legado {process_id} nao encontrado para comparar etapas")
                continue

            vt_legacy_id = legacy_row.get("tipo_visto_id")
            if not vt_legacy_id:
                continue

            trip_vt = process.trip.visa_type
            statuses, status_by_name = self._build_status_name_map(trip_vt)
            if not statuses:
                continue

            cron_rows = cronograma_by_process.get(process_id, [])
            fallback_date = parse_date(legacy_row.get("updated_at"))
            stage_state_by_status = self._build_expected_stage_state(
                statuses=statuses,
                status_by_name=status_by_name,
                cron_rows=cron_rows,
                situacao_by_id=situacao_by_id,
                fallback_date=fallback_date,
            )

            percentage = self._parse_legacy_percentage(legacy_row.get("percet_conclusao"))
            done_count = int(round((percentage / 100) * len(statuses)))
            done_count = max(0, min(len(statuses), done_count))

            for index, status in enumerate(statuses):
                if cron_rows:
                    expected_done = stage_state_by_status.get(status.pk, {}).get("completed", False)
                else:
                    expected_done = index < done_count
                stage = ProcessStage.objects.filter(process=process, status=status).first()
                if not stage:
                    stage_mismatches.append(
                        f"Processo {process_id}: etapa '{status.name}' ausente no ORM"
                    )
                    continue
                if stage.completed != expected_done:
                    stage_mismatches.append(
                        f"Processo {process_id}: etapa '{status.name}' esperado={expected_done} orm={stage.completed}"
                    )

        partner_mismatches = []
        legacy_partner_by_id = {
            int(row["id"]): str(row.get("user_email") or "").strip().lower()
            for row in legacy["parceiros"]
            if row.get("id") is not None
        }
        expected_links = self._collect_legacy_partner_links(legacy)
        for legacy_client_id, legacy_partner_id in expected_links.items():
            client = client_map.get(legacy_client_id)
            if not client or not client.referring_partner_id:
                partner_mismatches.append(
                    f"Cliente legado {legacy_client_id}: parceiro ausente no ORM"
                )
                continue
            expected_email = legacy_partner_by_id.get(legacy_partner_id)
            current_email = str(client.referring_partner.email or "").strip().lower()
            if expected_email and expected_email != current_email:
                partner_mismatches.append(
                    f"Cliente legado {legacy_client_id}: parceiro esperado={expected_email} orm={current_email}"
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
        for process_id, process in process_map.items():
            legacy_row = legacy_process_map.get(process_id)
            if not legacy_row:
                continue
            expected_concluded_form = parse_bool(legacy_row.get("conclusao_formulario")) is True
            orm_qs = FormAnswer.objects.filter(
                trip=process.trip,
                client=process.client,
            )
            orm_response_count = orm_qs.count()
            if expected_concluded_form and orm_response_count == 0:
                form_mismatches.append(
                    f"Processo {process_id}: legado conclusao_formulario=1 mas ORM sem respostas"
                )

            form = VisaForm.objects.filter(visa_type=process.trip.visa_type, is_active=True).first()
            legacy_client = legacy_client_map.get(int(legacy_row.get("cliente_id") or 0))
            if not form or not legacy_client:
                continue

            context = {
                "cliente": legacy_client,
                "processo": legacy_row,
            }
            for table_name, table_map in payload_maps.items():
                context[table_name] = table_map.get(process_id, {})

            for question in FormQuestion.objects.filter(form=form, is_active=True).order_by("order"):
                q_key = normalize_text(question.question)
                if not any(alias in q_key for alias in critical_form_aliases):
                    continue
                expected_value = self._extract_answer_value(question.question, context)
                if expected_value in (None, ""):
                    continue
                answer = orm_qs.filter(question=question).first()
                if not answer:
                    form_mismatches.append(
                        f"Processo {process_id}: pergunta '{question.question}' sem resposta no ORM"
                    )
                    continue

                if question.field_type == "date":
                    expected_date = parse_date(expected_value)
                    if expected_date and answer.answer_date != expected_date:
                        form_mismatches.append(
                            f"Processo {process_id}: pergunta '{question.question}' data esperada={expected_date} orm={answer.answer_date}"
                        )
                elif question.field_type == "number":
                    expected_number = parse_decimal_strict(expected_value)
                    if expected_number is not None and answer.answer_number != expected_number:
                        form_mismatches.append(
                            f"Processo {process_id}: pergunta '{question.question}' numero esperado={expected_number} orm={answer.answer_number}"
                        )
                elif question.field_type == "boolean":
                    expected_bool = parse_bool(expected_value)
                    if expected_bool is not None and answer.answer_boolean != expected_bool:
                        form_mismatches.append(
                            f"Processo {process_id}: pergunta '{question.question}' booleano esperado={expected_bool} orm={answer.answer_boolean}"
                        )
                elif question.field_type == "select":
                    expected_option = self._match_option(question, expected_value)
                    if expected_option and answer.answer_select_id != expected_option.pk:
                        form_mismatches.append(
                            f"Processo {process_id}: pergunta '{question.question}' selecao esperada={expected_option.text} orm={answer.get_answer_display()}"
                        )
                else:
                    expected_text_key = normalize_semantic_key(expected_value)
                    actual_text_key = normalize_semantic_key(answer.answer_text)
                    if expected_text_key and actual_text_key and expected_text_key != actual_text_key:
                        form_mismatches.append(
                            f"Processo {process_id}: pergunta '{question.question}' texto esperado={expected_value} orm={answer.answer_text}"
                        )

        return {
            "stage_mismatches": stage_mismatches,
            "partner_mismatches": partner_mismatches,
            "form_mismatches": form_mismatches,
        }

    def _print_validation_report(
        self,
        legacy,
        client_map,
        process_map,
        trip_map,
        client_issues,
        stages_count,
        partners_linked_count,
        financial_count,
        answers_count,
    ):
        issues_total = sum(1 for _, issues in client_issues.items() if issues)
        legacy_clients = len(legacy["clientes"])
        legacy_processes = len(legacy["processos"])
        legacy_groups = len(set(self._build_process_groups(legacy).values()))

        self.stdout.write("\n================= VALIDACAO LEGADO -> VISARY =================")
        self.stdout.write(f"SQL legado clientes: {legacy_clients}")
        self.stdout.write(f"ORM importados clientes: {len(client_map)}")
        self.stdout.write(f"SQL legado processos: {legacy_processes}")
        self.stdout.write(f"ORM importados processos: {len(process_map)}")
        self.stdout.write(f"SQL legado grupos de viagem: {legacy_groups}")
        self.stdout.write(f"ORM importadas viagens: {len(trip_map)}")
        self.stdout.write(f"ORM etapas de processo atualizadas/criadas: {stages_count}")
        self.stdout.write(f"Clientes com parceiro legado vinculado: {partners_linked_count}")
        self.stdout.write(f"ORM financeiro atualizados/criados: {financial_count}")
        self.stdout.write(f"ORM respostas de formulario atualizadas/criadas: {answers_count}")
        self.stdout.write(f"Clientes com inconsistencia de CPF marcada: {issues_total}")
        advisor_counter = Counter(
            client.assigned_advisor.name
            for client in client_map.values()
            if client.assigned_advisor_id
        )
        for advisor_name, count in advisor_counter.items():
            self.stdout.write(f"Clientes vinculados ao assessor {advisor_name}: {count}")

        strict_report = self._strict_sql_orm_validation(
            legacy=legacy,
            client_map=client_map,
            process_map=process_map,
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
            len(client_map) == legacy_clients
            and len(process_map) == legacy_processes
            and len(trip_map) == legacy_groups
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
