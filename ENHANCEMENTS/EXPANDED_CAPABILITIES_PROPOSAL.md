# Proposta de Expansão de Capacidades do Agente Infinix

## Objetivo

Expandir as capacidades do agente Infinix para permitir acesso controlado a todo o sistema computacional, não apenas ao workspace configurado, mantendo princípios de segurança robustos.

## Análise das Limitações Atuais

### 1. Workspace Restrito (`agent_core/workspace.py`)
- **Problema**: O agente só pode ler/escrever arquivos dentro de `allowed_roots`
- **Impacto**: Impossível acessar arquivos do sistema, configurações globais, ou outros diretórios
- **Código Problemático**:
```python
def resolve(self, relative: str) -> Path:
    raw = Path(str(relative)).expanduser()
    candidate = raw.resolve() if raw.is_absolute() else (self.root / raw).resolve()
    if any(candidate == base or base in candidate.parents for base in self.allowed_roots):
        return candidate
    roots = ", ".join(str(p) for p in self.allowed_roots)
    raise WorkspaceError(f"path is outside allowed workspace roots: {relative} (allowed: {roots})")
```

### 2. Comandos Shell Limitados (`agent_core/process.py`)
- **Problema**: Apenas comandos allowlistados podem ser executados via `process.test`
- **Allowlist atual**: `{"python", "python3", "node", "npm", "pnpm", "pytest", "git"}`
- **Impacto**: Impossível executar ferramentas do sistema como `ipconfig`, `tasklist`, `reg`, etc.

### 3. Terminal.run Restrito
- Embora `terminal.run` exista, ele ainda opera sob políticas restritivas
- Não há ferramentas para gerenciamento de sistema completo

## Proposta de Expansão Controlada

### Nível 1: Sistema de Permissões Granulares

Criar um sistema de permissões baseado em escopos:

```python
# Novo arquivo: agent_core/permissions.py
from enum import Enum
from dataclasses import dataclass
from typing import Set

class PermissionScope(Enum):
    WORKSPACE = "workspace"           # Acesso total ao workspace
    USER_HOME = "user_home"           # Acesso à pasta do usuário
    SYSTEM_READ = "system_read"       # Leitura de arquivos do sistema
    SYSTEM_WRITE = "system_write"     # Escrita em áreas permitidas do sistema
    PROCESS_FULL = "process_full"     # Execução de qualquer comando
    NETWORK_FULL = "network_full"     # Acesso total à rede
    REGISTRY_READ = "registry_read"   # Leitura do registro Windows
    REGISTRY_WRITE = "registry_write" # Escrita no registro Windows
    SERVICE_CONTROL = "service_control" # Controle de serviços

@dataclass
class PermissionProfile:
    name: str
    scopes: Set[PermissionScope]
    description: str
    
# Perfis predefinidos
PROFILES = {
    "sandbox": PermissionProfile(
        name="sandbox",
        scopes={PermissionScope.WORKSPACE},
        description="Apenas workspace - máximo isolamento"
    ),
    "developer": PermissionProfile(
        name="developer",
        scopes={
            PermissionScope.WORKSPACE,
            PermissionScope.USER_HOME,
            PermissionScope.SYSTEM_READ,
        },
        description="Desenvolvimento com leitura do sistema"
    ),
    "power_user": PermissionProfile(
        name="power_user",
        scopes={
            PermissionScope.WORKSPACE,
            PermissionScope.USER_HOME,
            PermissionScope.SYSTEM_READ,
            PermissionScope.SYSTEM_WRITE,
            PermissionScope.PROCESS_FULL,
            PermissionScope.REGISTRY_READ,
        },
        description="Usuário avançado com controle quase total"
    ),
    "system_admin": PermissionProfile(
        name="system_admin",
        scopes=set(PermissionScope),  # Todas as permissões
        description="Acesso total ao sistema (requer confirmação explícita)"
    ),
}
```

### Nível 2: Workspace Expandido

Modificar `agent_core/workspace.py` para suportar múltiplos escopos:

