# No Force Push / No History Rewrite Doctrine

**Doctrine ID:** `no-force-push`  
**Scope:** All collaborative/shared branches  
**Enforcement:** Local advisory + Remote GitHub rulesets

## Policy

### Explicitly Banned Operations

The following operations are **forbidden** on protected/shared branches:

| Operation | Rationale |
|-----------|-----------|
| `git push --force` | Overwrites shared history without warning |
| `git push -f` | Short form, same danger |
| `git push --force-with-lease` | Still rewrites history, may hide conflicts |
| `git push --force-if-includes` | Soft force-push variant, still dangerous |
| `git push --mirror` | Mirror pushes rewrite all refs |
| `git push --delete` | Deleting shared branches destroys collaboration |
| `+<refspec>` (e.g., `+main`, `+refs/heads/main`) | Force-prefixed refspecs are force pushes |
| `src:+dst` patterns | Force source-to-destination pushes |
| Branch deletion via `git push origin :<branch>` | Removes shared history |
| Rebasing shared/published commits | Rewrites already-pushed history |
| Amending already-pushed commits | Rewrites already-pushed history |
| Cherry-picking in a way that rewrites shared history | Dangerous on shared branches |

### Recovery from Bad Commits

When bad commits reach a protected branch:

1. **Preferred**: Create a revert commit with `git revert <bad-commit>`
2. **Alternative**: Create a forward-fix commit that corrects the issue
3. **Break-glass only**: Emergency procedure documented in `docs/doctrine/emergency-procedures.md`

### Local vs. Remote Enforcement

| Layer | Type | Description |
|-------|------|-------------|
| Local pre-push hook | **Advisory only** | `scripts/git_no_force_push_guard.py` - catches accidents before push |
| GitHub branch protection | **Authoritative** | Blocks force-push and deletion on `main` |
| GitHub rulesets | **Authoritative** | Additional ruleset enforcement |

### Protected Branches

The following branches are protected:

- `refs/heads/main`
- `refs/heads/master`
- `refs/heads/release/*`
- Any branch configured in `docs/policy/no-force-push-protected-refs.json`

### Anti-Overreach Clause

**This policy is NOT:**

- An anti-NIH (not invented here) rule
- A ban on local rebasing of private branches
- A restriction on cleaning up local history before first publication

**The ban starts when:**

- History is pushed to a shared/protected branch
- History is pushed to a shared collaboration branch
- The push target is the canonical `main` or equivalent

### Emergency Exceptions

Any emergency exception must be:

1. **Manual**: Human-initiated, not automated
2. **Documented**: Explicit justification in commit message or PR
3. **Time-bounded**: Protections restored within defined window
4. **Reviewed**: Post-incident review of the exception
5. **Followed by restoration**: Branch protection restored immediately after

## Enforcement

### Local Guard (Advisory)

```bash
# Install the pre-push guard
python scripts/install_git_no_force_push_hook.py

# The guard:
# - Parses pre-push stdin to detect dangerous ref updates
# - Checks command-line arguments for force flags
# - Fails CLOSED for protected refs when danger is identifiable
# - Blocks unverifiable protected-ref updates (until fast-forward validation is implemented)
```

### Remote Guard (Authoritative)

The GitHub rules verifier proves enforcement:

```bash
python scripts/verify_github_no_force_push_rules.py
```

This verifier checks:
- Branch protection rules on `main`
- Force pushes disabled
- Branch deletion disabled
- Rulesets applied correctly

## Verification

The offline policy verifier validates doctrine compliance:

```bash
python scripts/verify_no_force_push_policy.py --self-test  # Self-test
python scripts/verify_no_force_push_policy.py               # Full gate
```

## Related Documents

- `docs/policy/no-force-push-protected-refs.json` - Protected branch configuration
- `scripts/git_no_force_push_guard.py` - Local pre-push guard
- `scripts/install_git_no_force_push_hook.py` - Hook installer
- `scripts/verify_no_force_push_policy.py` - Offline policy verifier
- `scripts/verify_github_no_force_push_rules.py` - Remote GitHub rules verifier
