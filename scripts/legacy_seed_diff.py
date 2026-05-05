import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY_FORMS_DIR = ROOT.parent / "visary-front" / "src" / "pages" / "Processos" / "Formularios"
SEEDS_DIR = ROOT / "static" / "forms_ini"


@dataclass(frozen=True)
class LegacyField:
    label: str
    required: bool
    file: str


def _norm(text: str) -> str:
    raw = unicodedata.normalize("NFKD", (text or "").strip())
    raw = raw.replace("\u00a0", " ")
    raw = re.sub(r"\s+", " ", raw)
    return raw.lower()


LABEL_PATTERNS = [
    # Input / InputSelect components
    re.compile(r"label=\{['\"]([^'\"]+)['\"]\}"),
    re.compile(r'label=\{"([^"]+)"\}'),
]

PLAIN_LABEL_PATTERN = re.compile(r"<label[^>]*>\s*([^<]+?)\s*</label>", re.DOTALL)


def _is_noise_label(label: str) -> bool:
    token = _norm(label)
    if not token:
        return True
    noise = {
        "sim",
        "não",
        "nao",
        "endereço",
        "endereco",
        "carregando",
        "salvar",
        "continuar",
    }
    return token in noise or len(token) <= 2


def extract_legacy_fields(tsx_path: Path) -> list[LegacyField]:
    text = tsx_path.read_text(encoding="utf-8", errors="ignore")
    fields: list[LegacyField] = []

    for pat in LABEL_PATTERNS:
        for m in pat.finditer(text):
            label = re.sub(r"\s+", " ", m.group(1)).strip()
            if not label or _is_noise_label(label):
                continue
            # crude heuristic: required prop near the match
            span_start = max(m.start() - 120, 0)
            span_end = min(m.end() + 200, len(text))
            window = text[span_start:span_end]
            required = bool(re.search(r"\brequired\b(?!\s*=\s*{?\s*false)", window))
            fields.append(LegacyField(label=label, required=required, file=str(tsx_path.relative_to(ROOT.parent))))

    # Radio blocks (plain <label>) frequently contain question prompts in legacy.
    for m in PLAIN_LABEL_PATTERN.finditer(text):
        label = re.sub(r"\s+", " ", m.group(1)).strip()
        if not label or _is_noise_label(label):
            continue
        span_start = max(m.start() - 200, 0)
        span_end = min(m.end() + 200, len(text))
        window = text[span_start:span_end]
        required = bool(re.search(r"\brequired\b(?!\s*=\s*{?\s*false)", window))
        fields.append(LegacyField(label=label, required=required, file=str(tsx_path.relative_to(ROOT.parent))))

    # de-dup by normalized label + required + file
    seen = set()
    out: list[LegacyField] = []
    for f in fields:
        key = (_norm(f.label), f.required, f.file)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def load_seed_questions(seed_path: Path) -> dict[int, list[dict]]:
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    form_item = payload[0]
    by_stage: dict[int, list[dict]] = {}
    for q in form_item.get("perguntas", []):
        by_stage.setdefault(int(q.get("etapa") or 0), []).append(q)
    for stage, items in by_stage.items():
        items.sort(key=lambda x: int(x.get("ordem") or 0))
    return by_stage


