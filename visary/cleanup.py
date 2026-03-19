from __future__ import annotations

import os
import shutil
import stat
import ast
import io
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

try:
    import psutil
except ImportError:                    
    psutil = None


def remove_pycache(root: Path) -> int:
    removed = 0
    for cache_dir in root.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)
        removed += 1
    return removed


def clean_migrations(root: Path) -> int:
    removed = 0
    for migrations_dir in root.rglob("migrations"):
        if not migrations_dir.is_dir():
            continue

        for path in migrations_dir.iterdir():
            if path.name == "__init__.py":
                continue

            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            removed += 1
    return removed


def clean_directory(directory: Path, extra_excluded: Iterable[str] | None = None) -> int:
    removed = 0
    excluded = {"__init__.py"}
    if extra_excluded:
        excluded.update(extra_excluded)

    if not directory.exists():
        return 0

    for path in directory.iterdir():
        if path.name in excluded:
            continue

        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        removed += 1
    return removed


def _force_release_db(db_path: Path) -> None:
    if psutil is None:
        return

    for proc in psutil.process_iter(["pid", "name"]):
        try:
            files = proc.open_files()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

        for opened in files:
            if Path(opened.path) == db_path:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                    try:
                        proc.kill()
                        proc.wait(timeout=3)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                        pass
                break


def remove_database(root: Path) -> bool:
    db_path = root / "db.sqlite3"
    if not db_path.exists():
        print("Arquivo db.sqlite3 não encontrado.")
        return False

    _force_release_db(db_path)

    try:
        db_path.unlink()
    except PermissionError:
        try:
            os.chmod(db_path, stat.S_IWRITE | stat.S_IREAD)
            db_path.unlink()
        except PermissionError as err:
            raise SystemExit(
                "Permissão negada ao remover db.sqlite3. "
                "Execute o script em um prompt com privilégios elevados."
            ) from err

    print("Arquivo db.sqlite3 removido.")
    return True


def _collect_python_processes(excluded_pids: set[int]) -> list["psutil.Process"]:
    assert psutil is not None

    processes: list["psutil.Process"] = []
    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        if proc.pid in excluded_pids:
            continue

        try:
            name = (proc.info.get("name") or "").lower()
            exe = (proc.info.get("exe") or "").lower()
            cmdline: Iterable[str] | None = proc.info.get("cmdline")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

        if "python" in name or "python" in exe:
            processes.append(proc)
            continue

        if cmdline and any("python" in part.lower() for part in cmdline):
            processes.append(proc)
    return processes


def list_and_terminate_python_processes() -> int:
    if psutil is None:
        print("psutil não está instalado; não é possível listar/finalizar processos Python.")
        return 0

    current_pid = psutil.Process().pid
    excluded = {current_pid}

    processes = _collect_python_processes(excluded)
    if not processes:
        print("Nenhum processo Python restante.")
        return 0

    print("Processos Python restantes:")
    for proc in processes:
        cmdline = " ".join(proc.info.get("cmdline") or [])
        print(f"- PID {proc.pid} | {proc.info.get('name') or ''} | {cmdline}")

    terminated = 0
    for proc in processes:
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    gone, alive = psutil.wait_procs(processes, timeout=3)
    terminated += len(gone)

    for proc in alive:
        try:
            proc.kill()
            terminated += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            print(f"Aviso: não foi possível encerrar PID {proc.pid}.")

    leftovers = _collect_python_processes(excluded)
    if leftovers:
        pids = ", ".join(str(proc.pid) for proc in leftovers)
        print(f"Processos que permaneceram ativos: {pids}")
    else:
        print("Todos os processos Python foram finalizados.")

    return terminated


def strip_comments_and_docstrings(root: Path) -> None:
                                                               
    repo_root = root.parent
    print("Limpando comentários e docstrings (stripper embutido)...")
    _strip_comments_and_docstrings_apply(repo_root)


DEFAULT_EXTENSIONS = (".py", ".html", ".txt")


EXCLUDED_DIRS_DEFAULT = {
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".git",
}