```python
class Workspace:
    def __init__(self, root: Path, backup_dir: Path | None = None, 
                 allowed_roots: list[Path] | None = None,
                 permission_profile: str = "sandbox") -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        
        # Carregar perfil de permissões
        profile = PROFILES.get(permission_profile, PROFILES["sandbox"])
        self.permissions = profile.scopes
        
        # Configurar raízes permitidas baseado nas permissões
        configured = [Path(p).expanduser().resolve() for p in (allowed_roots or [])]
        
        # Adicionar User Home se permitido
        if PermissionScope.USER_HOME in self.permissions:
            user_home = Path.home()
            configured.append(user_home)
        
        self.allowed_roots = tuple(dict.fromkeys([self.root, *configured]))
        self.backup_dir = (backup_dir or self.root / ".zeroscript" / "backups").resolve()
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def resolve(self, relative: str) -> Path:
        raw = Path(str(relative)).expanduser()
        candidate = raw.resolve() if raw.is_absolute() else (self.root / raw).resolve()
        
        # Verificar se está em alguma raiz permitida
        if any(candidate == base or base in candidate.parents for base in self.allowed_roots):
            return candidate
        
        # Se tiver permissão SYSTEM_READ/SYSTEM_WRITE, permitir caminhos absolutos
        if PermissionScope.SYSTEM_READ in self.permissions or PermissionScope.SYSTEM_WRITE in self.permissions:
            if raw.is_absolute():
                # Validar que não é um caminho crítico do sistema
                if not self._is_protected_system_path(candidate):
                    return candidate
        
        roots = ", ".join(str(p) for p in self.allowed_roots)
        raise WorkspaceError(
            f"path is outside allowed workspace roots: {relative}\n"
            f"Allowed roots: {roots}\n"
            f"Current permission profile: {self.permissions}"
        )
    
    def _is_protected_system_path(self, path: Path) -> bool:
        """Verificar se o caminho é crítico para o sistema."""
        protected_paths = [
            Path("C:/Windows"),
            Path("C:/Program Files"),
            Path("C:/Program Files (x86)"),
            Path("C:/System Volume Information"),
            Path("C:/Recovery"),
        ]
        
        # Permitir leitura mesmo em paths protegidos se SYSTEM_READ estiver ativo
        # mas bloquear escrita
        if PermissionScope.SYSTEM_WRITE not in self.permissions:
            for protected in protected_paths:
                if protected in path.parents or path == protected:
                    return True
        
        return False
```

### Nível 3: Process Runner Expandido

Modificar `agent_core/process.py` para suportar execução completa:

```python
class ProcessRunner:
    # Expandir allowlist ou remover baseada em permissões
    ALLOWED_BASIC = {"python", "python3", "node", "npm", "pnpm", "pytest", "git"}
    ALLOWED_SYSTEM = {
        "ipconfig", "ping", "tracert", "nslookup",      # Rede
        "tasklist", "taskkill", "wmic",                  # Processos
        "dir", "cd", "type", "find", "findstr",          # Arquivos
        "systeminfo", "driverquery",                     # Sistema
        "reg", "sc", "net",                              # Serviços/Registro
        "powershell", "pwsh", "cmd",                     # Shells
        "curl", "wget",                                  # Download
        "where", "which",                                # Localização
    }
    
    def __init__(self, root: Path, permission_profile: str = "sandbox") -> None:
        self.root = Path(root).resolve()
        profile = PROFILES.get(permission_profile, PROFILES["sandbox"])
        self.permissions = profile.scopes
    
    def test(self, command: list[str], timeout: int = 300) -> dict[str, Any]:
        executable = Path(command[0]).name.casefold() if command else ""
        
        # Se tiver PROCESS_FULL, permitir qualquer comando (com validações de segurança)
        if PermissionScope.PROCESS_FULL in self.permissions:
            return self._run_unrestricted(command, timeout)
        
        # Caso contrário, usar allowlist tradicional
        current_python = Path(sys.executable).name.casefold()
        if not command or (executable not in self.ALLOWED_BASIC and 
                          executable not in self.ALLOWED_SYSTEM and
                          executable != current_python):
            raise ProcessPolicyError(
                f"command executable is not allowlisted: {executable}\n"
                f"Current profile only allows: {self.ALLOWED_BASIC}\n"
                f"Upgrade to 'developer' or 'power_user' profile for more commands"
            )
        
        # Validações de segurança básicas
        if any(token in {"format", "shutdown", "sudo"} for token in command):
            raise ProcessPolicyError("destructive command token is blocked")
        
        timeout = max(1, min(int(timeout), 900))
        env = {"PATH": self._command_environment().get("PATH", ""), "PYTHONUNBUFFERED": "1"}
        proc = subprocess.run(command, cwd=self.root, env=env, text=True, capture_output=True, timeout=timeout)
        return {
            "command": command, 
            "returncode": proc.returncode, 
            "stdout": proc.stdout[-self.OUTPUT_LIMIT:], 
            "stderr": proc.stderr[-self.OUTPUT_LIMIT:]
        }
    
    def _run_unrestricted(self, command: list[str], timeout: int) -> dict[str, Any]:
        """Executar comando sem restrições de allowlist (apenas validações críticas)."""
        # Bloquear apenas comandos verdadeiramente destrutivos
        dangerous_patterns = [
            "format ", "del /f /s /q C:\\", "rd /s /q C:\\",
            "shutdown /r /t 0", "rm -rf /",
        ]
        
        cmd_str = " ".join(command).lower()
        for pattern in dangerous_patterns:
            if pattern in cmd_str:
                raise ProcessPolicyError(
                    f"Command matches dangerous pattern: {pattern}\n"
                    "This operation is blocked even with full permissions."
                )
        
        timeout = max(1, min(int(timeout), 900))
        env = self._command_environment()
        proc = subprocess.run(command, cwd=self.root, env=env, text=True, capture_output=True, timeout=timeout)
        return {
            "command": command,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-self.OUTPUT_LIMIT:],
            "stderr": proc.stderr[-self.OUTPUT_LIMIT:],
            "mode": "unrestricted"
        }
```

