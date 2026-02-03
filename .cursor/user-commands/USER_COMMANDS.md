# User Commands - Personal Commands

These commands are **personal** and should be copied manually to your user commands directory.

## Installation

### Quick Setup (Recommended)

Copy all command files from `.cursor/user-commands/` to your user commands directory:

**Windows PowerShell:**
```powershell
# Create directory if it doesn't exist
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.cursor\commands"

# Copy all command files
Copy-Item -Path ".cursor\user-commands\*.md" -Destination "$env:USERPROFILE\.cursor\commands\"
```

**Linux/Mac:**
```bash
# Create directory if it doesn't exist
mkdir -p ~/.cursor/commands

# Copy all command files
cp .cursor/user-commands/*.md ~/.cursor/commands/
```

### Manual Setup

Copy each command file individually to one of these directories:
- **Windows**: `C:\Users\seu-usuario\.cursor\commands\`
- **Linux/Mac**: `~/.cursor/commands/`
- **Alternative**: `~/.claude/commands/`

After copying, restart Cursor. Commands will be available when you type `/` in the chat.

---

## Available User Commands

### 1. quick-fix.md
Quick fix for common issues - syntax errors, imports, typos.

### 2. explain-code.md
Explain code in detail - how it works, what it does, dependencies.

### 3. optimize-performance.md
Analyze and optimize code performance - queries, loops, algorithms.

### 4. generate-docs.md
Generate documentation for functions, classes, APIs (when explicitly requested).

### 5. refactor-code.md
Refactor code to improve structure, readability, maintainability.

### 6. debug-issue.md
Debug specific issue - analyze error, trace execution, identify root cause.

### 7. review-pr.md
Review pull request - analyze changes, check for issues, suggest improvements.

---

## Command Files

### quick-fix.md

```markdown
# Quick Fix

Fix the identified issue immediately. Focus on:
- Syntax errors
- Import errors
- Typos and naming issues
- Missing dependencies
- Quick logic corrections

Implement fix directly. No planning files. Validate after fix.
```

### explain-code.md

```markdown
# Explain Code

Explain the selected code in detail:

1. **What it does** - Purpose and functionality
2. **How it works** - Step-by-step execution flow
3. **Dependencies** - What it depends on (imports, models, services)
4. **Data flow** - Input/output, transformations
5. **Edge cases** - Potential issues or special cases
6. **Related code** - Where it's used, what calls it

Be thorough and technical. Use concrete examples from the codebase.
```

### optimize-performance.md

```markdown
# Optimize Performance

Analyze and optimize code performance:

1. **Database queries** - Check for N+1 problems, missing indexes, inefficient queries
2. **Loops and iterations** - Identify O(n²) or worse, suggest optimizations
3. **Algorithm efficiency** - Analyze time/space complexity
4. **Caching opportunities** - Identify data that can be cached
5. **Lazy loading** - Check if eager loading can be optimized
6. **Memory usage** - Identify memory leaks, large object retention

Before optimizing:
- ALWAYS consult Context7 (MCP) for framework-specific optimization patterns
- ALWAYS search internet for current best practices

Provide concrete evidence of performance issues with measurements when possible.
Implement optimizations directly. Validate performance improvements.
```

### generate-docs.md

```markdown
# Generate Documentation

Generate documentation ONLY when explicitly requested by user.

Documentation should include:
- Function/class purpose
- Parameters and return values
- Usage examples
- Edge cases and exceptions
- Related functions/classes

Format: Clean, technical, no fluff. Use code examples from actual codebase.
```

### refactor-code.md

```markdown
# Refactor Code

Refactor code to improve:
- Structure and organization
- Readability and maintainability
- Code duplication (DRY principle)
- Naming conventions
- Separation of concerns

Before refactoring:
- Read complete file(s) first
- Understand all dependencies
- Ensure tests exist or create them
- Validate after refactoring

Refactor incrementally. Maintain original functionality. Validate with tests.
```

### debug-issue.md

```markdown
# Debug Issue

Debug the specified issue:

