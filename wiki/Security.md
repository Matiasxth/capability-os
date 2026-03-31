# Security Guide

Complete security reference for Capability OS. This covers the progressive security model, authentication, execution sandboxing, plugin policy enforcement, and hardening best practices.

---

## Table of Contents

- [Progressive Security Model](#progressive-security-model)
- [Authentication](#authentication)
  - [JWT Token System](#jwt-token-system)
  - [User Roles](#user-roles)
  - [Token Lifecycle](#token-lifecycle)
- [Execution Sandbox](#execution-sandbox)
  - [L2 Process Sandbox](#l2-process-sandbox)
  - [L3 Docker Sandbox](#l3-docker-sandbox)
- [Security Hardening](#security-hardening)
  - [Command Injection Prevention](#command-injection-prevention)
  - [Path Traversal Prevention](#path-traversal-prevention)
  - [Docker Hardening](#docker-hardening)
  - [CORS Configuration](#cors-configuration)
- [Plugin Policy Engine](#plugin-policy-engine)
  - [Permission Scopes](#permission-scopes)
  - [Policy Rules](#policy-rules)
  - [Enforcement Points](#enforcement-points)
  - [Audit Trail](#audit-trail)
- [Best Practices](#best-practices)
- [Security Audit Script](#security-audit-script)

---

## Progressive Security Model

Capability OS uses a three-level progressive security classification for all tool and capability executions. The `SecurityService` (`system/core/security/security_service.py`) classifies every operation before it runs.

### Level 1 -- FREE

Safe, read-only operations that require no confirmation.

**Examples**: Read a file, list directory contents, search memory, get system status, view workspace info.

**Behavior**: Executes immediately without user interaction.

### Level 2 -- CONFIRM

Write or modify operations within the user's workspace. The user must click "Allow" in the UI.

**Examples**: Write a file, create a directory, run a command, install a package.

**Behavior**: The UI shows a confirmation dialog with the operation details. The user clicks "Allow" or "Deny".

### Level 3 -- PROTECTED

Critical or destructive operations. Requires password authentication.

**Examples**: Delete system files, access paths outside workspaces, run dangerous commands (`rm -rf`, `format`, `shutdown`), modify security rules.

**Behavior**: The UI prompts for the user's password before executing.

### Classification Logic

The `SecurityService.classify()` method checks in this order:

1. **Critical path check**: Does any input path contain a critical location pattern (system directories, registry, etc.)?
2. **Dangerous command check**: Does the command field contain dangerous commands (`rm -rf`, `del /s`, `format`, `shutdown`, `reboot`, `mkfs`, `fdisk`, `registry`)?
3. **Explicit protected rules**: Is the tool/capability in the protected list?
4. **Outside workspace check**: Is this a write operation targeting a path outside all registered workspaces?
5. **Explicit free rules**: Is the tool/capability in the free list?
6. **Explicit confirm rules**: Is the tool/capability in the confirm list?
7. **Default**: If nothing matches, default to CONFIRM (safe fallback -- unknown operations require approval)

### Security Rules File

Tool and capability classifications are stored in `system/core/security/security_rules.json`:

```json
{
  "free": {
    "tools": ["filesystem_read_file", "filesystem_list_directory", "memory_recall", ...],
    "capabilities": ["read_file", "list_directory", "search_memory", ...]
  },
  "confirm": {
    "tools": ["filesystem_write_file", "filesystem_create_directory", "run_command", ...],
    "capabilities": ["write_file", "create_directory", "execute_command", ...]
  },
  "protected": {
    "tools": ["filesystem_delete_directory", "system_shutdown", ...],
    "capabilities": ["delete_directory", "modify_security_rules", ...]
  },
  "critical_paths": {
    "patterns": ["system32", "windows\\system", "/etc/", "/usr/bin/", "registry"]
  }
}
```

---

## Authentication

### JWT Token System

Authentication uses JSON Web Tokens (JWT) with HMAC-SHA256 signing. The implementation is in `system/core/auth/jwt_service.py`.

#### How It Works

1. **Secret key generation**: On first run, a 128-character hex secret is auto-generated and saved to `workspace/jwt_secret.key` with restricted file permissions (600)
2. **Token creation**: `JWTService.create_token(user_id, role)` generates a signed token
3. **Token validation**: `JWTService.validate_token(token)` decodes and verifies the token
4. **Token refresh**: `JWTService.refresh_token(token)` returns a fresh token if the current one is still valid

#### Token Payload

```json
{
  "user_id": "abc123",
  "role": "owner",
  "iat": 1711800000,
  "exp": 1711886400
}
```

| Field | Description |
|---|---|
| `user_id` | Unique user identifier |
| `role` | User role (`owner`, `admin`, `user`, `viewer`) |
| `iat` | Issued at (UTC timestamp) |
| `exp` | Expiration time (UTC timestamp) |

#### API Authentication

Include the JWT token in the `Authorization` header:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### User Roles

Four roles with hierarchical permissions. Defined in `system/core/auth/user_registry.py`:

| Role | Workspaces | Agents | Max Security Level | Supervisor | Create Agents | Create Skills |
|---|---|---|---|---|---|---|
| **owner** | All (`*`) | All (`*`) | 10 | Yes | Yes | Yes |
| **admin** | All (`*`) | All (`*`) | 7 | Yes | Yes | Yes |
| **user** | Assigned only | Assigned only | 3 | No | No | No |
| **viewer** | Assigned only | Assigned only | 0 | No | No | No |

**Max Security Level** determines which operations a user can approve:
- Level 10 (owner): Can approve any operation
- Level 7 (admin): Can approve most operations
- Level 3 (user): Can only approve basic operations
- Level 0 (viewer): Cannot approve any operations (read-only)

### Token Lifecycle

```
1. First run: POST /auth/setup
   - Creates owner account with bcrypt-hashed password
   - Returns JWT token
   - Emits "auth_setup_complete" event

2. Login: POST /auth/login
   - Validates credentials against bcrypt hash
   - Returns fresh JWT token (24h expiry)

3. Authenticated requests: GET/POST with Authorization header
   - AuthMiddleware validates token on each request
   - Expired tokens return 401

4. Token refresh: handled automatically by frontend
   - Refreshes before expiry
   - Invalid refresh returns to login
```

### Auth API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/auth/status` | Check if auth is configured (has owner) |
| `POST` | `/auth/setup` | Create initial owner account |
| `POST` | `/auth/login` | Login with username/password |
| `GET` | `/auth/me` | Get current user info from token |
| `GET` | `/auth/users` | List all users (admin+) |
| `POST` | `/auth/users` | Create a new user (admin+) |
| `PUT` | `/auth/users/{user_id}` | Update user details (admin+) |
| `DELETE` | `/auth/users/{user_id}` | Delete a user (owner only) |

### Password Storage

Passwords are hashed with **bcrypt** before storage. The `UserRegistry` uses the `bcrypt` library with automatic salt generation. Raw passwords are never stored or logged.

---

## Execution Sandbox

The sandbox system provides two levels of isolation for code execution, managed by `SandboxManager` (`system/core/sandbox/sandbox_manager.py`) and the Sandbox plugin (`system/plugins/sandbox/plugin.py`).

### L2 Process Sandbox

Runs code in a separate subprocess with resource limits.

**Features**:
- Process isolation (separate PID)
- Configurable timeout (default: 30 seconds)
- Stdout/stderr capture
- Exit code monitoring
- Works on all platforms

**Configuration**:

```json
{
  "sandbox": {
    "process_timeout": 30
  }
}
```

### L3 Docker Sandbox

Runs code in an isolated Docker container for maximum security.

**Features**:
- Full filesystem isolation
- Network isolation (optional)
- Memory limits (default: 512MB)
- CPU limits
- Read-only root filesystem
- No privilege escalation (`no-new-privileges`)
- Automatic container cleanup
- Configurable timeout (default: 60 seconds)

**Configuration**:

```json
{
  "sandbox": {
    "docker_timeout": 60,
    "docker_image": "python:3.12-slim",
    "max_memory_mb": 512
  }
}
```

**Requirements**: Docker must be installed and the Docker daemon must be running. The `SandboxPlugin` checks Docker availability at initialization and falls back to L2 if unavailable.

---

## Security Hardening

These are the security improvements that have been implemented across the codebase.

### Command Injection Prevention

**What was fixed**: All subprocess calls now use list-based arguments instead of shell strings. The `subprocess.run(..., shell=True)` pattern has been eliminated.

**Before** (vulnerable):

```python
# DANGEROUS: shell=True with user input
subprocess.run(f"git clone {url}", shell=True)
```

**After** (safe):

```python
# SAFE: list arguments, no shell interpretation
subprocess.run(["git", "clone", url], shell=False)
```

Dangerous command patterns (`rm -rf`, `del /s`, `format`, `shutdown`, `reboot`, `mkfs`, `fdisk`, `registry`) are detected by the `SecurityService` and escalated to PROTECTED level.

### Path Traversal Prevention

**What was fixed**: A `PathValidator` (`system/core/workspace/path_validator.py`) ensures all file operations stay within authorized workspace boundaries.

**Protection mechanism**:

```python
# The PathValidator uses Path.resolve() + is_relative_to()
resolved_path = Path(user_input).resolve()
if not resolved_path.is_relative_to(workspace_root):
    raise SecurityError("Path traversal attempt blocked")
```

**Blocked patterns**:
- `../../../etc/passwd`
- Symbolic link escapes
- Absolute paths outside workspace
- Null byte injection

### Docker Hardening

The `docker-compose.yml` includes several security options:

```yaml
services:
  capability-os:
    security_opt:
      - no-new-privileges:true    # Prevent privilege escalation
    ports:
      - "127.0.0.1:8000:8000"    # Loopback only (not 0.0.0.0)
      - "127.0.0.1:8001:8001"

  chrome:
    expose:
      - "3000"                     # Internal only (not published to host)
```

**Key hardening measures**:
- `no-new-privileges`: Prevents setuid/setgid escalation inside containers
- Loopback port binding: API only accessible from localhost, not from the network
- Chrome isolation: The browser service is only accessible from the `capability-os` container via internal Docker networking
- Named volumes: Data persists safely in Docker-managed volumes

### CORS Configuration

The API server sets CORS headers on all responses:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Headers: Content-Type, Authorization
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
```

**Production recommendation**: Restrict `Access-Control-Allow-Origin` from `*` to your specific frontend origin:

```python
# Instead of "*", use a specific origin
self.send_header("Access-Control-Allow-Origin", "http://localhost:5173")
```

Or configure it via the `CORS_ORIGIN` environment variable when deploying behind a reverse proxy.

---

## Plugin Policy Engine

The policy engine controls what permissions plugins have at runtime. It is defined in `system/sdk/policy.py` and uses the permission hierarchy from `system/sdk/permissions.py`.

### Permission Scopes

Permissions are hierarchical with wildcard support:

```
*                          # All permissions (superuser)
filesystem.*               # All filesystem permissions
filesystem.read            # Only file reading
filesystem.write           # Only file writing
```

#### Complete Permission Tree

| Category | Scopes |
|---|---|
| `filesystem` | `read`, `write`, `delete`, `create_directory` |
| `network` | `http`, `websocket`, `dns` |
| `execution` | `subprocess`, `docker`, `script` |
| `browser` | `navigate`, `screenshot`, `interact`, `read_text` |
| `memory` | `read`, `write`, `semantic`, `markdown` |
| `event_bus` | `emit`, `subscribe` |
| `settings` | `read`, `write` |
| `users` | `read`, `manage` |
| `plugins` | `install`, `reload`, `configure` |
| `workspaces` | `read`, `write`, `delete` |
| `agents` | `read`, `write`, `execute` |
| `capabilities` | `read`, `register`, `execute` |
| `tools` | `read`, `register`, `execute` |
| `scheduler` | `read`, `create`, `delete`, `run` |
| `workflows` | `read`, `create`, `execute` |
| `mcp` | `servers`, `tools` |
| `a2a` | `agents`, `delegate` |
| `supervisor` | `invoke`, `health`, `approve` |
| `voice` | `transcribe`, `synthesize` |

### Policy Rules

Rules are defined in a JSON policy file and evaluated in priority order (highest priority first). The first matching rule wins.

```json
{
  "default_effect": "deny",
  "rules": [
    {
      "id": "builtin-allow-all",
      "description": "Builtin plugins have unrestricted access",
      "target": {
        "tags": ["builtin"]
      },
      "permissions": ["*"],
      "effect": "allow",
      "priority": 100
    },
    {
      "id": "external-read-only",
      "description": "External plugins can only read",
      "target": {
        "tags": ["external"]
      },
      "permissions": [
        "filesystem.read",
        "memory.read",
        "tools.read",
        "capabilities.read"
      ],
      "effect": "allow",
      "priority": 50
    },
    {
      "id": "deny-dangerous",
      "description": "Block dangerous operations for all non-builtin",
      "target": {},
      "permissions": [
        "execution.docker",
        "settings.write",
        "users.manage"
      ],
      "effect": "deny",
      "priority": 90
    }
  ]
}
```

#### Rule Structure

```python
class PolicyRule(TypedDict):
    id: str              # Unique rule identifier
    description: str     # Human-readable description
    target: PolicyTarget # Who this rule applies to
    permissions: list[str]  # Permission scopes covered
    effect: str          # "allow" or "deny"
    priority: int        # Higher = evaluated first
```

#### Target Matching

```python
class PolicyTarget(TypedDict, total=False):
    plugin_ids: list[str]      # Specific plugin IDs
    user_roles: list[str]      # Specific user roles
    workspace_ids: list[str]   # Specific workspace IDs
    tags: list[str]            # Plugin tags (e.g. "builtin", "external")
```

An empty target (`{}`) matches all requests.

### Enforcement Points

The policy engine enforces permissions at three levels:

#### 1. Plugin Load Time

When a plugin is loaded, `check_plugin_permissions()` verifies all declared permissions:

```python
denied = engine.check_plugin_permissions(
    plugin_id="ext.my-plugin",
    declared_permissions=["filesystem.write", "network.http"],
    plugin_tags=["external"],
)
if denied:
    raise PermissionDeniedError(...)
```

#### 2. Service Resolution

When a plugin calls `ctx.get_service()`, the context checks `service.<ContractName>` permission:

```python
# This internally checks "service.ToolRegistryContract" permission
tool_registry = ctx.get_service(ToolRegistryContract)
```

Plugins tagged `"builtin"` bypass this check.

#### 3. Runtime Evaluation

Any code path can call `engine.evaluate()` for ad-hoc permission checks:

```python
decision = engine.evaluate(
    permission="filesystem.write",
    plugin_id="ext.my-plugin",
    plugin_tags=["external"],
)
if not decision["allowed"]:
    raise PermissionDeniedError(
        plugin_id, "filesystem.write", decision["reason"]
    )
```

### Audit Trail

Every policy decision is recorded by the `AuditLogger` (`system/sdk/audit.py`).

#### Audit Entry Structure

```python
class AuditEntry(TypedDict):
    timestamp: str      # ISO 8601 UTC
    event: str          # "policy_decision", "service_access", "plugin_lifecycle", "plugin_action"
    plugin_id: str
    user_role: str
    permission: str
    allowed: bool
    detail: str
```

#### Querying the Audit Log

```python
from system.sdk.audit import AuditLogger

logger = AuditLogger()

# Query by plugin
entries = logger.query(plugin_id="ext.my-plugin", limit=50)

# Query denied actions only
denied = logger.query(allowed=False)

# Get activity summary for a plugin
activity = logger.get_plugin_activity("ext.my-plugin")
# Returns: {"policy_decision": 42, "service_access": 15}

# Get denied summary grouped by plugin
summary = logger.get_denied_summary()
# Returns: [{"plugin_id": "ext.bad-plugin", "denied_count": 5, "permissions": ["filesystem.write"]}]
```

#### Audit Logger Methods

| Method | Description |
|---|---|
| `log(event, ...)` | Record a generic audit entry |
| `log_policy_decision(...)` | Record a policy decision |
| `log_service_access(plugin_id, service_name, allowed)` | Record a service access attempt |
| `log_plugin_lifecycle(plugin_id, action, detail)` | Record plugin lifecycle events |
| `query(plugin_id, event, allowed, limit)` | Query audit log with filters |
| `get_plugin_activity(plugin_id)` | Activity summary for a plugin |
| `get_denied_summary()` | Denied actions grouped by plugin |
| `recent` | Property: last 50 entries |
| `total_entries` | Property: total entry count |
| `clear()` | Clear all entries |

The audit log is kept in memory with a cap of 5,000 entries. When the cap is reached, the oldest half is pruned.

---

## Best Practices

### API Key Management

1. **Never commit `settings.json` with real keys**. Use `settings.example.json` as a template with placeholder values.
2. **If a key was committed**, rotate it immediately at your provider's console (Groq, OpenAI, Anthropic, etc.).
3. **Use environment variables** in Docker deployments instead of putting keys in files.
4. **The `_security_note` field** in `settings.example.json` serves as a constant reminder.

### Key Rotation

- Regularly rotate API keys for all LLM providers
- Rotate the JWT secret by deleting `jwt_secret.key` (a new one is auto-generated on restart -- note this invalidates all active sessions)
- Rotate channel bot tokens if compromised

### CORS Hardening

For production deployments:

```python
# Restrict to specific origin instead of wildcard
Access-Control-Allow-Origin: https://your-frontend-domain.com
```

### Network Security

- Bind API ports to `127.0.0.1` (Docker default), never `0.0.0.0`
- Use a reverse proxy (nginx, Caddy) for HTTPS termination
- Keep the Chrome service internal (not published to host)

### Plugin Security

- Audit the `permissions` field in third-party plugin manifests before installing
- Use the `default_effect: "deny"` policy to block unpermitted actions
- Review the audit log regularly for suspicious denied access patterns
- Tag custom plugins as `"external"` to apply stricter policy rules

### Docker Security

- Always use `no-new-privileges:true`
- Set memory limits for sandbox containers
- Use read-only root filesystems where possible
- Keep base images updated (`python:3.12-slim`)

---

## Security Audit Script

Capability OS includes a comprehensive security audit script at `scripts/security_audit.py`.

### Running the Audit

```bash
cd /path/to/capability-os
python scripts/security_audit.py
```

### What It Checks

The audit runs 8 checks:

| Check | What it scans |
|---|---|
| **1. Dangerous code patterns** | Scans all `.py` files for `eval()`, `exec()`, `__import__()`, `os.system()` |
| **2. Exposed secrets** | Checks `settings.json`, `.env`, `docker-compose.yml` for API keys (OpenAI, Groq, Anthropic, GitHub) |
| **3. Security rules integrity** | Verifies `security_rules.json` has all three levels (free, confirm, protected) |
| **4. Authentication** | Checks `users.json` for users without password hashes, validates JWT secret length |
| **5. Path traversal protection** | Verifies `PathValidator` uses `resolve()` + `is_relative_to()` |
| **6. CORS configuration** | Detects wildcard CORS (`*`) in server files |
| **7. Execution sandbox** | Verifies `SandboxManager` is present with Docker support |
| **8. Dependencies** | Checks `requirements.txt` for pinned vs unpinned dependencies |

### Sample Output

```
============================================================
  SECURITY AUDIT REPORT -- Capability OS
============================================================

  [i] INFO (6)
      security_rules: Rules OK: 12 free, 8 confirm, 5 protected tools
      auth: 1 users, 1 owner(s)
      auth: JWT secret exists (128 chars)
      path_traversal: PathValidator uses resolve() + is_relative_to
      sandbox: SandboxManager present (L2 process + L3 docker)
      sandbox: Docker sandbox support available

  [~] MEDIUM (1)
      cors: Wildcard CORS (*) in api_server.py -- restrict in production

  VERDICT: ACCEPTABLE -- 1 medium issues (review recommended)
```

### Severity Levels

| Severity | Icon | Meaning |
|---|---|---|
| **HIGH** | `[!]` | Action required -- security vulnerability |
| **MEDIUM** | `[~]` | Review recommended -- potential risk |
| **LOW** | `[-]` | Minor concern |
| **INFO** | `[i]` | Informational -- no action needed |

### Automated Auditing

The Supervisor daemon includes a `SecurityAuditor` (`system/core/supervisor/security_auditor.py`) that runs periodic security checks and emits `supervisor_alert` events when issues are detected.
