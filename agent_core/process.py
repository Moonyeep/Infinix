from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class ProcessPolicyError(PermissionError):
    pass


class ProcessRunner:
    """Run allowlisted checks and explicitly approved OS-shell commands as the bridge user."""

    ALLOWED = {"python", "python3", "node", "npm", "pnpm", "pytest", "git"}
    WINDOWS = os.name == "nt"
    OUTPUT_LIMIT = 12000
    SHELL_COMMAND_LIMIT = 12000

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    @staticmethod
    def build_windows_argv(shell: str, command: str, executable: str | None = None) -> list[str]:
        """Build argv without invoking Python's shell=True parsing."""
        shell = str(shell).strip().lower()
        if shell == "cmd":
            return [executable or "cmd.exe", "/d", "/s", "/c", command]
        if shell in {"powershell", "pwsh"}:
            if not executable:
                raise ProcessPolicyError("PowerShell executable was not found")
            return [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]
        raise ProcessPolicyError("shell must be cmd, powershell, or pwsh")

    @staticmethod
    def build_posix_argv(shell: str, command: str, executable: str) -> list[str]:
        shell = str(shell).strip().lower()
        if shell in {"bash", "sh"}:
            return [executable, "-c", command]
        if shell == "zsh":
            return [executable, "-f", "-c", command]
        if shell == "pwsh":
            return [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]
        raise ProcessPolicyError("shell must be bash, sh, zsh, or pwsh")

    @staticmethod
    def _decode(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode(errors="replace")
        return str(value)

    def _shell_executable(self, shell: str) -> str:
        shell = shell.strip().lower()
        if self.WINDOWS and shell == "cmd":
            return os.environ.get("ComSpec") or os.environ.get("COMSPEC") or "cmd.exe"
        if self.WINDOWS and shell == "powershell":
            found = shutil.which("powershell.exe") or shutil.which("powershell")
            if found:
                return found
            system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
            if system_root:
                return str(Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
            raise ProcessPolicyError("Windows PowerShell (powershell.exe) was not found")
        if shell == "pwsh":
            found = shutil.which("pwsh.exe") or shutil.which("pwsh")
            if found:
                return found
            raise ProcessPolicyError("PowerShell 7 (pwsh) is not installed or not on PATH")
        if not self.WINDOWS and shell in {"bash", "sh", "zsh"}:
            found = shutil.which(shell)
            if found:
                return found
            raise ProcessPolicyError(f"{shell} is not installed or not on PATH")
        allowed = "cmd, powershell, pwsh" if self.WINDOWS else "bash, sh, zsh, pwsh"
        raise ProcessPolicyError(f"shell must be one of: {allowed}")

    @classmethod
    def available_shells(cls) -> list[str]:
        if cls.WINDOWS:
            shells = ["cmd", "powershell"]
            if shutil.which("pwsh.exe") or shutil.which("pwsh"):
                shells.append("pwsh")
            return shells
        return [name for name in ("bash", "sh", "zsh", "pwsh") if shutil.which(name)]

    @staticmethod
    def _merge_path_values(*values: str, separator: str = os.pathsep) -> str:
        merged: list[str] = []
        seen: set[str] = set()
        for value in values:
            for entry in value.split(separator):
                entry = entry.strip().strip('"')
                if not entry:
                    continue
                normalized = os.path.normcase(os.path.normpath(entry)).casefold()
                if normalized not in seen:
                    seen.add(normalized)
                    merged.append(entry)
        return separator.join(merged)

    def _command_environment(self) -> dict[str, str]:
        """Refresh PATH from Windows registry for child shells without mutating this process."""
        env = os.environ.copy()
        if not self.WINDOWS:
            return env
        try:
            import winreg

            path_values = [env.get("PATH", "")]
            registry_paths = (
                (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                (winreg.HKEY_CURRENT_USER, r"Environment"),
            )
            for hive, key_name in registry_paths:
                try:
                    with winreg.OpenKey(hive, key_name) as key:
                        value, _kind = winreg.QueryValueEx(key, "Path")
                    if value:
                        path_values.append(os.path.expandvars(str(value)))
                except OSError:
                    continue

            env["PATH"] = self._merge_path_values(*path_values)
        except (ImportError, OSError, AttributeError):
            # Registry access can be restricted; inherited PATH remains a safe fallback.
            pass
        return env

    def test(self, command: list[str], timeout: int = 300) -> dict[str, Any]:
        executable = Path(command[0]).name.casefold() if command else ""
        current_python = Path(sys.executable).name.casefold()
        if not command or (executable not in self.ALLOWED and executable != current_python):
            raise ProcessPolicyError("command executable is not allowlisted")
        if any(token in {"rm", "del", "format", "shutdown", "sudo", "--delete"} for token in command):
            raise ProcessPolicyError("destructive command token is blocked")
        timeout = max(1, min(int(timeout), 900))
        env = {"PATH": self._command_environment().get("PATH", ""), "PYTHONUNBUFFERED": "1"}
        proc = subprocess.run(command, cwd=self.root, env=env, text=True, capture_output=True, timeout=timeout)
        return {"command": command, "returncode": proc.returncode, "stdout": proc.stdout[-self.OUTPUT_LIMIT :], "stderr": proc.stderr[-self.OUTPUT_LIMIT :]}

    def admin_shell_available(self) -> bool:
        """Return whether a POSIX sudo executable is available; GUI askpass is checked on use."""
        return not self.WINDOWS and bool(shutil.which("sudo"))

    @staticmethod
    def _askpass_helper() -> tuple[str, str | None]:
        """Find a desktop askpass app or create a short-lived wrapper for common Linux dialogs."""
        for name in ("ssh-askpass", "ksshaskpass", "lxqt-openssh-askpass", "qt5-ssh-askpass"):
            found = shutil.which(name)
            if found:
                return found, None
        wrappers = (
            ("zenity", 'exec {app} --password --title="Infinix — privilégio de administrador" --text="$1"'),
            ("yad", 'exec {app} --password --title="Infinix — privilégio de administrador" --text="$1"'),
            ("kdialog", 'exec {app} --password "$1"'),
        )
        for name, template in wrappers:
            app = shutil.which(name)
            if not app:
                continue
            fd, path = tempfile.mkstemp(prefix="zeroscript-askpass-", suffix=".sh")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write("#!/bin/sh\n" + template.format(app=shlex.quote(app)) + "\n")
                os.chmod(path, 0o700)
                return path, path
            except Exception:
                try:
                    os.unlink(path)
                except OSError:
                    pass
                raise
        raise ProcessPolicyError(
            "No graphical sudo password dialog was found. Install/enable a desktop askpass app "
            "(ssh-askpass, zenity, yad, or kdialog) and retry. The password was not requested or stored."
        )

    def run_shell_as_admin(self, shell: str, command: str, cwd: str | None = None, timeout: int = 120) -> dict[str, Any]:
        """Run a POSIX shell command via sudo; the OS askpass dialog handles the secret."""
        if self.WINDOWS:
            raise ProcessPolicyError("sudo elevation is only available on Linux/POSIX")
        if not isinstance(command, str) or not command.strip():
            raise ProcessPolicyError("command must be a non-empty string")
        if "\x00" in command:
            raise ProcessPolicyError("command contains a null character")
        if len(command) > self.SHELL_COMMAND_LIMIT:
            raise ProcessPolicyError(f"command exceeds the {self.SHELL_COMMAND_LIMIT}-character limit")
        working_dir = Path(cwd).expanduser().resolve() if cwd else self.root
        if not working_dir.is_dir():
            raise ProcessPolicyError("cwd must be an existing directory")
        sudo = shutil.which("sudo")
        if not sudo:
            raise ProcessPolicyError("sudo is not installed or not on PATH")
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise ProcessPolicyError("A graphical desktop session is required for the secure sudo password dialog")
        timeout = max(1, min(int(timeout), 120))
        executable = self._shell_executable(shell)
        argv = self.build_posix_argv(shell, command, executable)
        askpass, temporary_helper = self._askpass_helper()
        env = self._command_environment()
        env["SUDO_ASKPASS"] = askpass
        try:
            # The password goes directly from the native desktop dialog to sudo.
            # It is never a tool argument, environment value, model message or log entry.
            auth = subprocess.run(
                [sudo, "-A", "-p", "Infinix precisa de autorização de administrador", "-v"],
                cwd=working_dir, env=env, text=True, capture_output=True, timeout=timeout, check=False,
            )
            if auth.returncode != 0:
                return {
                    "shell": shell.strip().lower(), "cwd": str(working_dir), "returncode": auth.returncode,
                    "timed_out": False, "status": "authorization_failed",
                    "message": "A autenticação foi cancelada ou recusada. Nenhum comando elevado foi executado; a senha não foi armazenada.",
                    "stdout": "", "stderr": "", "stdout_truncated": False, "stderr_truncated": False,
                }
            proc = subprocess.run(
                [sudo, "-n", "--", *argv], cwd=working_dir, env=self._command_environment(),
                text=True, capture_output=True, timeout=timeout, check=False,
            )
            stdout, stderr = proc.stdout or "", proc.stderr or ""
            return {
                "shell": shell.strip().lower(), "cwd": str(working_dir), "returncode": proc.returncode,
                "timed_out": False, "elevated": True,
                "stdout": stdout[-self.OUTPUT_LIMIT :], "stderr": stderr[-self.OUTPUT_LIMIT :],
                "stdout_truncated": len(stdout) > self.OUTPUT_LIMIT,
                "stderr_truncated": len(stderr) > self.OUTPUT_LIMIT,
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "shell": shell.strip().lower(), "cwd": str(working_dir), "returncode": None,
                "timed_out": True, "timeout_seconds": timeout,
                "message": "A autenticação ou o comando elevado excedeu o tempo limite. Nenhuma senha foi registrada.",
                "stdout": self._decode(exc.stdout)[-self.OUTPUT_LIMIT :],
                "stderr": "", "stdout_truncated": False, "stderr_truncated": False,
            }
        finally:
            if temporary_helper:
                try:
                    os.unlink(temporary_helper)
                except OSError:
                    pass

    def run_shell(self, shell: str, command: str, cwd: str | None = None, timeout: int = 120) -> dict[str, Any]:
        """Run one user-reviewed command in an OS shell as the bridge account, without elevating."""
        if not isinstance(command, str) or not command.strip():
            raise ProcessPolicyError("command must be a non-empty string")
        if "\x00" in command:
            raise ProcessPolicyError("command contains a null character")
        if len(command) > self.SHELL_COMMAND_LIMIT:
            raise ProcessPolicyError(f"command exceeds the {self.SHELL_COMMAND_LIMIT}-character limit")

        working_dir = Path(cwd).expanduser().resolve() if cwd else self.root
        if not working_dir.is_dir():
            raise ProcessPolicyError("cwd must be an existing directory")
        timeout = max(1, min(int(timeout), 120))
        executable = self._shell_executable(shell)
        argv = self.build_windows_argv(shell, command, executable) if self.WINDOWS else self.build_posix_argv(shell, command, executable)
        try:
            proc = subprocess.run(argv, cwd=working_dir, env=self._command_environment(), text=True, capture_output=True, timeout=timeout, check=False)
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            return {
                "shell": shell.strip().lower(),
                "cwd": str(working_dir),
                "returncode": proc.returncode,
                "timed_out": False,
                "stdout": stdout[-self.OUTPUT_LIMIT :],
                "stderr": stderr[-self.OUTPUT_LIMIT :],
                "stdout_truncated": len(stdout) > self.OUTPUT_LIMIT,
                "stderr_truncated": len(stderr) > self.OUTPUT_LIMIT,
            }
        except subprocess.TimeoutExpired as exc:
            stdout = self._decode(exc.stdout)
            stderr = self._decode(exc.stderr)
            return {
                "shell": shell.strip().lower(),
                "cwd": str(working_dir),
                "returncode": None,
                "timed_out": True,
                "timeout_seconds": timeout,
                "stdout": stdout[-self.OUTPUT_LIMIT :],
                "stderr": stderr[-self.OUTPUT_LIMIT :],
                "stdout_truncated": len(stdout) > self.OUTPUT_LIMIT,
                "stderr_truncated": len(stderr) > self.OUTPUT_LIMIT,
            }