EUA_STAGE_FILES = {
    1: "FormulariosEua/DadosPessoais/index.tsx",
    2: "FormulariosEua/DadosConjuge/index.tsx",
    3: "FormulariosEua/Passaporte/index.tsx",
    4: "FormulariosEua/DadosViagem/index.tsx",
    5: "FormulariosEua/DadosEscola/index.tsx",
    6: "FormulariosEua/DadosContatoBrasil/index.tsx",
    7: "FormulariosEua/CusteioViagem/index.tsx",
    8: "FormulariosEua/DadosAcompanhantes/index.tsx",
    9: "FormulariosEua/DadosViagensAnteriores/index.tsx",
    10: "FormulariosEua/VistoAnterior/index.tsx",
    11: "FormulariosEua/ContatoEUA/index.tsx",
    12: "FormulariosEua/DadosDosPais/index.tsx",
    13: "FormulariosEua/DadosParentesNoPais/index.tsx",
    14: "FormulariosEua/DadosOcupacao/index.tsx",
    15: "FormulariosEua/PerguntasAdicionais/index.tsx",
    16: "FormulariosEua/EmpregosAnteriores/index.tsx",
    17: "FormulariosEua/InformacoesEducacionais/index.tsx",
    18: "FormulariosEua/IdiomaExperienciaInternacional/index.tsx",
    19: "FormulariosEua/PerguntaSeguranca/index.tsx",
    20: "FormulariosEua/ComentariosAdicionais/index.tsx",
    21: "FormulariosEua/DadosBiometria/index.tsx",
    22: "FormulariosEua/Consulado/index.tsx",
    23: "FormulariosEua/Agendamento/index.tsx",
    24: "FormulariosEua/Declaracao/index.tsx",
}

CANADA_STAGE_FILES = {
    1: "FormulariosCa/DadosPessoais/index.tsx",
    2: "FormulariosCa/DadosConjugeCa/index.tsx",
    3: "FormulariosCa/ConjugeAnterior/index.tsx",
    4: "FormulariosCa/PassaporteCa/index.tsx",
    5: "FormulariosCa/DadosContatoCa/index.tsx",
    6: "FormulariosCa/DadosViagemCa/index.tsx",
    7: "FormulariosCa/PermissaoEstudosCa/index.tsx",
    8: "FormulariosCa/DadosEducacionaisCa/index.tsx",
    9: "FormulariosCa/InformacoesProfissionaisCa/index.tsx",
    10: "FormulariosCa/DetalhesEmpregaticiosEstudoAposentadoria/index.tsx",
    11: "FormulariosCa/DetalhamentoEmpregoAnteriorCA/index.tsx",
    12: "FormulariosCa/SaudeHistoricoImigracionalCa/index.tsx",
    13: "FormulariosCa/PerguntaSegurancaCa/index.tsx",
    14: "FormulariosCa/DadosFamiliaresCa/index.tsx",
    15: "FormulariosCa/DadosFilhosCa/index.tsx",
    16: "FormulariosCa/InformacoesAdicionaisViagemCa/index.tsx",
}

AUS_VIS_STAGE_FILES = {
    1: "FormulariosAusVisitante/DadosPessoaisAus/index.tsx",
    2: "FormulariosAusVisitante/PassaporteAusVisitante/index.tsx",
    3: "FormulariosAusVisitante/InformacoesContato/index.tsx",
    4: "FormulariosAusVisitante/DadosViagemAusVisitante/index.tsx",
    5: "FormulariosAusVisitante/OcupacaoAusVisitante/index.tsx",
    6: "FormulariosAusVisitante/ComprovanteRendaAus/index.tsx",
    7: "FormulariosAusVisitante/AutorizacaoMenores/index.tsx",
    8: "FormulariosAusVisitante/DeclaracaoSaudeAus/index.tsx",
    9: "FormulariosAusVisitante/DeclaracaoCaraterPessoalAus/index.tsx",
    10: "FormulariosAusVisitante/DeclaracaoFinalAus/index.tsx",
}

