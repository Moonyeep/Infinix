"""
Test suite for the permission system.

Validates permission profiles, confirmation codes, and safety checks.
"""

import sys
from pathlib import Path

# Add workspace to path
sys.path.insert(0, str(Path(__file__).parent))

from agent_core_permissions import (
    PermissionScope,
    SANDBOX_PROFILE,
    DEVELOPER_PROFILE,
    POWER_USER_PROFILE,
    SYSTEM_ADMIN_PROFILE,
    AVAILABLE_PROFILES,
    CONFIRMATION_CODES,
    get_profile,
    validate_confirmation,
    check_permission,
    is_protected_system_path,
    is_dangerous_command,
)


def test_profiles_exist():
    """Test that all expected profiles are available."""
    assert "sandbox" in AVAILABLE_PROFILES
    assert "developer" in AVAILABLE_PROFILES
    assert "power_user" in AVAILABLE_PROFILES
    assert "system_admin" in AVAILABLE_PROFILES
    print("[PASS] test_profiles_exist")


def test_sandbox_profile():
    """Test sandbox profile has minimal permissions."""
    profile = SANDBOX_PROFILE
    assert profile.name == "sandbox"
    assert PermissionScope.WORKSPACE in profile.scopes
    assert len(profile.scopes) == 1
    assert not profile.requires_confirmation
    print("[PASS] test_sandbox_profile")


def test_developer_profile():
    """Test developer profile has appropriate permissions."""
    profile = DEVELOPER_PROFILE
    assert PermissionScope.WORKSPACE in profile.scopes
    assert PermissionScope.USER_HOME in profile.scopes
    assert PermissionScope.SYSTEM_READ in profile.scopes
    assert PermissionScope.SYSTEM_WRITE not in profile.scopes
    assert PermissionScope.PROCESS_FULL not in profile.scopes
    assert not profile.requires_confirmation
    print("[PASS] test_developer_profile")


def test_power_user_profile():
    """Test power user profile has extensive permissions."""
    profile = POWER_USER_PROFILE
    assert PermissionScope.WORKSPACE in profile.scopes
    assert PermissionScope.SYSTEM_READ in profile.scopes
    assert PermissionScope.SYSTEM_WRITE in profile.scopes
    assert PermissionScope.PROCESS_FULL in profile.scopes
    assert PermissionScope.REGISTRY_READ in profile.scopes
    assert profile.requires_confirmation
    assert "CONFIRM_POWER_USER" in profile.confirmation_message
    print("[PASS] test_power_user_profile")


def test_system_admin_profile():
    """Test system admin profile has all permissions."""
    profile = SYSTEM_ADMIN_PROFILE
    # Should have all scopes
    for scope in PermissionScope:
        assert scope in profile.scopes, f"Missing scope: {scope}"
    assert profile.requires_confirmation
    assert "CONFIRM_ADMIN_ACCESS" in profile.confirmation_message
    print("[PASS] test_system_admin_profile")


def test_get_profile():
    """Test getting profiles by name."""
    profile = get_profile("sandbox")
    assert profile.name == "sandbox"
    
    profile = get_profile("power_user")
    assert profile.name == "power_user"
    
    try:
        get_profile("nonexistent")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unknown permission profile" in str(e)
    
    print("[PASS] test_get_profile")


def test_validate_confirmation():
    """Test confirmation code validation."""
    # Sandbox doesn't require confirmation
    assert validate_confirmation("sandbox", "anything") == True
    
    # Developer doesn't require confirmation
    assert validate_confirmation("developer", "anything") == True
    
    # Power user requires specific code
    assert validate_confirmation("power_user", "CONFIRM_POWER_USER") == True
    assert validate_confirmation("power_user", "wrong_code") == False
    
    # System admin requires specific code
    assert validate_confirmation("system_admin", "CONFIRM_ADMIN_ACCESS") == True
    assert validate_confirmation("system_admin", "wrong_code") == False
    
    print("[PASS] test_validate_confirmation")


