# Authentication System

k9b supports secure session-based authentication for protecting the UI and API endpoints.

## Current Implementation: Local Admin Session Auth

The current authentication system uses:

- **Server-side sessions** with opaque session IDs stored in memory
- **PBKDF2-HMAC-SHA256** password hashing with 600,000 iterations
- **HttpOnly session cookies** for secure cookie-based authentication
- **Single admin account** configured via environment variables

### Security Properties

| Requirement | Implementation |
|------------|----------------|
| Server-side sessions | In-memory SessionStore with 256-bit session IDs |
| Password hashing | PBKDF2-HMAC-SHA256, 600k iterations, random salt |
| Constant-time comparison | `hmac.compare_digest()` for all comparisons |
| Generic login errors | No disclosure of which field (user/pass) failed |
| HttpOnly cookies | Prevents XSS from accessing session token |
| SameSite=Lax | Prevents CSRF on navigation, allows external links |
| Secure flag | Configurable via `K9B_SECURE_COOKIE=true` |
| Session expiry | Max age (8h default) and idle timeout (30m default) |

## Environment Configuration

### Required for Production

```bash
# Enable authentication
export K9B_AUTH_ENABLED=true

# Admin credentials (password hash, not plaintext)
export K9B_ADMIN_PASSWORD_HASH='$pbkdf2-sha256$600000$...'

# Username (optional, defaults to 'admin')
export K9B_ADMIN_USERNAME=admin

# Enable Secure flag on cookies (for HTTPS deployments)
export K9B_SECURE_COOKIE=true
```

### Generating a Password Hash

Use the helper script to generate a password hash:

```bash
# Generate random password and hash
python scripts/generate_admin_hash.py

# Generate hash for a specific password
python scripts/generate_admin_hash.py --password "your-secure-password"

# Quiet mode (just the hash)
python scripts/generate_admin_hash.py --password "pass" --quiet
```

### Session Configuration

```bash
# Session cookie name (optional, defaults to 'k9b_session')
export K9B_SESSION_COOKIE_NAME=k9b_session

# Session max age in seconds (optional, defaults to 28800 = 8 hours)
export K9B_SESSION_MAX_AGE_SECONDS=28800

# Session idle timeout in seconds (optional, defaults to 1800 = 30 minutes)
export K9B_SESSION_IDLE_TIMEOUT_SECONDS=1800
```

### Development Mode

To disable authentication for local development:

```bash
export K9B_AUTH_ENABLED=false
```

**Warning**: This is insecure for production use. Only use in development.

## Future: Keycloak/OIDC Integration

The authentication system is designed with a clean seam for future enterprise authentication:

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Route Protection Layer                    │
│                  (auth_guard.require_auth())                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    AuthProvider Interface                    │
│   authenticate(), get_principal_for_session(), etc.          │
└─────────────────────────────────────────────────────────────┘
                              │
           ┌──────────────────┴──────────────────┐
           ▼                                     ▼
┌──────────────────────┐              ┌──────────────────────┐
│ LocalAdminAuthProvider│              │   Future: OIDC       │
│ (current)             │              │   Keycloak Provider  │
└──────────────────────┘              └──────────────────────┘
```

### Migration Path

1. **Session layer stays the same**: The session store and HttpOnly cookies can remain after OIDC integration

2. **Replace the provider**: Swap `LocalAdminAuthProvider` with `KeycloakAuthProvider` that:
   - Validates Keycloak/OIDC tokens
   - Extracts user info from token claims
   - Creates internal sessions after OIDC callback

3. **Alternative: Gateway auth**: Use reverse proxy with OIDC:
   - Proxy handles OIDC authentication
   - Sets auth headers (e.g., `X-Auth-User`)
   - k9b validates headers instead of sessions

4. **Route protection unchanged**: All protected routes use `AuthenticatedPrincipal`, not Keycloak-specific objects

### Planned Configuration

```yaml
# Future Keycloak configuration (not implemented yet)
k9b:
  auth:
    enabled: true
    provider: keycloak
    keycloak:
      issuer: https://keycloak.example.com/realms/k9b
      client_id: k9b-ui
      # Or use gateway auth headers
      # use_gateway_headers: true
```

## API Endpoints

### POST /api/auth/login

Login with username and password.

**Request:**
```json
{
  "username": "admin",
  "password": "your-password"
}
```

**Response (success):**
```json
{
  "authenticated": true,
  "user": {
    "principal_id": "admin",
    "display_name": "admin",
    "auth_method": "local"
  }
}
```

**Response (failure):**
```json
{
  "error": "Invalid credentials"
}
```

### POST /api/auth/logout

Logout and invalidate the session.

**Response:**
```json
{
  "authenticated": false
}
```

### GET /api/auth/me

Check current authentication state.

**Response (authenticated):**
```json
{
  "authenticated": true,
  "user": {
    "principal_id": "admin",
    "display_name": "admin",
    "auth_method": "local"
  }
}
```

**Response (not authenticated):**
```json
{
  "authenticated": false,
  "user": null
}
```

## Protected Routes

All routes except auth endpoints require authentication:

| Route | Auth Required |
|-------|---------------|
| `/api/auth/*` | No (these SET the session) |
| `/health`, `/ready` | No (health checks) |
| `/api/run/*` | Yes |
| `/api/fleet` | Yes |
| `/api/proposals` | Yes |
| `/api/notifications` | Yes |
| `/api/cluster-detail` | Yes |
| `/api/next-check-*` | Yes |
| `/api/runs` | Yes |
| `/api/incidents/*` | Yes |
| `/api/deterministic-next-check/*` | Yes |
| `/api/run-batch-*` | Yes |
| `/api/alertmanager-*` | Yes |
| `/api/runtime-status` | Yes |
| `/artifact` | Yes |
| Static assets | No (needed for login page) |

## Cookie Security

Session cookies have the following attributes:

```
Name=k9b_session
HttpOnly
Path=/
Max-Age=28800
SameSite=Lax
Secure (when K9B_SECURE_COOKIE=true)
```

| Attribute | Purpose |
|-----------|---------|
| HttpOnly | Prevents JavaScript access (XSS protection) |
| Secure | Only sent over HTTPS (when enabled) |
| SameSite=Lax | Allows navigation from external sites, CSRF protection |
| Max-Age | Session expiry (absolute lifetime) |
| Path=/ | Available for all paths |

## Troubleshooting

### "Authentication required" on all API calls

1. Check that `K9B_AUTH_ENABLED=true` is set
2. Verify `K9B_ADMIN_PASSWORD_HASH` is configured
3. Check browser cookies are enabled
4. Verify the session cookie is being set (check browser dev tools)

### "Session expired or invalid"

1. Session may have expired (check max age and idle timeout)
2. Server may have been restarted (in-memory sessions are lost)
3. Clear browser cookies and log in again

### Login succeeds but API calls fail

1. Check that cookies are being sent with API requests
2. Verify `credentials: "include"` is set in fetch calls
3. Check for cookie domain/path issues

### Can't login with correct password

1. Verify the password hash was generated correctly
2. Check that `K9B_ADMIN_PASSWORD_HASH` environment variable is set correctly
3. Ensure no extra whitespace or quotes in the hash value