AUS_STU_STAGE_FILES = {
    1: "FormularioAusEstudante/DadosPessoaisAusEstudante/index.tsx",
    2: "FormularioAusEstudante/PassaporteAusEstudante/index.tsx",
    3: "FormularioAusEstudante/DadosViagemAusEstudante/index.tsx",
    4: "FormularioAusEstudante/DadosViageEducacionalAusEstudante/index.tsx",
    5: "FormularioAusEstudante/NivelIngles/index.tsx",
    6: "FormularioAusEstudante/DadosVistosAnterioresAusEstudante/index.tsx",
    7: "FormularioAusEstudante/OcupacaoAusEstudante/index.tsx",
    8: "FormularioAusEstudante/FamiliaresBrasil/index.tsx",
    9: "FormularioAusEstudante/SegundoContatoPais/index.tsx",
    10: "FormularioAusEstudante/InformacoesFinanceirasAus/index.tsx",
    11: "FormularioAusEstudante/AssistenciaMedicaAusEstudante/index.tsx",
    12: "FormularioAusEstudante/DeclaracaoSaudeAusEstudante/index.tsx",
    13: "FormularioAusEstudante/DeclaracaoCaraterPessoal/index.tsx",
    14: "FormularioAusEstudante/AutorizacaoMenorAusEstudante/index.tsx",
    15: "FormularioAusEstudante/InformacoesAdicionaisAusEstudante/index.tsx",
    16: "FormularioAusEstudante/DeclaracaoFinalAusEstudante/index.tsx",
}


def _legacy_file_map_for_seed(seed_name: str) -> dict[int, str]:
    if "EUA" in seed_name:
        return EUA_STAGE_FILES
    if "CANADA" in seed_name:
        return CANADA_STAGE_FILES
    if "AUSTRALIA_VISITANTE" in seed_name:
        return AUS_VIS_STAGE_FILES
    if "AUSTRALIA_ESTUDANTE" in seed_name:
        return AUS_STU_STAGE_FILES
    return {}


def main() -> int:
    if not LEGACY_FORMS_DIR.exists():
        raise SystemExit(f"Legacy dir not found: {LEGACY_FORMS_DIR}")
    if not SEEDS_DIR.exists():
        raise SystemExit(f"Seeds dir not found: {SEEDS_DIR}")

    seed_files = sorted(SEEDS_DIR.glob("FORMULARIO_*.json"))
    out_path = ROOT / "docs" / "prd" / "PRD-019-legacy-seed-diff-report.md"
    lines: list[str] = ["# Legacy × Seed diff (por etapa)\n"]
    for seed_path in seed_files:
        seed_name = seed_path.name
        lines.append(f"## {seed_name}")

        seed_by_stage = load_seed_questions(seed_path)
        legacy_map = _legacy_file_map_for_seed(seed_name)
        if not legacy_map:
            lines.append("- **status**: sem mapeamento de legado para este seed\n")
            continue

        for stage_order in sorted({k for k in seed_by_stage.keys() if k} | set(legacy_map.keys())):
            legacy_rel = legacy_map.get(stage_order)
            legacy_fields: list[LegacyField] = []
            if legacy_rel:
                legacy_path = LEGACY_FORMS_DIR / legacy_rel
                if legacy_path.exists():
                    legacy_fields = extract_legacy_fields(legacy_path)

            legacy_labels = {_norm(f.label) for f in legacy_fields}
            seed_labels = {_norm(q["pergunta"]) for q in seed_by_stage.get(stage_order, [])}

            missing_in_seed = sorted(legacy_labels - seed_labels)
            extra_in_seed = sorted(seed_labels - legacy_labels)

            if not missing_in_seed and not extra_in_seed:
                continue

            lines.append(f"### Etapa {stage_order}")
            if legacy_rel:
                lines.append(f"- **legado**: `{(LEGACY_FORMS_DIR / legacy_rel).as_posix()}`")
            lines.append(f"- **missing_in_seed**: {len(missing_in_seed)}")
            for item in missing_in_seed[:20]:
                lines.append(f"  - {item}")
            if len(missing_in_seed) > 20:
                lines.append("  - ...")
            lines.append(f"- **extra_in_seed**: {len(extra_in_seed)}")
            for item in extra_in_seed[:20]:
                lines.append(f"  - {item}")
            if len(extra_in_seed) > 20:
                lines.append("  - ...")
            lines.append("")

        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

