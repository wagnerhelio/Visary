from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from typing import Iterable

try:
    import psutil
except ImportError:  # pragma: no cover
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


def main() -> None:
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

    list_and_terminate_python_processes()


if __name__ == "__main__":
    main()

