from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

from .process import ProcessPolicyError, ProcessRunner


class EndpointDiagnostics:
    """Bounded, local endpoint checks plus a tiny allowlist of explicit scans/repairs."""

    OUTPUT_LIMIT = 12000
    WINDOWS_ACTIONS = {
        "windows_defender_quick_scan": ("scan", 900),
        "windows_dism_scanhealth": ("scan", 900),
        "windows_sfc_verifyonly": ("scan", 900),
        "windows_sfc_scannow": ("repair", 1800),
        "windows_dism_restorehealth": ("repair", 1800),
    }

    def __init__(self, process: ProcessRunner) -> None:
        self.process = process

    @property
    def system(self) -> str:
        return platform.system().lower()

    @staticmethod
    def _bounded_limit(value: int, default: int = 30, maximum: int = 100) -> int:
        try:
            return max(1, min(int(value), maximum))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _bounded_hours(value: int, default: int = 24, maximum: int = 72) -> int:
        try:
            return max(1, min(int(value), maximum))
        except (TypeError, ValueError):
            return default

    @classmethod
    def _response(
        cls,
        operation: str,
        platform_name: str,
        returncode: int | None,
        stdout: str = "",
        stderr: str = "",
        timed_out: bool = False,
        **extra: Any,
    ) -> dict[str, Any]:
        raw_out, raw_err = stdout or "", stderr or ""
        return {
            "operation": operation,
            "platform": platform_name,
            "returncode": returncode,
            "timed_out": timed_out,
            "stdout": raw_out[-cls.OUTPUT_LIMIT :],
            "stderr": raw_err[-cls.OUTPUT_LIMIT :],
            "stdout_truncated": len(raw_out) > cls.OUTPUT_LIMIT,
            "stderr_truncated": len(raw_err) > cls.OUTPUT_LIMIT,
            **extra,
        }

    def _windows_ps(self, operation: str, script: str, timeout: int = 30) -> dict[str, Any]:
        try:
            executable = self.process._shell_executable("powershell")
            argv = self.process.build_windows_argv("powershell", script, executable)
            proc = subprocess.run(
                argv,
                cwd=self.process.root,
                env=self.process._command_environment(),
                text=True,
                capture_output=True,
                timeout=max(1, min(int(timeout), 1800)),
                check=False,
            )
            return self._response(operation, "windows", proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as exc:
            return self._response(
                operation,
                "windows",
                None,
                ProcessRunner._decode(exc.stdout),
                ProcessRunner._decode(exc.stderr),
                timed_out=True,
                timeout_seconds=max(1, min(int(timeout), 1800)),
                note="O processo local foi interrompido pelo timeout; verifique o estado da ferramenta antes de repetir.",
            )
        except (OSError, ProcessPolicyError) as exc:
            return {"operation": operation, "platform": "windows", "available": False, "error": str(exc)}

    def _linux(self, operation: str, argv: list[str], timeout: int = 20) -> dict[str, Any]:
        executable = shutil.which(argv[0]) if argv else None
        if not executable:
            return {"operation": operation, "platform": "linux", "available": False, "error": f"Ferramenta indisponível: {argv[0] if argv else 'comando vazio'}"}
        try:
            proc = subprocess.run(
                [executable, *argv[1:]],
                cwd=self.process.root,
                env=self.process._command_environment(),
                text=True,
                capture_output=True,
                timeout=max(1, min(int(timeout), 1800)),
                check=False,
            )
            return self._response(operation, "linux", proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as exc:
            return self._response(
                operation,
                "linux",
                None,
                ProcessRunner._decode(exc.stdout),
                ProcessRunner._decode(exc.stderr),
                timed_out=True,
                timeout_seconds=max(1, min(int(timeout), 1800)),
                note="O processo local foi interrompido pelo timeout; verifique o estado da ferramenta antes de repetir.",
            )
        except OSError as exc:
            return {"operation": operation, "platform": "linux", "available": False, "error": str(exc)}

    @staticmethod
    def is_admin() -> bool:
        if os.name == "nt":
            try:
                return bool(ctypes.windll.shell32.IsUserAnAdmin())
            except Exception:
                return False
        return hasattr(os, "geteuid") and os.geteuid() == 0

    def system_info(self) -> dict[str, Any]:
        try:
            usage = shutil.disk_usage(Path.home().anchor or str(Path.home()))
            disk = {"total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}
        except OSError as exc:
            disk = {"error": str(exc)}
        info = {
            "platform": self.system,
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "architecture": platform.machine(),
            "hostname": socket.gethostname(),
            "python": platform.python_version(),
            "bridge_is_admin_or_root": self.is_admin(),
            "root_disk": disk,
        }
        if os.name == "nt":
            info["process_architecture"] = os.environ.get("PROCESSOR_ARCHITECTURE")
            info["process_architecture_wow64"] = os.environ.get("PROCESSOR_ARCHITEW6432")
        return info

    def processes(self, limit: int = 30) -> dict[str, Any]:
        limit = self._bounded_limit(limit)
        if self.system == "windows":
            script = (
                "$ErrorActionPreference='Stop'; Get-Process | Sort-Object CPU -Descending "
                f"| Select-Object -First {limit} Id,ProcessName,CPU,WorkingSet64 "
                "| ConvertTo-Json -Compress"
            )
            return self._windows_ps("processes", script)
        if self.system == "linux":
            result = self._linux("processes", ["ps", "-eo", "pid,ppid,user,stat,pcpu,pmem,comm", "--sort=-pcpu"])
            if result.get("stdout"):
                lines = result["stdout"].splitlines()
                result["stdout"] = "\n".join(lines[: limit + 1])
            return result
        return {"operation": "processes", "platform": self.system, "available": False, "error": "Sistema operacional não suportado por esta coleta"}

    def services(self, limit: int = 50) -> dict[str, Any]:
        limit = self._bounded_limit(limit, maximum=100)
        if self.system == "windows":
            script = (
                "$ErrorActionPreference='Stop'; Get-CimInstance Win32_Service "
                f"| Sort-Object Name | Select-Object -First {limit} Name,DisplayName,State,StartMode "
                "| ConvertTo-Json -Compress"
            )
            return self._windows_ps("services", script)
        if self.system == "linux":
            result = self._linux("services", ["systemctl", "list-units", "--type=service", "--all", "--no-pager", "--plain"])
            if result.get("stdout"):
                lines = result["stdout"].splitlines()
                result["stdout"] = "\n".join(lines[: limit + 1])
            return result
        return {"operation": "services", "platform": self.system, "available": False, "error": "Sistema operacional não suportado por esta coleta"}

    def network(self) -> dict[str, Any]:
        if self.system == "windows":
            script = (
                "$ErrorActionPreference='SilentlyContinue'; "
                "$ips=@(Get-NetIPAddress -AddressFamily IPv4 | Select-Object -First 100 InterfaceAlias,IPAddress,PrefixLength); "
                "$listeners=@(Get-NetTCPConnection -State Listen | Select-Object -First 100 LocalAddress,LocalPort,OwningProcess); "
                "[pscustomobject]@{ipv4=$ips;tcp_listeners=$listeners} | ConvertTo-Json -Depth 4 -Compress"
            )
            return self._windows_ps("network", script)
        if self.system == "linux":
            results = {
                "addresses": self._linux("network_addresses", ["ip", "-brief", "address"]),
                "routes": self._linux("network_routes", ["ip", "route"]),
                "listeners": self._linux("network_listeners", ["ss", "-lntu"]),
            }
            return {"operation": "network", "platform": "linux", "results": results}
        return {"operation": "network", "platform": self.system, "available": False, "error": "Sistema operacional não suportado por esta coleta"}

    def security_status(self) -> dict[str, Any]:
        if self.system == "windows":
            script = (
                "$defender=$null; $defenderError=$null; "
                "try {$defender=Get-MpComputerStatus -ErrorAction Stop | Select-Object AntivirusEnabled,AntispywareEnabled,RealTimeProtectionEnabled,AntivirusSignatureLastUpdated,QuickScanAge,FullScanAge} "
                "catch {$defenderError=$_.Exception.Message}; "
                "$firewall=@(Get-NetFirewallProfile -ErrorAction SilentlyContinue | Select-Object Name,Enabled,DefaultInboundAction,DefaultOutboundAction); "
                "[pscustomobject]@{defender=$defender;defender_query_error=$defenderError;firewall_profiles=$firewall} | ConvertTo-Json -Depth 4 -Compress"
            )
            return self._windows_ps("security_status", script)
        if self.system == "linux":
            candidates = ("clamdscan", "clamscan", "lynis", "auditctl", "rkhunter", "chkrootkit", "ufw", "firewall-cmd", "nft", "iptables", "systemctl", "journalctl")
            return {
                "operation": "security_status",
                "platform": "linux",
                "available_tools": {name: shutil.which(name) is not None for name in candidates},
                "note": "Presença de um executável não comprova que a proteção esteja ativa ou corretamente configurada.",
            }
        return {"operation": "security_status", "platform": self.system, "available": False}

    def recent_events(self, channel: str = "System", limit: int = 20, hours: int = 24) -> dict[str, Any]:
        limit = self._bounded_limit(limit, maximum=50)
        hours = self._bounded_hours(hours)
        if self.system == "windows":
            allowed = {"System", "Application", "Security"}
            if channel not in allowed:
                raise ValueError("channel deve ser System, Application ou Security")
            script = (
                f"$log='{channel}'; $since=(Get-Date).AddHours(-{hours}); "
                "$items=Get-WinEvent -FilterHashtable @{LogName=$log;StartTime=$since;Level=1,2,3} "
                f"-MaxEvents {limit} -ErrorAction Stop | Select-Object TimeCreated,Id,LevelDisplayName,ProviderName,@{{n='Message';e={{if ($_.Message) {{ $_.Message.Substring(0,[Math]::Min(400,$_.Message.Length)) }} else {{ '' }}}}}}; "
                "$items | ConvertTo-Json -Depth 3 -Compress"
            )
            return self._windows_ps("recent_events", script)
        if self.system == "linux":
            return self._linux(
                "recent_events",
                ["journalctl", "--no-pager", "--since", f"-{hours} hours", "-p", "warning", "-n", str(limit), "-o", "short-iso"],
            )
        return {"operation": "recent_events", "platform": self.system, "available": False}

    def startup_items(self, limit: int = 50) -> dict[str, Any]:
        limit = self._bounded_limit(limit, maximum=100)
        if self.system == "windows":
            script = (
                "$tasks=@(); $startup=@(); "
                f"try {{$tasks=@(Get-ScheduledTask -ErrorAction Stop | Select-Object -First {limit} TaskPath,TaskName,State)}} catch {{}}; "
                f"try {{$startup=@(Get-CimInstance Win32_StartupCommand -ErrorAction Stop | Select-Object -First {limit} Name,Location,User)}} catch {{}}; "
                "[pscustomobject]@{scheduled_tasks=$tasks;startup_entries=$startup} | ConvertTo-Json -Depth 4 -Compress"
            )
            return self._windows_ps("startup_items", script)
        if self.system == "linux":
            result = self._linux("startup_items", ["systemctl", "list-unit-files", "--state=enabled", "--type=service", "--no-pager"])
            if result.get("stdout"):
                lines = result["stdout"].splitlines()
                result["stdout"] = "\n".join(lines[: limit + 1])
            home = Path.home() / ".config" / "autostart"
            entries = sorted(p.name for p in home.iterdir() if p.is_file())[:limit] if home.is_dir() else []
            result["user_autostart_filenames"] = entries
            return result
        return {"operation": "startup_items", "platform": self.system, "available": False}

    def windows_account_snapshot(self) -> dict[str, Any]:
        if self.system != "windows":
            return {"operation": "windows_account_snapshot", "platform": self.system, "available": False, "error": "Esta consulta é específica de Windows"}
        script = r"""
$ErrorActionPreference='Stop'
$users=@(); $admins=@(); $accountError=$null
try {
  $users=@(Get-LocalUser | Select-Object Name,Enabled,SID,LastLogon,PrincipalSource)
  $group=Get-LocalGroup -SID 'S-1-5-32-544'
  $admins=@(Get-LocalGroupMember -Group $group | Select-Object Name,ObjectClass,PrincipalSource,SID)
} catch { $accountError=$_.Exception.Message }
$profiles=@()
try { $profiles=@(Get-CimInstance Win32_UserProfile | Select-Object SID,LocalPath,Loaded,Special) } catch {}
$cmdPolicy=@()
$policyPath='HKCU:\Software\Policies\Microsoft\Windows\System'
if (Test-Path $policyPath) {
  $policy=Get-ItemProperty -Path $policyPath -Name DisableCMD -ErrorAction SilentlyContinue
  if ($null -ne $policy) { $cmdPolicy=@([pscustomobject]@{scope='current_user';DisableCMD=$policy.DisableCMD}) }
}
$ifeo=$null
$ifeoPath='HKLM:\Software\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\cmd.exe'
if (Test-Path $ifeoPath) { $ifeo=(Get-ItemProperty -Path $ifeoPath -Name Debugger -ErrorAction SilentlyContinue).Debugger }
$cmdPath=Join-Path $env:SystemRoot 'System32\cmd.exe'
$cmdSignature=$null
if (Test-Path $cmdPath) { try {$cmdSignature=Get-AuthenticodeSignature -FilePath $cmdPath | Select-Object Status,@{n='Signer';e={$_.SignerCertificate.Subject}}} catch {} }
[pscustomobject]@{
  architecture=$env:PROCESSOR_ARCHITECTURE
  wow64_architecture=$env:PROCESSOR_ARCHITEW6432
  is64bit_os=[Environment]::Is64BitOperatingSystem
  is64bit_powershell=[Environment]::Is64BitProcess
  local_users=$users
  local_administrators_group_members=$admins
  account_query_error=$accountError
  user_profiles=$profiles
  current_user_disable_cmd_policy=$cmdPolicy
  comspec=$env:ComSpec
  cmd_system32_exists=(Test-Path $cmdPath)
  cmd_system32_signature=$cmdSignature
  cmd_image_file_execution_debugger=$ifeo
} | ConvertTo-Json -Depth 6 -Compress
"""
        result = self._windows_ps("windows_account_snapshot", script, timeout=45)
        result["interpretation_note"] = (
            "Somente inventário: não prova invasão nem autoriza exclusão. Um SID local terminado em -500 costuma ser a conta Administrador interna; "
            "confirme identidade e uso legítimo antes de qualquer alteração. A remoção de perfil e a remoção/desativação de conta são ações distintas. "
            "Se LocalAccounts não estiver disponível em PowerShell de 32 bits, a enumeração pode estar incompleta; detecte a arquitetura do host e valide em PowerShell nativo compatível (por exemplo, x64 ou ARM64), sem presumir ARM."
        )
        return result

    def tools_inventory(self) -> dict[str, Any]:
        if self.system == "windows":
            tools = ("powershell", "pwsh", "cmd", "sfc", "dism", "chkdsk", "wevtutil", "MpCmdRun", "clamscan", "autorunsc", "tcpview")
            return {"operation": "tools_inventory", "platform": "windows", "available_tools": {name: shutil.which(name) is not None for name in tools}}
        if self.system == "linux":
            tools = ("bash", "sh", "zsh", "pwsh", "ps", "systemctl", "journalctl", "ip", "ss", "df", "findmnt", "free", "dpkg-query", "rpm", "clamscan", "lynis", "auditctl", "rkhunter", "chkrootkit")
            return {"operation": "tools_inventory", "platform": "linux", "available_tools": {name: shutil.which(name) is not None for name in tools}}
        return {"operation": "tools_inventory", "platform": self.system, "available_tools": {}}

    def run_action(self, action: str, target: str | None = None, sid: str | None = None) -> dict[str, Any]:
        """Run one allowlisted scan/remediation after ToolRegistry applies the session profile."""
        if self.system == "windows":
            if action == "windows_disable_local_account":
                if not sid or not re.fullmatch(r"S-1-\d+(?:-\d+)+", sid):
                    return {"operation": "diagnostics.action", "platform": "windows", "status": "invalid_sid", "message": "Informe o SID exato retornado pela consulta de contas."}
                if sid.endswith("-500"):
                    return {"operation": "diagnostics.action", "platform": "windows", "status": "protected_target", "message": "A ação não desativa a conta Administrador integrada (RID -500)."}
                if not self.is_admin():
                    return {"operation": "diagnostics.action", "platform": "windows", "status": "requires_elevation", "action": action, "message": "A bridge precisa já estar autorizada como administradora pelo fluxo normal do Windows; o agente não eleva nem contorna UAC."}
                script = f"""
$ErrorActionPreference='Stop'
$targetSid='{sid}'
$target=Get-LocalUser -SID $targetSid -ErrorAction Stop
$currentSid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
if ($currentSid -eq $targetSid) {{ throw 'Refusing to disable the account running the bridge.' }}
$adminGroup=Get-LocalGroup -SID 'S-1-5-32-544'
$admins=@(Get-LocalGroupMember -Group $adminGroup -ErrorAction Stop)
$isMember=@($admins | Where-Object {{ $_.SID -and $_.SID.Value -eq $targetSid }}).Count -gt 0
if (-not $isMember) {{ throw 'Refusing: the selected local account is not a member of local Administrators.' }}
$otherEnabledLocalAdmins=0
foreach ($member in $admins) {{
  if ($member.SID -and $member.SID.Value -ne $targetSid) {{
    try {{ $candidate=Get-LocalUser -SID $member.SID.Value -ErrorAction Stop; if ($candidate.Enabled) {{ $otherEnabledLocalAdmins++ }} }} catch {{}}
  }}
}}
if ($otherEnabledLocalAdmins -lt 1) {{ throw 'Refusing: no other enabled local administrator account could be verified.' }}
Disable-LocalUser -Name $target.Name -ErrorAction Stop
$after=Get-LocalUser -SID $targetSid -ErrorAction Stop
[pscustomobject]@{{action='disabled_local_account';name=$after.Name;sid=$targetSid;enabled=$after.Enabled;other_enabled_local_admins=$otherEnabledLocalAdmins;note='Existing sessions are not terminated; investigate credentials and persistence separately.'}} | ConvertTo-Json -Compress
"""
                result = self._windows_ps("action:windows_disable_local_account", script, timeout=30)
                result.update({"action": action, "mode": "remediation", "requires_reboot_check": False})
                return result
            specs = {
                "windows_defender_quick_scan": ("$ErrorActionPreference='Stop'; Start-MpScan -ScanType QuickScan; 'Quick scan requested. Check Defender protection history for outcomes.'", 900, True),
                "windows_dism_scanhealth": ("& dism.exe /Online /Cleanup-Image /ScanHealth", 900, True),
                "windows_sfc_verifyonly": ("& sfc.exe /verifyonly", 900, True),
                "windows_sfc_scannow": ("& sfc.exe /scannow", 1800, True),
                "windows_dism_restorehealth": ("& dism.exe /Online /Cleanup-Image /RestoreHealth", 1800, True),
            }
            if action not in specs:
                return {"operation": "diagnostics.action", "platform": "windows", "status": "unsupported_action"}
            mode = self.WINDOWS_ACTIONS[action][0]
            script, timeout, needs_admin = specs[action]
            if needs_admin and not self.is_admin():
                return {
                    "operation": "diagnostics.action",
                    "platform": "windows",
                    "status": "requires_elevation",
                    "action": action,
                    "message": "Inicie a bridge com aprovação normal do UAC somente se o proprietário autorizar; o agente não eleva nem contorna o UAC.",
                }
            result = self._windows_ps(f"action:{action}", script, timeout=timeout)
            result.update({"action": action, "mode": mode, "requires_reboot_check": mode == "repair"})
            return result

        if self.system == "linux" and action == "linux_clamav_scan":
            if not target:
                return {"operation": "diagnostics.action", "platform": "linux", "status": "target_required"}
            try:
                selected = Path(target).expanduser().resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                return {"operation": "diagnostics.action", "platform": "linux", "status": "invalid_target", "error": str(exc)}
            if selected == Path(selected.anchor):
                return {"operation": "diagnostics.action", "platform": "linux", "status": "target_too_broad", "error": "A varredura da raiz inteira não é aceita por esta ação limitada."}
            executable = shutil.which("clamscan")
            if not executable:
                return {"operation": "diagnostics.action", "platform": "linux", "status": "tool_unavailable", "error": "clamscan não está instalado."}
            try:
                proc = subprocess.run([executable, "--infected", "--no-summary", str(selected)], cwd=self.process.root, env=self.process._command_environment(), text=True, capture_output=True, timeout=900, check=False)
                return self._response("action:linux_clamav_scan", "linux", proc.returncode, proc.stdout, proc.stderr, target=str(selected), mode="scan", note="Sem opções de remoção/movimentação. Resultados podem incluir falsos positivos e exigem verificação.")
            except subprocess.TimeoutExpired as exc:
                return self._response("action:linux_clamav_scan", "linux", None, ProcessRunner._decode(exc.stdout), ProcessRunner._decode(exc.stderr), timed_out=True, target=str(selected), timeout_seconds=900)
            except OSError as exc:
                return {"operation": "diagnostics.action", "platform": "linux", "status": "execution_error", "error": str(exc)}
        return {"operation": "diagnostics.action", "platform": self.system, "status": "unsupported_action"}
