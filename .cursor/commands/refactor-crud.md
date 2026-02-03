# Refactor to Generic CRUD Pattern

Refactor code to follow generic CRUD pattern, removing hardcodes and making code dynamic and reusable.

## CRUD Principles

- **ALWAYS think in CRUD**: Create, Read, Update, Delete
- **Zero hardcode**: No fixed values, IDs, field names, or specific structures
- **Dynamic and expandable**: Easy to add new entities without modifying existing code
- **Configurable**: Allow customization via settings, models, or parameters

## Refactoring Checklist

1. **Identify hardcodes** - Fixed values, IDs, field names, entity-specific logic
2. **Extract to generic** - Create reusable base classes or generic functions
3. **Use configuration** - Dictionaries, settings, or parameters instead of conditionals
4. **Avoid complex conditionals** - Prefer polymorphism, base classes, or configuration
5. **Make expandable** - Code should work for any entity following same pattern

## Patterns to Apply

### Views/APIs
- Use generic views (Django Generic Views) or reusable base classes
- Parameters via URL/query string, not fixed values
- Generic serialization based on models

### Services
- Generic services that receive model/class as parameter
- Methods that work for any entity: `get_by_id(model, id)` not `get_user_by_id(id)`

### Models
- Configurable fields via Meta or settings when possible
- Generic relationships when applicable

## Before/After Example

**Bad (Hardcode, Specific):**
```python
def get_user_report(user_id):
    if user_id == 1:
        return "Admin Report"
    elif user_id == 2:
        return "Manager Report"
```

**Good (Dynamic, Generic):**
```python
def get_report_by_role(user):
    role_reports = {
        'admin': 'Admin Report',
        'manager': 'Manager Report'
    }
    return role_reports.get(user.role, 'Default Report')
```

## Implementation

Read complete file first, then refactor incrementally. Validate after each change.
