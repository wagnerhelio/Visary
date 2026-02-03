# Validate Django Migrations

Validate and manage Django migrations following migration rules.

## Mandatory Rules

- **NEVER create migration files manually** - Always let Django generate them
- **Always correct/adjust code first** - Models, fields, relationships
- **Let Django create migrations automatically** - Use `python visary/manage.py makemigrations`

## Process

1. **Modify model** - Add/remove fields, change types, add/remove relationships
2. **Generate migration** - `python visary/manage.py makemigrations`
3. **Review migration** - Django will show what will be created
4. **Apply migration** - `python visary/manage.py migrate`

## When Modifying Models

- **Adding fields**: Adjust model, Django generates migration
- **Removing unused/legacy fields**: Remove from model, Django generates migration
- **Changing field types**: Adjust model, Django generates migration
- **Adding/removing relationships**: Adjust model, Django generates migration
- **Changing Meta options**: Adjust model, Django generates migration

## Validation Commands

```powershell
# Activate venv
& .\.venv\Scripts\Activate.ps1

# Check for pending migrations
python visary/manage.py showmigrations

# Generate migrations (dry-run to preview)
python visary/manage.py makemigrations --dry-run

# Generate migrations
python visary/manage.py makemigrations

# Apply migrations
python visary/manage.py migrate

# Validate system
python visary/manage.py check
```

## Prohibited

- Creating file `*/migrations/XXXX_name.py` manually
- Editing existing migration files (except rare specific cases)
- Copying migrations from other projects

## Environments

Consider 3 environments:
- **Local**: SQLite (development)
- **Kubernetes Postgres Homologation**: test/staging
- **Kubernetes Postgres Production**: production