HTML_DJANGO_INLINE_COMMENT_RE = re.compile(r"\{#.*?#\}", re.DOTALL)
HTML_DJANGO_BLOCK_COMMENT_RE = re.compile(
    r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}",
    re.DOTALL,
)
HTML_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


@dataclass(frozen=True)
class Span:
    start_line: int
    start_col: int
    end_line: int
    end_col: int


def _detect_newline_style(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    return "\n"


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n")


def _line_offsets(lines: list[str]) -> list[int]:
    offsets = [0]
    total = 0
    for line in lines:
        total += len(line)
        offsets.append(total)
    return offsets


def _abs_index_from_line_col(offsets: list[int], lineno: int, col: int) -> int:
    return offsets[lineno - 1] + col


def _blank_span_preserve_newlines(
    text: str, lines: list[str], offsets: list[int], span: Span
) -> str:
    start = _abs_index_from_line_col(offsets, span.start_line, span.start_col)
    end = _abs_index_from_line_col(offsets, span.end_line, span.end_col)
    snippet = text[start:end]
    replacement = "".join("\n" if ch == "\n" else " " for ch in snippet)
    return text[:start] + replacement + text[end:]


def _iter_py_docstring_spans(source: str) -> tuple[list[Span], list[Span]]:
    tree = ast.parse(source)
    spans_to_blank: list[Span] = []
    suite_only_docstrings: list[Span] = []

    def record_if_docstring(body: list[ast.stmt]) -> None:
        if not body:
            return
        first = body[0]
        if not isinstance(first, ast.Expr):
            return
        value = first.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            span = Span(
                start_line=getattr(value, "lineno"),
                start_col=getattr(value, "col_offset"),
                end_line=getattr(value, "end_lineno"),
                end_col=getattr(value, "end_col_offset"),
            )
            spans_to_blank.append(span)
            if len(body) == 1:
                suite_only_docstrings.append(span)

    record_if_docstring(tree.body)                          
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            record_if_docstring(node.body)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            record_if_docstring(node.body)

    return spans_to_blank, suite_only_docstrings


def _remove_py_docstrings(source: str, filename: str) -> tuple[str, int]:
       
                                            

                                                                            
                                                                               
                         

                                                                                
                                                                  
       
    normalized = _normalize_newlines(source)
    newline_style = _detect_newline_style(source)

    lines = normalized.splitlines(keepends=True)
    offsets = _line_offsets(lines)

    spans_to_blank, suite_only = _iter_py_docstring_spans(normalized)
                                                                                               
    suite_start_set = {(s.start_line, s.start_col) for s in suite_only}

                                                                   
                                                    
    tokens = list(tokenize.generate_tokens(io.StringIO(normalized).readline))
    string_token_by_start: dict[tuple[int, int], tokenize.TokenInfo] = {}
    for tok in tokens:
        if tok.type == tokenize.STRING:
            string_token_by_start[tok.start] = tok

    actions: list[tuple[int, int, str]] = []
    for span in spans_to_blank:
        key = (span.start_line, span.start_col)
        tok = string_token_by_start.get(key)
        if tok is None:
                                                                                
            continue

        start_abs = _abs_index_from_line_col(offsets, tok.start[0], tok.start[1])
        end_abs = _abs_index_from_line_col(offsets, tok.end[0], tok.end[1])
        snippet = normalized[start_abs:end_abs]
        replacement = "".join("\n" if ch == "\n" else " " for ch in snippet)
        actions.append((start_abs, end_abs, replacement))

    actions.sort(key=lambda t: t[0], reverse=True)
    new_text = normalized
    for start_abs, end_abs, replacement in actions:
        new_text = new_text[:start_abs] + replacement + new_text[end_abs:]

                                                             
    if suite_start_set:
        new_lines = new_text.splitlines(keepends=True)
        offsets2 = _line_offsets(new_lines)
        for start_line, start_col in suite_start_set:
                                                                                 
            line = new_lines[start_line - 1]
            has_nl = line.endswith("\n")
            line_wo_nl = line[:-1] if has_nl else line
            base_abs = _abs_index_from_line_col(offsets2, start_line, start_col)
            end_abs = _abs_index_from_line_col(offsets2, start_line, len(line_wo_nl))

            old_len = end_abs - base_abs
            repl = "pass"
            if old_len > 0:
                if len(repl) < old_len:
                    repl = repl + (" " * (old_len - len(repl)))
                else:
                    repl = repl[:old_len]

            new_text = new_text[:base_abs] + repl + new_text[end_abs:]

    new_text = new_text.replace("\n", newline_style)
    compile(new_text, filename, "exec")
    return new_text, len(spans_to_blank)


def _iter_token_spans_to_blank(source: str) -> Iterator[Span]:
    normalized = _normalize_newlines(source)
    lines = normalized.splitlines(keepends=True)
    offsets = _line_offsets(lines)
    coding_re = re.compile(r"coding[:=]\s*([-\w.]+)")

    reader = io.StringIO(normalized).readline
    for tok in tokenize.generate_tokens(reader):
        if tok.type != tokenize.COMMENT:
            continue
        tok_line = tok.line or ""
        row, col = tok.start
        end_row, end_col = tok.end
        if row == 1 and tok_line.startswith("#!"):
            continue
        if row in (1, 2) and coding_re.search(tok_line):
            continue
        yield Span(start_line=row, start_col=col, end_line=end_row, end_col=end_col)


def _remove_py_comments(source: str, filename: str) -> tuple[str, int]:
    normalized = _normalize_newlines(source)
    newline_style = _detect_newline_style(source)
    lines = normalized.splitlines(keepends=True)
    offsets = _line_offsets(lines)
    new_text = normalized
    removed = 0

    for span in _iter_token_spans_to_blank(source):
        new_text = _blank_span_preserve_newlines(new_text, lines, offsets, span)
        removed += 1

    new_text = new_text.replace("\n", newline_style)
    compile(new_text, filename, "exec")
    return new_text, removed


def _strip_js_comments(code: str) -> tuple[str, int]:
    i = 0
    out: list[str] = []
    removed = 0
    quote: str | None = None
    escape = False
    in_template = False
    template_brace_depth = 0

    def peek(n: int = 1) -> str:
        return code[i + n] if i + n < len(code) else ""

    while i < len(code):
        ch = code[i]

        if quote is not None:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            i += 1
            continue

        if in_template and template_brace_depth == 0:
            out.append(ch)
            if ch == "\\":
                if i + 1 < len(code):
                    out.append(code[i + 1])
                    i += 2
                    continue
            elif ch == "`":
                in_template = False
            elif ch == "$" and peek(1) == "{":
                out.append("{")
                template_brace_depth = 1
                i += 2
                continue
            i += 1
            continue

        if in_template and template_brace_depth > 0:
            if ch in ("'", '"'):
                quote = ch
                out.append(ch)
                i += 1
                continue
            if ch == "{":
                template_brace_depth += 1
                out.append(ch)
                i += 1
                continue
            if ch == "}":
                template_brace_depth -= 1
                out.append(ch)
                i += 1
                continue

            if ch == "/" and peek(1) == "/":
                removed += 1
                i += 2
                while i < len(code) and code[i] not in ("\n", "\r"):
                    i += 1
                continue
            if ch == "/" and peek(1) == "*":
                removed += 1
                i += 2
                while i < len(code):
                    if code[i] == "*" and peek(1) == "/":
                        i += 2
                        break
                    if code[i] == "\n":
                        out.append("\n")
                    i += 1
                continue

            out.append(ch)
            i += 1
            continue

        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "`":
            in_template = True
            template_brace_depth = 0
            out.append(ch)
            i += 1
            continue

        if ch == "/" and peek(1) == "/":
            removed += 1
            i += 2
            while i < len(code) and code[i] not in ("\n", "\r"):
                i += 1
            continue
        if ch == "/" and peek(1) == "*":
            removed += 1
            i += 2
            while i < len(code):
                if code[i] == "*" and peek(1) == "/":
                    i += 2
                    break
                if code[i] == "\n":
                    out.append("\n")
                i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out), removed


