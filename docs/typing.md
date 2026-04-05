# Typing guidance

Typed contracts make the diagnostics agent more maintainable and easier to reason about. Follow these conventions when adding or refactoring code:

1. **Public interfaces** (functions exposed by modules or part of the CLI surface) should always declare parameter and return types.
2. **Dataclasses and domain records** must have type annotations on every field so downstream reasoning layers know what to trust.
3. **Cross-module contracts** (structures passed between `collect`, `normalize`, `reason`, `recommend`, `compare`, etc.) should stick to typed classes, `TypedDict`, or explicit `Mapping`/`Sequence` annotations instead of untyped dictionaries.
4. **Prefer explicit return types** even when inference is possible; this makes the code easier to audit and is required by the type checker.
5. Where `Any` is unavoidable (e.g., when dealing with third-party responses), limit it to a single assignment or helper, document why it is needed, and keep the rest of the call site typed.

Tooling and verification:

- Run `.venv/bin/python -m mypy src tests` to validate that the codebase follows these typing conventions.
- Keep `docs/typing.md` and `mypy.ini` aligned; if a new contract cannot be typed cleanly, add a note to this document explaining why before relaxing the configuration.
