# Code Review - Complete Analysis

Perform a complete code review following all project rules. Read the complete file(s) from start to finish before analyzing.

## Analysis Checklist

1. **Read complete file(s)** - Never analyze partially, read entire file(s) first
2. **Logical failures** - Identify logic errors, edge cases, incorrect flows
3. **ORM/SQL failures** - Validate queries, check for N+1, verify indexes
4. **Hardcodes** - Identify fixed values that should be dynamic/configurable
5. **Security vulnerabilities** - SQL injection, XSS, CSRF, auth/authz issues
6. **Unused/legacy fields** - Identify fields in models not referenced anywhere
7. **Debugs and logs** - Remove all print(), console.log(), logger.debug/info/warning
8. **Session/cookies issues** - Validate session management, cookie flags
9. **Code conventions** - Backend in English, frontend messages in Portuguese
10. **CRUD patterns** - Verify if code follows generic CRUD pattern, not hardcoded

## Evidence Required

For each flagged issue, provide:
- **File path and line numbers**
- **Code snippet** showing the problem
- **Explanation** of why it's a problem
- **Concrete evidence** - never use "probably" or "I think"

## Implementation

After identifying issues, implement corrections immediately in existing files. Never create planning files or documentation.

## Validation

After corrections, validate with:
- `python visary/manage.py check`
- `python visary/manage.py makemigrations --dry-run`
- Execute relevant tests
