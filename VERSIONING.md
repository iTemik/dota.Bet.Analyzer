# Independent Versioning System

The frontend and backend versions are now managed **independently** based on code changes. This allows each component to increment its version only when that component changes.

## Version Format

Both frontend and backend use **semantic versioning** in the format:
- **MAJOR.MINOR.BUILD** (e.g., `1.1.42`)
  - MAJOR: Manual update only (e.g., breaking changes)
  - MINOR: Auto-incremented by CI when code changes
  - BUILD: Injected from CI environment or set to "DEV" locally

## Version Storage

### Version Files (MAJOR.MINOR format)
- `backend/VERSION` - Contains backend's MAJOR.MINOR (e.g., `1.1`)

### Source Files (Full version)
- `backend/__init__.py` - Contains `__version__ = "1.1"` (MAJOR.MINOR only, BUILD added at runtime)
- `frontend/src/version.ts` - Contains `export const VERSION = '1.2.0'` (Full semantic version)

## Version Management Script

Use `scripts/version.js` to manage versions independently:

```bash
# Show all versions
node scripts/version.js

# Frontend version commands
node scripts/version.js frontend get                    # Get current version
node scripts/version.js frontend major 2               # Set major to 2 (resets minor to 0)
node scripts/version.js frontend build 42              # Set build to 42
node scripts/version.js frontend increment-minor       # Increment minor version

# Backend version commands
node scripts/version.js backend get                     # Get current version
node scripts/version.js backend major 2                # Set major to 2 (resets minor to 0)
node scripts/version.js backend build 42               # Set build to 42
node scripts/version.js backend increment-minor        # Increment minor version
```

## CI/CD Workflow

The `.github/workflows/version.yml` workflow:

1. **Downloads** the previous build number
2. **Increments** minor version based on changed files:
   - Only increment frontend if `frontend/` files changed
   - Only increment backend if `backend/` files changed
3. **Injects** build number from `github.run_number`
4. **Commits** version changes
5. **Creates** release tags

### Environment Variables

- `BUILD_NUMBER`: Automatically set to `${{ github.run_number }}` in CI
- Defaults to `"DEV"` in local development

## Tests

### Frontend Tests
Located in `frontend/src/version.test.ts`:
- Validates VERSION constant exists
- Checks semantic version format (X.Y.Z)
- Ensures major, minor, patch are present
- Allows DEV as build version

**Run:** `npm run test:frontend`

### Backend Tests
Located in `tests/test_version.py`:
- Validates `__version__` is a string
- Checks MAJOR.MINOR format
- Ensures version components are non-negative
- Verifies version is at least 1.0

**Run:** `npm run test:backend`

## Example: Independent Increments

**Scenario:** Only backend code changes

```bash
# Before
Frontend: 1.2.DEV
Backend:  1.2.DEV

# After CI runs
Frontend: 1.2.0 (unchanged)
Backend:  1.3.0 (auto-incremented)
```

**Scenario:** Only frontend code changes

```bash
# Before
Frontend: 1.1.DEV
Backend:  1.1.DEV

# After CI runs
Frontend: 1.2.0 (auto-incremented)
Backend:  1.1.0 (unchanged)
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
