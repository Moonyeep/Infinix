"""
Permission system for Infinix - Granular access control.

Defines permission scopes, profiles, and validation logic for expanding
agent capabilities beyond the workspace while maintaining security.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Set


class PermissionScope(Enum):
    """Granular permission scopes for Infinix agent."""
    
    WORKSPACE = "workspace"               # Full access to workspace
    USER_HOME = "user_home"               # Access to user's home directory
    SYSTEM_READ = "system_read"           # Read files anywhere on system
    SYSTEM_WRITE = "system_write"         # Write to non-critical system areas
    PROCESS_FULL = "process_full"         # Execute any command (with safety checks)
    NETWORK_FULL = "network_full"         # Unrestricted network access
    REGISTRY_READ = "registry_read"       # Read Windows registry
    REGISTRY_WRITE = "registry_write"     # Write to Windows registry
    SERVICE_CONTROL = "service_control"   # Start/stop/manage Windows services
    DESKTOP_CONTROL = "desktop_control"   # Control desktop applications


@dataclass(frozen=True)
class PermissionProfile:
    """A named collection of permission scopes."""
    name: str
    scopes: frozenset[PermissionScope]
    description: str
    requires_confirmation: bool = False
    confirmation_message: str = ""
    
    def has_scope(self, scope: PermissionScope) -> bool:
        """Check if this profile includes a specific scope."""
        return scope in self.scopes
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "scopes": [s.value for s in self.scopes],
            "description": self.description,
            "requires_confirmation": self.requires_confirmation,
        }


# Predefined permission profiles from most restrictive to most permissive
SANDBOX_PROFILE = PermissionProfile(
    name="sandbox",
    scopes=frozenset({PermissionScope.WORKSPACE}),
    description="Maximum isolation - only workspace access",
    requires_confirmation=False,
)

DEVELOPER_PROFILE = PermissionProfile(
    name="developer",
    scopes=frozenset({
        PermissionScope.WORKSPACE,
        PermissionScope.USER_HOME,
        PermissionScope.SYSTEM_READ,
    }),
    description="Development with system read access",
    requires_confirmation=False,
)

POWER_USER_PROFILE = PermissionProfile(
    name="power_user",
    scopes=frozenset({
        PermissionScope.WORKSPACE,
        PermissionScope.USER_HOME,
        PermissionScope.SYSTEM_READ,
        PermissionScope.SYSTEM_WRITE,
        PermissionScope.PROCESS_FULL,
        PermissionScope.REGISTRY_READ,
        PermissionScope.NETWORK_FULL,
    }),
    description="Advanced user with near-total system control",
    requires_confirmation=True,
    confirmation_message=(
        "WARNING: This profile grants extensive system access including:\n"
        "- Read/write files across the system\n"
        "- Execute any command\n"
        "- Access registry and network\n\n"
        "Only use this if you fully trust the agent. "
        "Type 'CONFIRM_POWER_USER' to proceed."
    ),
)

SYSTEM_ADMIN_PROFILE = PermissionProfile(
    name="system_admin",
    scopes=frozenset(PermissionScope),  # All permissions
    description="Full system access (requires explicit confirmation)",
    requires_confirmation=True,
    confirmation_message=(
        "CRITICAL WARNING: This grants COMPLETE system access including:\n"
        "- Modify any file\n"
        "- Execute any command\n"
        "- Control services and registry\n"
        "- Full desktop control\n\n"
        "This is DANGEROUS and should only be used by experts.\n"
        "Type 'CONFIRM_ADMIN_ACCESS' to proceed."
    ),
)

# Registry of all available profiles
AVAILABLE_PROFILES: dict[str, PermissionProfile] = {
    profile.name: profile for profile in [
        SANDBOX_PROFILE,
        DEVELOPER_PROFILE,
        POWER_USER_PROFILE,
        SYSTEM_ADMIN_PROFILE,
    ]
}

# Confirmation codes for elevated profiles
CONFIRMATION_CODES: dict[str, str] = {
    "power_user": "CONFIRM_POWER_USER",
    "system_admin": "CONFIRM_ADMIN_ACCESS",
}


def get_profile(name: str) -> PermissionProfile:
    """Get a permission profile by name."""
    if name not in AVAILABLE_PROFILES:
        available = ", ".join(AVAILABLE_PROFILES.keys())
        raise ValueError(
            f"Unknown permission profile: {name}\n"
            f"Available profiles: {available}"
        )
    return AVAILABLE_PROFILES[name]


def validate_confirmation(profile_name: str, confirmation_code: str) -> bool:
    """Validate confirmation code for elevated profiles."""
    expected_code = CONFIRMATION_CODES.get(profile_name)
    if expected_code is None:
        # Profile doesn't require confirmation
        return True
    return confirmation_code == expected_code


def list_profiles() -> list[dict]:
    """List all available profiles with their details."""
    return [profile.to_dict() for profile in AVAILABLE_PROFILES.values()]


def check_permission(
    current_profile: PermissionProfile,
    required_scope: PermissionScope
) -> tuple[bool, str]:
    """
    Check if current profile has the required permission scope.
    
    Returns:
        Tuple of (has_permission, message)
    """
    if current_profile.has_scope(required_scope):
        return True, f"Permission granted: {required_scope.value}"
    
    return False, (
        f"Permission denied: {required_scope.value} not in profile '{current_profile.name}'\n"
        f"Current scopes: {[s.value for s in current_profile.scopes]}\n"
        f"Upgrade to a profile with this permission to proceed."
    )


# Protected system paths that should never be modified
PROTECTED_SYSTEM_PATHS = [
    "C:/Windows",
    "C:/Windows/System32",
    "C:/Program Files",
    "C:/Program Files (x86)",
    "C:/System Volume Information",
    "C:/Recovery",
    "C:/$Recycle.Bin",
    "C:/Boot",
    "C:/EFI",
]


def is_protected_system_path(path: str) -> bool:
    """Check if a path is a protected system location."""
    from pathlib import Path
    
    try:
        test_path = Path(path).resolve()
    except (ValueError, OSError):
        return False
    
    for protected in PROTECTED_SYSTEM_PATHS:
        try:
            protected_path = Path(protected).resolve()
            if protected_path in test_path.parents or test_path == protected_path:
                return True
        except (ValueError, OSError):
            continue
    
    return False


# Dangerous command patterns that should always be blocked
DANGEROUS_COMMAND_PATTERNS = [
    "format ",
    "del /f /s /q c:\\",
    "del /f /s /q c:",
    "rd /s /q c:\\",
    "rd /s /q c:",
    "shutdown /r /t 0",
    "shutdown -r -t 0",
    "rm -rf /",
    "rm -rf /*",
    ":(){ :|:& };:",  # Fork bomb
    "mkfs",
    "fdisk",
    "diskpart",
]


def is_dangerous_command(command: str) -> tuple[bool, str | None]:
    """
    Check if a command matches dangerous patterns.
    
    Returns:
        Tuple of (is_dangerous, matched_pattern)
    """
    cmd_lower = command.lower().strip()
    
    for pattern in DANGEROUS_COMMAND_PATTERNS:
        if pattern in cmd_lower:
            return True, pattern
    
    return False, None
