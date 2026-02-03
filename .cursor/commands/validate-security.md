# Validate Security

Perform complete security validation following OWASP guidelines and Django best practices.

## Pre-Validation Required

Before implementing security changes:
- ALWAYS consult Context7 (MCP) documentation for framework/library
- ALWAYS search internet for current OWASP guidance and deprecations

## Security Checklist

### Authentication and Authorization
- Auth/authz mandatory in sensitive views
- Validate and sanitize all inputs (GET/POST/data)
- Correct session control (cleanup on logout)
- Cookies with adequate flags (HttpOnly, Secure, SameSite)

### SQL Injection
- NEVER concatenate parameters in SQL
- Use Django ORM or parameterized queries
- Verify all raw SQL queries use parameters

### Data Exposure
- DON'T expose secrets/PII in logs, exceptions or responses
- Remove all debug prints/logs
- Sanitize logs that contain sensitive data
- Validate session expiration with adequate redirects

### Secret Protection
- NEVER place tokens, keys, passwords in code, commits, logs
- Use environment variables for secrets
- Validate .env is in .gitignore

### Session and Cache
- Correct session expiration
- Cache without user data leakage
- localStorage/sessionStorage only for non-sensitive data

## Evidence Required

For each security issue:
- **File path and line numbers**
- **Code snippet** showing vulnerability
- **OWASP category** and risk level
- **Concrete evidence** - never use "probably"

## Implementation

Implement security corrections immediately. Never create planning files.
