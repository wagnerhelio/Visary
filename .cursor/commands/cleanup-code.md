# Cleanup Code - Remove Unused Fields, Debugs, Logs

Perform complete code cleanup following all cleanup rules.

## Cleanup Checklist

### 1. Unused Fields
- Search all model fields for references
- Identify fields not used in views, serializers, forms, templates, queries
- Remove unused fields from models
- Generate migration: `python visary/manage.py makemigrations`

### 2. Debugs and Logs
- Search for: `print(`, `console.log(`, `logger.debug(`, `logger.info(`, `logger.warning(`
- Remove ALL automatic logs (especially in `__init__` or module level)
- NEVER implement logs - only manually inserted by operator
- Critical: Logs in `__init__` break PowerShell commands

### 3. Docstrings and Comments
- Remove all docstrings
- Remove all comments
- Code must be self-explanatory

### 4. Dead Code
- Remove unused imports
- Remove unused functions/classes
- Remove commented code

## Search Commands

```powershell
# Search for prints
Select-String -Path "**/*.py" -Pattern "print\("

# Search for logs
Select-String -Path "**/*.py" -Pattern "logger\.(debug|info|warning)"

# Search for console.log
Select-String -Path "**/*.js" -Pattern "console\.log\("
```

## Validation

After cleanup:
- `python visary/manage.py check` (must not generate log outputs)
- `python visary/manage.py makemigrations --dry-run`
- Execute tests to ensure nothing broke

## Implementation

Remove immediately when identified. Never create planning files.