### Nível 4: Novas Ferramentas de Sistema

Adicionar novas ferramentas ao `ToolRegistry`:

```python
# Em agent_core/tools.py, adicionar:

if PermissionScope.SYSTEM_READ in self.permissions:
    self.register(ToolSpec(
        "system.info",
        "Get comprehensive system information (OS, hardware, network)",
        "system.read",
        {"type": "object", "properties": {"detail_level": {"type": "string", "enum": ["basic", "full"]}}},
        "low"
    ), self._system_info)
    
    self.register(ToolSpec(
        "filesystem.search",
        "Search for files across the entire system",
        "system.read",
        {
            "type": "object",
            "required": ["pattern"],
            "properties": {
                "pattern": {"type": "string"},
                "root_path": {"type": "string", "default": "C:\\"},
                "file_type": {"type": "string"},
                "max_results": {"type": "integer", "default": 100}
            }
        },
        "medium"
    ), self._filesystem_search)

if PermissionScope.PROCESS_FULL in self.permissions:
    self.register(ToolSpec(
        "process.list",
        "List all running processes with details",
        "process.full",
        {"type": "object", "properties": {"include_details": {"type": "boolean", "default": True}}},
        "low"
    ), self._process_list)
    
    self.register(ToolSpec(
        "process.manage",
        "Start, stop, or manage system processes",
        "process.full",
        {
            "type": "object",
            "required": ["action", "identifier"],
            "properties": {
                "action": {"type": "string", "enum": ["start", "stop", "restart"]},
                "identifier": {"type": "string"},
                "identifier_type": {"type": "string", "enum": ["pid", "name", "service"]}
            }
        },
        "high"
    ), self._process_manage)

if PermissionScope.REGISTRY_READ in self.permissions:
    self.register(ToolSpec(
        "registry.read",
        "Read Windows registry values",
        "registry.read",
        {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string"},
                "value_name": {"type": "string"}
            }
        },
        "medium"
    ), self._registry_read)
```

### Nível 5: Interface de Gerenciamento de Permissões

Criar ferramenta para gerenciar permissões dinamicamente:

```python
self.register(ToolSpec(
    "permissions.set_profile",
    "Change the agent's permission profile (requires confirmation)",
    "admin",
    {
        "type": "object",
        "required": ["profile", "confirmation_code"],
        "properties": {
            "profile": {"type": "string", "enum": list(PROFILES.keys())},
            "confirmation_code": {"type": "string", "description": "User-provided confirmation code"}
        }
    },
    "critical"
), self._set_permission_profile)

self.register(ToolSpec(
    "permissions.current",
    "Show current permission profile and capabilities",
    "system.read",
    {"type": "object"},
    "low"
), self._show_permissions)
```

