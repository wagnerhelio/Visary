# User Commands Templates

This directory contains **templates** for User Commands that should be copied to your personal commands directory.

## Location

- **Templates (this directory)**: `.cursor/user-commands/` (version-controlled in project)
- **Your Commands**: `~/.cursor/commands/` (personal, not version-controlled)

## Quick Setup

**Windows PowerShell:**
```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.cursor\commands"
Copy-Item -Path ".cursor\user-commands\*.md" -Destination "$env:USERPROFILE\.cursor\commands\" -Exclude "USER_COMMANDS.md","README.md"
```

**Linux/Mac:**
```bash
mkdir -p ~/.cursor/commands
cp .cursor/user-commands/*.md ~/.cursor/commands/ --exclude=USER_COMMANDS.md --exclude=README.md
```

After copying, restart Cursor. Commands will be available when you type `/` in the chat.

## Available Commands

This directory contains the following command templates:

1. **debug-issue.md** - Debug specific issue (analyze error, trace execution, identify root cause)
2. **explain-code.md** - Explain code in detail (how it works, what it does, dependencies)
3. **generate-docs.md** - Generate documentation for functions, classes, APIs (when explicitly requested)
4. **optimize-performance.md** - Analyze and optimize code performance (queries, loops, algorithms)
5. **quick-fix.md** - Quick fix for common issues (syntax errors, imports, typos)
6. **refactor-code.md** - Refactor code to improve structure, readability, maintainability
7. **review-pr.md** - Review pull request (analyze changes, check for issues, suggest improvements)

## Documentation

- **USER_COMMANDS.md** - Complete documentation with step-by-step instructions for creating commands via UI or manually
- **README.md** - This file (quick reference)

## How to Create New Commands

See **USER_COMMANDS.md** in this directory for complete instructions on creating commands via UI or manually.

## Notes

- These are **templates** - copy them to `~/.cursor/commands/` to use
- User commands are **personal** and apply to all projects
- Project commands are in `.cursor/commands/` and are project-specific
- Do not copy `USER_COMMANDS.md` or `README.md` to your personal commands directory
