---
name: release
description: Cut a new versioned release for the claude-code-usage-statusline project. Analyzes commits since the last git tag, automatically determines patch/minor/major bump from conventional commit semantics, confirms with the user, then dispatches the GitHub Actions release workflow which handles tagging, SHA256 computation, Homebrew formula update, and GitHub release creation. Use this skill whenever the user says /release, "cut a release", "ship it", "make a new release", "publish a new version", "tag and release", "bump the version", or wants to release changes from this project.
---

# Release

Dispatch a versioned GitHub release by analyzing commits and triggering the release workflow.

## Steps

### 1. Find the last tag and collect commits

```bash
git tag --sort=-version:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -1
```

If no tags exist, this is the **first release** — use all commits as the range:
```bash
git log --format="%s" HEAD --no-merges
```

If a tag exists (e.g. `v1.0.0`), collect commits since then:
```bash
git log v1.0.0..HEAD --format="%s" --no-merges
```

If there are no commits since the last tag, stop: "Nothing to release — no commits since `<last_tag>`."

### 2. Determine bump type

Scan commit subjects in priority order — first match wins:

| Priority | Pattern in subject | Bump |
|---|---|---|
| 1 | Contains `!:` anywhere, or body has `BREAKING CHANGE` | `major` |
| 2 | Starts with `feat:` or `feat(...):` | `minor` |
| 3 | Starts with `fix:`, `fix(...):`, or `perf:` | `patch` |
| 4 | None of the above | `patch` (fallback) |

Collect any commits that don't match conventional prefixes — show them as a warning before confirming.

### 3. Compute the new version

Parse the last tag as `MAJOR.MINOR.PATCH` (or `0.0.0` for first release), apply the bump:
- `major` → MAJOR+1, MINOR=0, PATCH=0
- `minor` → MINOR+1, PATCH=0
- `patch` → PATCH+1

### 4. Show summary and confirm

Display something like:

```
Commits since v1.0.0:
  - fix: correct utilization scale
  - feat: add Homebrew formula
  - feat: add post_install hook

Detected bump: minor  →  v1.0.0 → v1.1.0

The GitHub Action will:
  1. Create and push tag v1.1.0
  2. Compute SHA256 of the release tarball
  3. Update HomebrewFormula/claude-usage-statusline.rb
  4. Commit and push the formula update to main
  5. Create GitHub release v1.1.0 with auto-generated notes

Proceed? [Y/n]  (or type patch / minor / major to override)
```

If the user types `patch`, `minor`, or `major`, override the bump and recalculate before redisplaying. If `n`, abort.

### 5. Verify GitHub CLI is authenticated

```bash
gh auth status
```

If not authenticated, stop: "Run `gh auth login` first."

Check whether a release workflow is already running:
```bash
gh run list -R victorstein/claude-code-usage-statusline -w release.yml -L 1 --json status -q '.[0].status' 2>/dev/null
```

If the status is `in_progress` or `queued`, warn the user before dispatching another run.

### 6. Dispatch the workflow

```bash
gh workflow run release.yml \
  -R victorstein/claude-code-usage-statusline \
  -f bump=<bump_type>
```

### 7. Tail the run

Poll for the new run ID — check up to 5 times, 3 seconds apart, until a run appears:
```bash
gh run list -R victorstein/claude-code-usage-statusline -w release.yml -L 1 --json databaseId,url
```

Once found, watch it live:
```bash
gh run watch <run-id> -R victorstein/claude-code-usage-statusline --exit-status
```

On success, fetch and display the release URL:
```bash
gh release view <new_tag> -R victorstein/claude-code-usage-statusline --json url -q '.url'
```

On failure, print: "Workflow failed. See run at: <run_url>"

If the run ID can't be found after 5 attempts, fall back: "Check your runs at: https://github.com/victorstein/claude-code-usage-statusline/actions"
