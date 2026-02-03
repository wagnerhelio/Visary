# Analyze Django Model

Perform complete analysis of Django model(s) to identify issues and unused fields.

## Analysis Process

1. **Read complete model file** - From start to finish, no partial reading
2. **List all fields** - Document every field in the model
3. **Search field references** - Use grep/search to find all usages:
   - Views, serializers, forms, templates
   - ORM queries, filters, ordering
   - JavaScript/frontend access
   - Old migrations (historical use)
4. **Identify unused fields** - Fields not referenced anywhere
5. **Validate necessity** - Even audit fields must be validated
6. **Check relationships** - Verify ForeignKey/ManyToMany are correct and necessary

## Evidence Required

For each unused/unnecessary field:
- **Field name and model**
- **Search results** showing no references found
- **Justification** for removal

## Implementation

If field is unused/unnecessary:
1. Remove from model
2. Remove all references (if any found)
3. Generate migration: `python visary/manage.py makemigrations`
4. Validate: `python visary/manage.py check`

## New Field Validation

Before adding new fields, verify:
- Is field really necessary now?
- Is information not available via relationship?
- Am I not duplicating existing information?
- Will field be used immediately?
- Is relationship correct and necessary?
