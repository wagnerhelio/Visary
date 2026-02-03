# Create Complete Tests

Create or update complete tests for the specified functionality following all testing rules.

## Mandatory Test Coverage

### For Models
- Valid instance creation
- Required/optional field validation
- Data type, size, format validation
- Unique value validation
- Choices validation
- Representation (`__str__()`, `__repr__()`)
- Model methods and properties
- ForeignKey/relationship tests (cascade, protect, set null)
- ManyToMany and OneToOne relationships

### For Views
- GET without/with authentication
- GET with/without permission
- POST with valid/invalid data
- POST without authentication/permission
- PUT/PATCH with valid/invalid data
- DELETE with/without permission
- Correct status codes
- Template rendering and context
- Redirections
- Forms, pagination, filters, ordering

### For Session Control
- Login creates session correctly
- Logout destroys session correctly
- Expired/invalid session behavior
- Multiple sessions
- Session cookies configuration
- Session cleanup on logout

## Test Structure

Use `tests.py` in Django apps. Organize by classes:
- `TestYourModel`
- `TestYourViews`
- `TestYourServices`

## Process

1. Implement functionality first
2. Create/update tests immediately after
3. Execute tests to validate
4. Fix code or tests until 100% success
5. Never finish without complete and passing tests

## Execution

```powershell
& .\.venv\Scripts\Activate.ps1
python visary/manage.py test [app_name]
python visary/manage.py test --verbosity=2
```
