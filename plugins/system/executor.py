"""
System Plugin — SystemExecutor class.

ALL executor logic for the system plugin lives here as private instance
methods (``_name_mangled`` via double-underscore).  There are no
module-level executor functions in this package anymore.  The only way
to invoke one of these methods is via a bound reference handed to the
:class:`ExecutionEngine` during plugin registration.

Why name-mangled?
-----------------
A double-underscore method on a class becomes ``_ClassName__method`` in
the instance ``__dict__``.  External callers cannot reach it by the
obvious name (``instance._create_file``) — they would need to know the
class name and the mangled attribute.  Combined with a private plugin
instance (held only by the engine/loader), this makes the executors
practically unreachable from outside the registry pipeline.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path, PurePath
from typing import Any

import psutil

from aura.core.config_loader import get as get_config
from aura.core.errors import ExecutionError, PolicyError, SandboxError
from aura.core.event_bus import EventBus
from aura.core.logger import benchmark, get_logger
from aura.security.policy import get_policy, split_command_string
from aura.core.result import CommandResult
from aura.security.sandbox import resolve_safe_path
from aura.core.tracing import current_trace_id

_ALLOWED_SCRIPT_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_:."
)

_SHELL_BUILTINS: frozenset[str] = frozenset({
    "echo", "dir", "ls", "type", "cat",
})


class SystemExecutor:
    """All executors for the ``system`` plugin — private by construction."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._logger = get_logger("aura.plugin.system")
        self._policy = get_policy()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def __safe_run(
        self,
        argv: list[str],
        *,
        cwd: Path | None = None,
        timeout: int | None = None,
        command_type: str = "process.shell",
        use_shell: bool = False,
    ) -> CommandResult:
        if not argv:
            raise PolicyError("Empty argv")
        if timeout is None:
            timeout = int(get_config("shell.timeout", 120))

        run_arg: str | list[str] = " ".join(argv) if use_shell else argv

        with benchmark(
            self._logger, "process.run",
            action=command_type, argv=argv, trace_id=current_trace_id(),
        ):
            env = {**os.environ, "PYTHONUTF8": "1"}
            try:
                completed = subprocess.run(
                    run_arg,
                    cwd=str(cwd) if cwd else None,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    shell=use_shell,
                    check=False,
                    env=env,
                )
            except FileNotFoundError as exc:
                raise ExecutionError(f"Command not found: {exc}") from exc
            except subprocess.TimeoutExpired as exc:
                raise ExecutionError(f"Command timed out after {timeout}s") from exc

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        code = completed.returncode
        pieces: list[str] = []
        if stdout:
            pieces.append(stdout)
        if stderr:
            pieces.append(f"[stderr] {stderr}")
        pieces.append(f"(exit code {code})")

        return CommandResult(
            success=code == 0,
            message="\n".join(pieces),
            data={"stdout": stdout, "stderr": stderr, "returncode": code},
            command_type=command_type,
        )

    @staticmethod
    def __resolve_npm() -> str | None:
        return shutil.which("npm") or shutil.which("npm.cmd")

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------
    def __file_create(self, path: str) -> CommandResult:
        target = resolve_safe_path(path, create_parents=True)
        if target.exists():
            return CommandResult(
                success=True,
                message=f"[WARNING] File already exists: {target} \u2014 not overwritten.",
                data={"path": str(target), "already_existed": True},
                command_type="file.create",
            )
        target.touch(exist_ok=True)
        self._logger.info(
            "file.created",
            extra={"event": "file.created", "data": {"path": str(target)}},
        )
        return CommandResult(
            success=True,
            message=f"File created: {target}",
            data={"path": str(target)},
            command_type="file.create",
        )

    def __file_delete(self, path: str) -> CommandResult:
        target = resolve_safe_path(path, must_exist=True)
        if target.is_dir():
            raise SandboxError(
                f"Refusing to delete directory via file.delete: {target}"
            )
        target.unlink()
        self._logger.info(
            "file.deleted",
            extra={"event": "file.deleted", "data": {"path": str(target)}},
        )
        return CommandResult(
            success=True,
            message=f"File deleted: {target}",
            data={"path": str(target)},
            command_type="file.delete",
        )

    def __file_rename(self, old_name: str, new_name: str) -> CommandResult:
        new_clean = str(new_name).strip().strip("\"'")
        if not new_clean:
            raise SandboxError("new_name is required")
        if str(PurePath(new_clean).parent) != ".":
            raise SandboxError("new_name must be a plain filename, not a path")

        source = resolve_safe_path(old_name, must_exist=True)
        destination = resolve_safe_path(str(source.parent / new_clean))
        source.rename(destination)
        self._logger.info(
            "file.renamed",
            extra={"event": "file.renamed",
                   "data": {"old": str(source), "new": str(destination)}},
        )
        return CommandResult(
            success=True,
            message=f"Renamed: {source.name} -> {destination.name}",
            data={"old": str(source), "new": str(destination)},
            command_type="file.rename",
        )

    def __file_move(self, source: str, destination: str) -> CommandResult:
        src = resolve_safe_path(source, must_exist=True)
        dst = resolve_safe_path(destination, create_parents=True)
        if dst.is_dir():
            dst = resolve_safe_path(str(dst / src.name))
        shutil.move(str(src), str(dst))
        self._logger.info(
            "file.moved",
            extra={"event": "file.moved",
                   "data": {"source": str(src), "destination": str(dst)}},
        )
        return CommandResult(
            success=True,
            message=f"Moved: {src} -> {dst}",
            data={"source": str(src), "destination": str(dst)},
            command_type="file.move",
        )

    def __file_search(
        self, directory: str, pattern: str, limit: int = 200
    ) -> CommandResult:
        root = resolve_safe_path(directory, must_exist=True)
        if not root.is_dir():
            raise SandboxError(f"Not a directory: {root}")
        if not pattern or not str(pattern).strip():
            raise SandboxError("search pattern is required")
        try:
            limit_int = int(limit)
        except (TypeError, ValueError) as exc:
            raise SandboxError(f"limit must be int, got {limit!r}") from exc
        if limit_int <= 0:
            raise SandboxError("limit must be positive")

        matches: list[str] = []
        for idx, match in enumerate(root.rglob(str(pattern))):
            if idx >= limit_int:
                break
            matches.append(str(match))

        message = (
            "No files found."
            if not matches
            else f"Found {len(matches)} file(s):\n" + "\n".join(matches)
        )
        self._logger.info(
            "file.searched",
            extra={"event": "file.searched",
                   "data": {"root": str(root), "pattern": pattern,
                            "count": len(matches)}},
        )
        return CommandResult(
            success=True,
            message=message,
            data={"matches": matches, "root": str(root)},
            command_type="file.search",
        )

    # ------------------------------------------------------------------
    # Process / shell / monitor
    # ------------------------------------------------------------------
    def __process_shell(self, command: str) -> CommandResult:
        self._policy.check_shell_command(command)
        argv = split_command_string(command)
        cmd_name = Path(argv[0]).stem.lower() if argv else ""
        is_builtin = cmd_name in _SHELL_BUILTINS
        return self.__safe_run(
            argv, command_type="process.shell", use_shell=is_builtin,
        )

    def __process_list(self, limit: int = 25) -> CommandResult:
        try:
            limit_int = int(limit)
        except (TypeError, ValueError) as exc:
            raise ExecutionError(f"limit must be int, got {limit!r}") from exc
        if limit_int <= 0:
            raise ExecutionError("limit must be positive")

        snapshot: list[dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                info = proc.info
                mem = info.get("memory_info")
                snapshot.append({
                    "pid": info["pid"],
                    "name": info["name"],
                    "cpu_percent": info.get("cpu_percent", 0),
                    "memory_mb": round((mem.rss if mem else 0) / (1024 * 1024), 1),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        snapshot.sort(key=lambda p: p["memory_mb"], reverse=True)
        top = snapshot[:limit_int]
        rows = "\n".join(
            f"  {p['pid']:>7}  {p['name']:<25}  "
            f"CPU {p['cpu_percent']:>5}%  MEM {p['memory_mb']:>8} MB"
            for p in top
        )
        return CommandResult(
            success=True,
            message="Top processes:\n" + rows,
            data={"processes": top},
            command_type="process.list",
        )

    def __process_kill(self, process_name: str) -> CommandResult:
        self._policy.check_kill_target(process_name)
        killed = 0
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info.get("name") if proc.info else None
                if name and name.lower() == process_name.lower():
                    proc.terminate()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if killed:
            return CommandResult(
                success=True,
                message=f"Terminated {killed} process(es) named '{process_name}'",
                data={"killed": killed, "name": process_name},
                command_type="process.kill",
            )
        return CommandResult(
            success=False,
            message=f"No running process found with name '{process_name}'",
            data={"killed": 0, "name": process_name},
            command_type="process.kill",
        )

    def __cpu_usage(self) -> CommandResult:
        pct = psutil.cpu_percent(interval=0.1)
        return CommandResult(
            success=True,
            message=f"CPU usage: {pct}%",
            data={"cpu_percent": pct},
            command_type="system.cpu",
        )

    def __ram_usage(self) -> CommandResult:
        vm = psutil.virtual_memory()
        used_gb = vm.used / (1024**3)
        total_gb = vm.total / (1024**3)
        return CommandResult(
            success=True,
            message=(
                f"Memory usage: {vm.percent}% "
                f"({used_gb:.2f} GiB used / {total_gb:.2f} GiB total)"
            ),
            data={
                "percent": vm.percent,
                "used_bytes": vm.used,
                "total_bytes": vm.total,
            },
            command_type="system.ram",
        )

    # ------------------------------------------------------------------
    # System health
    # ------------------------------------------------------------------
    def __probe_tool(self, tool: str) -> str:
        executable = shutil.which(tool)
        if executable is None:
            return "not installed"
        try:
            result = self.__safe_run(
                [executable, "--version"], timeout=10,
                command_type="system.health",
            )
        except PolicyError:
            return "blocked by policy"
        except Exception:
            return "not installed"
        if not result.success:
            return "not installed"
        out = (result.data.get("stdout") or "").strip()
        return out or "installed"

    def __system_health(self) -> CommandResult:
        import sys as _sys
        python_version = f"Python {_sys.version.split()[0]}"
        tools = get_config("system_check.tools") or ["git", "node", "docker", "npm"]
        report: dict[str, str] = {"python": python_version}
        report.update({tool: self.__probe_tool(tool) for tool in tools})
        lines = [
            f"  {tool:<10} : {('NOT INSTALLED' if v == 'not installed' else v)}"
            for tool, v in report.items()
        ]
        self._logger.info(
            "system.health.checked",
            extra={"event": "system.health.checked", "data": report},
        )
        return CommandResult(
            success=True,
            message="System Health:\n" + "\n".join(lines),
            data={"tools": report},
            command_type="system.health",
        )

    # ------------------------------------------------------------------
    # Project scaffolding
    # ------------------------------------------------------------------
    def __project_create(self, path: str) -> CommandResult:
        if not path or not str(path).strip():
            raise ExecutionError(
                "Project path is required. Usage: create project <path>"
            )
        target = resolve_safe_path(path, create_parents=True)
        if target.exists() and any(target.iterdir()):
            return CommandResult(
                success=False,
                message=f"[ERROR] Directory already exists and is not empty: {target}",
                data={"path": str(target)},
                command_type="project.create",
            )
        target.mkdir(parents=True, exist_ok=True)
        (target / "src").mkdir(exist_ok=True)
        (target / "tests").mkdir(exist_ok=True)
        project_name = target.name
        (target / "README.md").write_text(
            f"# {project_name}\n", encoding="utf-8",
        )
        (target / ".gitignore").write_text(
            "__pycache__/\n*.pyc\n.env\n*.egg-info/\ndist/\nbuild/\n"
            "node_modules/\n.venv/\n",
            encoding="utf-8",
        )
        (target / "requirements.txt").touch()
        self._logger.info(
            "project.created",
            extra={"event": "project.created", "data": {"path": str(target)}},
        )
        return CommandResult(
            success=True,
            message=f"Project '{project_name}' created at {target}",
            data={"path": str(target), "name": project_name},
            command_type="project.create",
        )

    # ------------------------------------------------------------------
    # Log reader
    # ------------------------------------------------------------------
    def __log_show(self, filepath: str, lines: int = 20) -> CommandResult:
        if not filepath or not str(filepath).strip():
            raise ExecutionError(
                "Log file path is required. Usage: show logs <path> [n]"
            )
        try:
            n = int(lines)
        except (TypeError, ValueError) as exc:
            raise ExecutionError(f"Line count must be an integer, got {lines!r}") from exc
        if n <= 0:
            raise ExecutionError("Line count must be positive")

        log_path = Path(str(filepath).strip())
        if not log_path.is_absolute():
            log_path = Path(__file__).resolve().parent.parent.parent / log_path

        if not log_path.exists():
            return CommandResult(
                success=False,
                message=f"Log file not found: {log_path}",
                data={"path": str(log_path)},
                command_type="log.show",
            )

        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as fh:
                all_lines = fh.readlines()
            tail = all_lines[-n:] if len(all_lines) > n else all_lines
            output = "".join(tail).rstrip("\n")
        except Exception as exc:
            return CommandResult(
                success=False,
                message=f"Error reading log file: {exc}",
                data={"path": str(log_path)},
                command_type="log.show",
            )

        header = f"Last {len(tail)} line(s) of {log_path}:\n"
        return CommandResult(
            success=True,
            message=header + output,
            data={"path": str(log_path), "lines_shown": len(tail)},
            command_type="log.show",
        )

    # ------------------------------------------------------------------
    # npm
    # ------------------------------------------------------------------
    def __npm_install(self, cwd: str) -> CommandResult:
        project = resolve_safe_path(cwd, must_exist=True)
        if not project.is_dir():
            raise ExecutionError(f"Not a directory: {project}")
        npm_exec = self.__resolve_npm()
        if npm_exec is None:
            raise ExecutionError("npm executable not found in PATH")
        return self.__safe_run(
            [npm_exec, "install"], cwd=project, command_type="npm.install",
        )

    def __npm_run(self, script: str, cwd: str) -> CommandResult:
        if not script or not str(script).strip():
            raise ExecutionError("Script name is required")
        script_clean = str(script).strip()
        if not set(script_clean).issubset(_ALLOWED_SCRIPT_CHARS):
            raise PolicyError(
                f"Invalid npm script name {script_clean!r} "
                f"(only [A-Za-z0-9_-:.] allowed)"
            )
        project = resolve_safe_path(cwd, must_exist=True)
        if not project.is_dir():
            raise ExecutionError(f"Not a directory: {project}")
        npm_exec = self.__resolve_npm()
        if npm_exec is None:
            raise ExecutionError("npm executable not found in PATH")
        return self.__safe_run(
            [npm_exec, "run", script_clean],
            cwd=project, command_type="npm.run",
        )

    # ------------------------------------------------------------------
    # The ONLY public surface: a private bound-method map handed to the
    # plugin loader.  This returns **bound methods** so the engine can
    # invoke them — but the underlying methods themselves are never
    # accessible by plain attribute name due to name-mangling.
    # ------------------------------------------------------------------
    def _export_executors(self) -> dict[str, Any]:
        return {
            "file.create": self._SystemExecutor__file_create,
            "file.delete": self._SystemExecutor__file_delete,
            "file.rename": self._SystemExecutor__file_rename,
            "file.move":   self._SystemExecutor__file_move,
            "file.search": self._SystemExecutor__file_search,
            "project.create": self._SystemExecutor__project_create,
            "log.show":      self._SystemExecutor__log_show,
            "process.shell": self._SystemExecutor__process_shell,
            "process.list":  self._SystemExecutor__process_list,
            "process.kill":  self._SystemExecutor__process_kill,
            "system.cpu":    self._SystemExecutor__cpu_usage,
            "system.ram":    self._SystemExecutor__ram_usage,
            "system.health": self._SystemExecutor__system_health,
            "npm.install":   self._SystemExecutor__npm_install,
            "npm.run":       self._SystemExecutor__npm_run,
        }


__all__: list[str] = ["SystemExecutor"]