def test_check_permission():
    """Test permission checking."""
    # Sandbox should only have WORKSPACE
    allowed, msg = check_permission(SANDBOX_PROFILE, PermissionScope.WORKSPACE)
    assert allowed == True
    
    denied, msg = check_permission(SANDBOX_PROFILE, PermissionScope.SYSTEM_READ)
    assert denied == False
    assert "Permission denied" in msg
    
    # Developer should have SYSTEM_READ
    allowed, msg = check_permission(DEVELOPER_PROFILE, PermissionScope.SYSTEM_READ)
    assert allowed == True
    
    # Developer should NOT have PROCESS_FULL
    denied, msg = check_permission(DEVELOPER_PROFILE, PermissionScope.PROCESS_FULL)
    assert denied == False
    
    print("[PASS] test_check_permission")


def test_protected_system_paths():
    """Test protected system path detection."""
    # These should be protected
    assert is_protected_system_path("C:/Windows/System32/cmd.exe") == True
    assert is_protected_system_path("C:/Program Files/test.txt") == True
    assert is_protected_system_path("C:/Windows/test.dll") == True
    
    # These should NOT be protected
    assert is_protected_system_path("C:/Users/Arthur/test.txt") == False
    assert is_protected_system_path("D:/test.txt") == False
    assert is_protected_system_path("C:/temp/file.txt") == False
    
    print("[PASS] test_protected_system_paths")


def test_dangerous_commands():
    """Test dangerous command detection."""
    # These should be detected as dangerous
    dangerous, pattern = is_dangerous_command("format C:")
    assert dangerous == True
    assert "format " in pattern
    
    dangerous, pattern = is_dangerous_command("del /f /s /q C:\\*.*")
    assert dangerous == True
    
    dangerous, pattern = is_dangerous_command("shutdown /r /t 0")
    assert dangerous == True
    
    dangerous, pattern = is_dangerous_command("rm -rf /")
    assert dangerous == True
    
    # These should NOT be dangerous
    safe, pattern = is_dangerous_command("dir C:\\")
    assert safe == False
    
    safe, pattern = is_dangerous_command("python test.py")
    assert safe == False
    
    safe, pattern = is_dangerous_command("git status")
    assert safe == False
    
    print("[PASS] test_dangerous_commands")


def test_profile_to_dict():
    """Test profile serialization."""
    profile = POWER_USER_PROFILE
    data = profile.to_dict()
    
    assert "name" in data
    assert "scopes" in data
    assert "description" in data
    assert "requires_confirmation" in data
    assert data["name"] == "power_user"
    assert isinstance(data["scopes"], list)
    assert "workspace" in data["scopes"]
    assert "process_full" in data["scopes"]
    
    print("[PASS] test_profile_to_dict")


def test_all_scopes_defined():
    """Test that all expected scopes are defined."""
    expected_scopes = {
        "workspace",
        "user_home",
        "system_read",
        "system_write",
        "process_full",
        "network_full",
        "registry_read",
        "registry_write",
        "service_control",
        "desktop_control",
    }
    
    actual_scopes = {scope.value for scope in PermissionScope}
    assert expected_scopes == actual_scopes, f"Missing: {expected_scopes - actual_scopes}"
    
    print("[PASS] test_all_scopes_defined")


if __name__ == "__main__":
    print("Running permission system tests...\n")
    print("=" * 60)
    
    test_profiles_exist()
    test_sandbox_profile()
    test_developer_profile()
    test_power_user_profile()
    test_system_admin_profile()
    test_get_profile()
    test_validate_confirmation()
    test_check_permission()
    test_protected_system_paths()
    test_dangerous_commands()
    test_profile_to_dict()
    test_all_scopes_defined()
    
    print("=" * 60)
    print("\n[PASS] All 12 tests passed!")
    print("\nPermission system validated successfully.")
    print("Ready for integration into Infinix agent_core.")