1. **Analyze error** - Read error message, stack trace, logs
2. **Trace execution** - Follow code path that leads to error
3. **Identify root cause** - Find the actual problem, not just symptoms
4. **Check dependencies** - Verify imports, models, services are correct
5. **Validate data** - Check if data format/type is as expected
6. **Check edge cases** - Verify handling of null, empty, invalid inputs

Provide:
- **Root cause** with evidence
- **Fix** with explanation
- **Prevention** - How to avoid similar issues

Implement fix directly. Validate fix resolves issue completely.
```

### review-pr.md

```markdown
# Review Pull Request

Review pull request changes:

1. **Code quality** - Readability, structure, naming
2. **Logic correctness** - Verify logic is correct, handle edge cases
3. **Security** - Check for vulnerabilities, auth/authz, input validation
4. **Performance** - Check for N+1, inefficient queries, algorithms
5. **Tests** - Verify tests exist and cover changes
6. **Breaking changes** - Identify potential breaking changes
7. **Documentation** - Check if changes need documentation updates

For each issue found:
- **File and line numbers**
- **Code snippet**
- **Explanation and severity**
- **Suggestion for fix**

Be direct and constructive. Focus on actionable feedback.
```

---

## Usage

1. Copy desired command file(s) from `.cursor/user-commands/` to your user commands directory
2. Restart Cursor
3. Type `/` in chat to see available commands
4. Select command to insert its content into chat

## Template Location

All user command templates are located in:
- **Project**: `.cursor/user-commands/`
- **Copy to**: `~/.cursor/commands/` or `~/.claude/commands/`

## Notes

- User commands are **personal** and not version-controlled with the project
- Project commands in `.cursor/commands/` are version-controlled and shared with team
- User commands apply to **all projects** you work on
- Project commands apply only to **this specific project**

## How to Create User Commands via UI

### Step-by-Step Process

1. **Open Cursor Settings**
   - Press `Ctrl+,` or go to `File → Preferences → Settings`
   - Or press `Ctrl+Shift+P` and type "Preferences: Open Settings"

2. **Navigate to Commands**
   - Search for "Commands" in the settings search bar
   - Or go to `Features → Commands`

3. **Access User Commands Section**
   - Scroll to "User Commands" section (below "Project Commands")
   - If empty, it will show "No User Commands"

4. **Create New Command**
   - Click "+ Add Command" button (top right of User Commands section)
   - Or click the centered "Add Command" button

5. **Enter Command Name**
   - Dialog appears: "Enter Command Name"
   - **Format**: Use kebab-case (lowercase with hyphens)
   - **Examples**:
     - `quick-fix` ✅
     - `explain-code` ✅
     - `optimize-performance` ✅
     - `my-custom-command` ✅
   - **Avoid**:
     - `QuickFix` ❌ (camelCase)
     - `quick_fix` ❌ (snake_case)
     - `quick fix` ❌ (spaces)

6. **Confirm Name**
   - Press `Enter` to confirm
   - Press `Escape` to cancel

7. **Insert Command Content**
   - Editor opens automatically
   - File is saved in: `~/.cursor/commands/[nome].md`
   - **Windows**: `C:\Users\seu-usuario\.cursor\commands\[nome].md`
   - **Linux/Mac**: `~/.cursor/commands/[nome].md`
   - Insert Markdown content (see examples above)

8. **Save and Use**
   - Save file (`Ctrl+S`)
   - Restart Cursor (recommended)
   - Type `/` in chat to see your command

### Command Content Template

When creating a command, use this template:

```markdown
# Command Name

Brief description of what the command does.

## Instructions

1. First action the AI should take
2. Second action
3. Third action

## Checklist

- [ ] Item 1
- [ ] Item 2
- [ ] Item 3
```

### Alternative: Manual File Creation

If you prefer to create files manually:

1. **Create Directory** (if it doesn't exist):
   ```powershell
   # Windows
   New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.cursor\commands"
   
   # Linux/Mac
   mkdir -p ~/.cursor/commands
   ```

2. **Create `.md` File**:
   - Name: `meu-comando.md` (kebab-case)
   - Location: `~/.cursor/commands/meu-comando.md`

3. **Insert Markdown Content**:
   - Use examples from this file or create custom content

4. **Restart Cursor**:
   - Commands are loaded on startup