def _strip_css_comments(code: str) -> tuple[str, int]:
    out: list[str] = []
    removed = 0
    i = 0
    quote: str | None = None
    escape = False

    def peek(n: int = 1) -> str:
        return code[i + n] if i + n < len(code) else ""

    while i < len(code):
        ch = code[i]

        if quote is not None:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            i += 1
            continue

        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            continue

        if ch == "/" and peek(1) == "*":
            removed += 1
            i += 2
            while i < len(code):
                if code[i] == "*" and peek(1) == "/":
                    i += 2
                    break
                if code[i] == "\n":
                    out.append("\n")
                i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out), removed


SCRIPT_BLOCK_RE = re.compile(r"(<script\b[^>]*>)(.*?)(</script>)", re.DOTALL | re.IGNORECASE)


def _remove_comments_from_html(source: str) -> tuple[str, dict[str, int]]:
    newline_style = _detect_newline_style(source)
    normalized = _normalize_newlines(source)
    counts: dict[str, int] = {"django_inline": 0, "django_block": 0, "html": 0, "js": 0, "css": 0}

    text = normalized
    counts["django_inline"] = len(HTML_DJANGO_INLINE_COMMENT_RE.findall(text))
    text = HTML_DJANGO_INLINE_COMMENT_RE.sub("", text)
    counts["django_block"] = len(HTML_DJANGO_BLOCK_COMMENT_RE.findall(text))
    text = HTML_DJANGO_BLOCK_COMMENT_RE.sub("", text)
    counts["html"] = len(HTML_HTML_COMMENT_RE.findall(text))
    text = HTML_HTML_COMMENT_RE.sub("", text)

    out: list[str] = []
    last = 0
    for match in SCRIPT_BLOCK_RE.finditer(text):
        before = text[last : match.start()]
        stripped_before, n_css = _strip_css_comments(before)
        counts["css"] += n_css
        out.append(stripped_before)

        open_tag, content, close_tag = match.group(1), match.group(2), match.group(3)
        stripped_js, n_js = _strip_js_comments(content)
        counts["js"] += n_js
        out.append(f"{open_tag}{stripped_js}{close_tag}")

        last = match.end()

    after = text[last:]
    stripped_after, n_css = _strip_css_comments(after)
    counts["css"] += n_css
    out.append(stripped_after)
    text = "".join(out)

    text = text.replace("\n", newline_style)
    return text, counts


