# Independent Versioning System

The frontend and backend versions are managed **independently** based on git changes. Each component increments its version only when that component has changes.

## Version Format

- **Component versions**: `MAJOR.MINOR` (stored in VERSION files, e.g., `0.7`)
- **Release version**: `{FRONTEND_VERSION}-{BACKEND_VERSION}-{BUILD_NUMBER}` (e.g., `0.3-0.7-42`)

Version components:
- **MAJOR**: Manual update only (breaking changes)
- **MINOR**: Auto-incremented by CI when git changes detected
- **BUILD**: CI build number (GitHub run number)

## Version Storage

### Source Files (version sources)
- `backend/__init__.py` - Reads backend version from `backend/VERSION` at import time
- `frontend/src/version.ts` - Exports the frontend version and is used by `scripts/version.js` as the source of truth

## Version Management Script

Use `scripts/version.js` to manage versions:

```bash
# Show all versions
node scripts/version.js
# Output:
#   Frontend version: 0.3
#   Backend version: 0.7
#   Release version: 0.3-0.7-42

# Get release version (for CI tags)
node scripts/version.js release get                    # 0.3-0.7-42

# Auto-increment based on git changes
node scripts/version.js auto increment                 # Increments only changed components

# Check for changes
node scripts/version.js frontend check-changes         # Output: changed|unchanged
node scripts/version.js backend check-changes          # Output: changed|unchanged

# Manual version commands
node scripts/version.js frontend get                   # Get frontend version
node scripts/version.js frontend increment-minor       # Increment frontend minor
node scripts/version.js frontend major 1               # Set frontend major to 1.0

node scripts/version.js backend get                    # Get backend version
node scripts/version.js backend increment-minor        # Increment backend minor
node scripts/version.js backend major 1                # Set backend major to 1.0
```

## CI/CD Workflow

The `.github/workflows/version.yml` workflow:

1. **Detects changes** between current branch and main in `frontend/` and `backend/` directories
2. **Increments** minor version only for components with changes compared to main:
   - Only increment frontend if `frontend/` has changes vs main
   - Only increment backend if `backend/` has changes vs main
3. **Commits** VERSION files and source files to git
4. **Creates** release tag with format: `v{FRONTEND_VERSION}-{BACKEND_VERSION}-{BUILD_NUMBER}`

### Environment Variables

- `BUILD_NUMBER`: Automatically set to `${{ github.run_number }}` in CI
- Defaults to `"DEV"` in local development

## Release Tag Format

Release tags combine all version information:
- Format: `v{FRONTEND_VERSION}-{BACKEND_VERSION}-{BUILD_NUMBER}`
- Example: `v0.3-0.7-42`
  - Frontend version: 0.3
  - Backend version: 0.7
  - Build number: 42

## Tests

### Frontend Tests
Located in `frontend/src/version.test.ts`:
- Validates VERSION constant exists
- Checks version format (X.Y)
- Ensures major and minor are present

**Run:** `npm test` (includes frontend tests)

### Backend Tests
Located in `tests/test_version.py`:
- Validates `__version__` is a string
- Checks MAJOR.MINOR format (e.g., `0.7`)
- Ensures version components are non-negative
- Verifies version is at least 0.2

**Run:** `python -m pytest tests/test_version.py`

## Example: Selective Version Increments

**Scenario 1: Only backend code changes**

```bash
# Before
Frontend: 0.3
Backend: 0.7
Release: v0.3-0.7-41

# Push backend changes
# CI detects only backend/ changed

# After
Frontend: 0.3 (unchanged)
Backend: 0.8 (incremented)
Release: v0.3-0.8-42
```

**Scenario 2: Both components change**

```bash
# Before
Frontend: 0.3
Backend: 0.8
Release: v0.3-0.8-42

# Push frontend + backend changes
# CI detects both changed

# After
Frontend: 0.4 (incremented)
Backend: 0.9 (incremented)
Release: v0.4-0.9-43
```

## Manual Version Updates

Use the version script to manually update major versions:

```bash
# Update only backend major version
node scripts/version.js backend major 2
# Result: backend/__init__.py shows __version__ = "2.0"
#         backend/VERSION shows 2.0

# Update only frontend major version
node scripts/version.js frontend major 2
# Result: frontend/src/version.ts exports VERSION = '2.0.0'
```

## Integration with Build Number

The build number from CI is injected at runtime:

```typescript
// Frontend
export const VERSION = '1.1.42'  // 42 is the BUILD_NUMBER from CI
```

```python
# Backend
__version__ = '1.1'  # MAJOR.MINOR only
# At runtime, with BUILD_NUMBER=42: returns 1.1.42
```

The `/version` API endpoint returns both versions:
```json
{
  "frontend": "1.1.42",
  "backend": "1.1.42",
  "build": "42"
}
```