## Implementação Prática

### Passo 1: Criar Sistema de Permissões
- Arquivo: `agent_core/permissions.py`
- Definir enums, perfis e lógica de verificação

### Passo 2: Modificar Workspace
- Atualizar `agent_core/workspace.py` para usar perfis de permissão
- Adicionar suporte a caminhos absolutos condicionais

### Passo 3: Expandir Process Runner
- Atualizar `agent_core/process.py` para suportar execução irrestrita condicional
- Adicionar validações de segurança críticas

### Passo 4: Adicionar Novas Ferramentas
- Estender `agent_core/tools.py` com ferramentas de sistema
- Implementar handlers para cada nova ferramenta

### Passo 5: Atualizar Policy Broker
- Modificar `agent_core/policy.py` para incluir novos scopes
- Adicionar regras de precedência para permissões expandidas

### Passo 6: Interface de Usuário
- Atualizar extensão do navegador para mostrar perfil atual
- Adicionar UI para mudança de perfil com confirmação

## Considerações de Segurança

### Proteções Mantidas
1. **Confirmação Explícita**: Mudança de perfil requer código de confirmação
2. **Logs Detalhados**: Todas as ações fora do workspace são logadas
3. **Backup Automático**: Modificações em sistema criam pontos de restauração
4. **Padrão Conservador**: Perfil inicial continua sendo "sandbox"
5. **Bloqueio Crítico**: Comandos verdadeiramente destrutivos sempre bloqueados

### Auditoria e Rastreabilidade
- Cada ação fora do workspace gera evento em `events.jsonl`
- Snapshots do estado do sistema antes/depois de modificações
- Histórico completo de mudanças de perfil de permissão

## Benefícios

1. **Flexibilidade**: Agente pode operar em diferentes níveis de acesso conforme necessidade
2. **Segurança Gradual**: Usuário controla exatamente quanta confiança dar ao agente
3. **Casos de Uso Expandidos**:
   - Automação de tarefas do sistema
   - Gerenciamento de arquivos em múltiplos locais
   - Diagnóstico e troubleshooting completo
   - Integração com ferramentas externas
4. **Transparência**: Usuário sempre sabe quais permissões o agente tem

## Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| Escalação inadvertida de privilégios | Confirmação explícita + código para perfis elevados |
| Ações destrutivas acidentais | Bloqueio hard-coded de padrões perigosos |
| Vazamento de dados sensíveis | Logs de todas as leituras fora do workspace |
| Comprometimento do sistema | Perfis podem ser revertidos instantaneamente |

## Exemplo de Uso

```python
# Inicializar agente com perfil power_user
registry = ToolRegistry(
    workspace=Workspace(root, permission_profile="power_user"),
    policy=PolicyBroker(),
    events=EventLog(state / "events.jsonl")
)

# Acessar arquivo em qualquer lugar
result = registry.call("file.read", {"path": "C:\\Users\\USERNAME\\Documents\\notes.txt"})

# Executar comando do sistema
result = registry.call("terminal.run", {
    "shell": "powershell",
    "command": "Get-Process | Where-Object {$_.CPU -gt 50}"
})

# Buscar arquivos em todo o sistema
result = registry.call("filesystem.search", {
    "pattern": "*.config",
    "root_path": "C:\\",
    "max_results": 50
})

# Reverter para sandbox quando terminar
registry.call("permissions.set_profile", {
    "profile": "sandbox",
    "confirmation_code": "USER_CONFIRM_123"
})
```

## Conclusão

Esta proposta transforma o Infinix de um agente confinado ao workspace em um assistente de sistema completo, mantendo princípios de segurança através de:
- Permissões granulares e explícitas
- Confirmações para ações críticas
- Auditoria completa
- Padrões conservadores por default

O agente ganha capacidade real de automatizar tarefas em todo o computador, tornando-se uma ferramenta verdadeiramente poderosa para produtividade e automação.