def _remove_comments_from_txt(source: str) -> tuple[str, int]:
    newline_style = _detect_newline_style(source)
    normalized = _normalize_newlines(source)
    removed = 0
    lines = normalized.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("//"):
            removed += 1
            continue
        out.append(line)
    result = "".join(out).replace("\n", newline_style)
    return result, removed


def _iter_files(root: Path, extensions: Iterable[str], excluded_dirs: Iterable[str]) -> Iterator[Path]:
    excluded = {d.lower() for d in excluded_dirs}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            continue
        parts = {p.lower() for p in path.parts}
        if excluded & parts:
            continue
        yield path


def _read_text_preserve_encoding(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    newline_style = "\r\n" if b"\r\n" in data else "\n"

    encoding = ""
    if data.startswith(b"\xff\xfe"):
        encoding = "utf-16-le"
    elif data.startswith(b"\xfe\xff"):
        encoding = "utf-16-be"
    elif data.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"

    if not encoding:
        try:
            encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        except Exception:
            encoding = ""

    candidates: list[str] = []
    if encoding:
        candidates.append(encoding)
    candidates.extend(["utf-8-sig", "utf-8", "cp1252", "latin-1"])

    for enc in candidates:
        try:
            text = data.decode(enc)
            return text, enc
        except Exception:
            continue

    text = data.decode("utf-8", errors="replace")
    return text, "utf-8"


def _write_text(path: Path, text: str, encoding: str) -> None:
    path.write_bytes(text.encode(encoding))


def transform_file(path: Path, apply: bool) -> tuple[bool, dict[str, int], str | None]:
    suffix = path.suffix.lower()
    text, encoding_used = _read_text_preserve_encoding(path)
    changed = False

    if suffix == ".py":
        filename = str(path)
        try:
            new_text, doc_count = _remove_py_docstrings(text, filename)
            new_text2, comment_count = _remove_py_comments(new_text, filename)
            if new_text2 != text:
                changed = True
            if apply and changed:
                _write_text(path, new_text2, encoding_used)
            return changed, {"docstrings": doc_count, "comments": comment_count}, None
        except Exception as e:
            return False, {}, str(e)

    if suffix == ".html":
        new_text, counts = _remove_comments_from_html(text)
        if new_text != text:
            changed = True
        if apply and changed:
            _write_text(path, new_text, encoding_used)
        return changed, counts, None

    if suffix == ".txt":
        new_text, removed = _remove_comments_from_txt(text)
        if new_text != text:
            changed = True
        if apply and changed:
            _write_text(path, new_text, encoding_used)
        return changed, {"removed_comment_lines": removed}, None

    return False, {}, None


def _strip_comments_and_docstrings_apply(repo_root: Path) -> None:
    excluded_dirs = set(EXCLUDED_DIRS_DEFAULT)
    extensions = tuple(ext for ext in DEFAULT_EXTENSIONS)
    files = list(_iter_files(repo_root, extensions, excluded_dirs))

    total_changed = 0
    total_errors = 0
    aggregate_counts: dict[str, int] = {}

    for idx, path in enumerate(sorted(files), start=1):
        changed, counts, error = transform_file(path, apply=True)
        if error:
            total_errors += 1
            print(f"[{idx}/{len(files)}] ERROR {path}: {error}")
            continue
        if changed:
            total_changed += 1
            for k, v in counts.items():
                aggregate_counts[k] = aggregate_counts.get(k, 0) + int(v)

    print(f"Stripper changed files: {total_changed}/{len(files)} | errors={total_errors}")
    if aggregate_counts:
        parts = " ".join(f"{k}={v}" for k, v in sorted(aggregate_counts.items()))
        print(f"Counts: {parts}")

    print("Running `python -m compileall visary`...")
    proc = subprocess.run(
        [sys.executable, "-m", "compileall", "visary"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit("compileall falhou após strip.")

    manage_py = repo_root / "visary" / "manage.py"
    if manage_py.exists():
        print("Running `python visary/manage.py check`...")
        proc = subprocess.run(
            [sys.executable, str(manage_py), "check"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            raise SystemExit("Django check falhou após strip.")


def clean() -> None:
    root = Path(__file__).resolve().parent

    if not root.exists():
        raise SystemExit(f"Diretório não encontrado: {root}")

    removed = remove_pycache(root)
    if removed:
        print(f"Diretórios __pycache__ removidos: {removed}")
    else:
        print("Nenhum diretório __pycache__ encontrado.")

    removed_migrations = clean_migrations(root)
    if removed_migrations:
        print(f"Arquivos de migrations removidos: {removed_migrations}")
    else:
        print("Nenhum arquivo de migrations (além de __init__.py) encontrado.")

    remove_database(root)

    services_root = root / "services" / "pysql"
    reports_dir = services_root / "reports"
    images_dir = services_root / "images"
    logs_dir = services_root / "logs"

    removed_reports = clean_directory(reports_dir)
    removed_images = clean_directory(images_dir, {"LogoRelatorio.jpg"})
    removed_logs = clean_directory(logs_dir)

    total_removed = removed_reports + removed_images + removed_logs
    if total_removed:
        print(
            "Arquivos removidos dos diretórios reports/images/logs: "
            f"{total_removed} (reports={removed_reports}, images={removed_images}, logs={removed_logs})"
        )
    else:
        print("Nenhum arquivo removido dos diretórios reports/images/logs.")

                                                                                    
    strip_comments_and_docstrings(root)

    list_and_terminate_python_processes()


def main() -> None:
    clean()


if __name__ == "__main__":
    main()

