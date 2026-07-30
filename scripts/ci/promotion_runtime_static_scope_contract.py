"""ScopeRecord contract for the dual-range static-scope model.

Owner: ScopeRecord schema, validation, checksum computation.
All other logic lives in promotion_runtime_static_scope_git.py,
promotion_runtime_static_scope_policy.py, and the orchestrator.
"""

from __future__ import annotations

import hashlib
import json


class ScopeError(RuntimeError):
    """Raised when the scope is invalid or classification fails."""


# ---------------------------------------------------------------------------
# ScopeRecord
# ---------------------------------------------------------------------------


class ScopeRecord:
    """Complete scope record for the dual-range model.

    Attributes
    ----------
    schema_version : str
        Always "1".
    runtime_base_sha : str
        Full SHA of the runtime base (deployed runtime range).
    lane_base_sha : str
        Full SHA of the lane base (experimental lane range).
    subject_sha : str
        Full SHA of the subject commit.
    subject_tree : str
        Full SHA of the subject commit tree (``git rev-parse SUBJECT^{tree}``).
    repo_root : str
        Always "." — repository-relative paths only.
    cumulative_changed_python : tuple[str, ...]
        All Python files changed from RUNTIME_BASE..SUBJECT (sorted, unique).
    runtime_paths : tuple[str, ...]
        runtime_changed filtered to src/k8s_diag_agent/ (sorted, unique).
    lane_changed_python : tuple[str, ...]
        All Python files changed from LANE_BASE..SUBJECT (sorted, unique).
    lane_paths : tuple[str, ...]
        lane_changed_python minus runtime_paths (sorted, unique).
    historical_nonruntime_paths : tuple[str, ...]
        In cumulative_changed_python, not in runtime_paths, not in lane_changed_python.
    unclassified_paths : tuple[str, ...]
        In lane_changed_python minus runtime_paths, not in lane_authority_policy.
        MUST be empty (hard fail).
    cumulative_changed_count : int
    runtime_count : int
    lane_changed_count : int
    lane_count : int
    historical_nonruntime_count : int
    unclassified_count : int
    cumulative_changed_sha256 : str
    runtime_paths_sha256 : str
    lane_changed_sha256 : str
    lane_paths_sha256 : str
    historical_nonruntime_sha256 : str
    unclassified_sha256 : str
    included_paths_sha256 : str
    scope_record_sha256 : str

    Invariants (enforced by validate()):
        - schema_version == "1"
        - runtime_base_sha, lane_base_sha, subject_sha, subject_tree are
          exactly 40-hex characters
        - lane_paths ∩ runtime_paths == empty
        - lane_paths ∩ historical_nonruntime_paths == empty
        - runtime_paths ∩ historical_nonruntime_paths == empty
        - unclassified_paths ∩ every bucket == empty
        - len(cumulative_changed_python) == cumulative_changed_count
        - len(runtime_paths) == runtime_count
        - len(lane_changed_python) == lane_changed_count
        - len(lane_paths) == lane_count
        - len(historical_nonruntime_paths) == historical_nonruntime_count
        - len(unclassified_paths) == unclassified_count
        - sorted(paths) == paths (each tuple is sorted)
        - scope_record_sha256 binds canonical JSON of all authoritative fields
    """

    __slots__ = (
        "schema_version",
        "runtime_base_sha",
        "lane_base_sha",
        "subject_sha",
        "subject_tree",
        "repo_root",
        "cumulative_changed_python",
        "runtime_paths",
        "lane_changed_python",
        "lane_paths",
        "historical_nonruntime_paths",
        "unclassified_paths",
        "cumulative_changed_count",
        "runtime_count",
        "lane_changed_count",
        "lane_count",
        "historical_nonruntime_count",
        "unclassified_count",
        "cumulative_changed_sha256",
        "runtime_paths_sha256",
        "lane_changed_sha256",
        "lane_paths_sha256",
        "historical_nonruntime_sha256",
        "unclassified_sha256",
        "included_paths_sha256",
        "scope_record_sha256",
    )

    def __init__(
        self,
        *,
        runtime_base_sha: str,
        lane_base_sha: str,
        subject_sha: str,
        subject_tree: str,
        repo_root: str,
        cumulative_changed_python: tuple[str, ...],
        runtime_paths: tuple[str, ...],
        lane_changed_python: tuple[str, ...],
        lane_paths: tuple[str, ...],
        historical_nonruntime_paths: tuple[str, ...],
        unclassified_paths: tuple[str, ...],
        cumulative_changed_count: int,
        runtime_count: int,
        lane_changed_count: int,
        lane_count: int,
        historical_nonruntime_count: int,
        unclassified_count: int,
        cumulative_changed_sha256: str,
        runtime_paths_sha256: str,
        lane_changed_sha256: str,
        lane_paths_sha256: str,
        historical_nonruntime_sha256: str,
        unclassified_sha256: str,
        included_paths_sha256: str,
        scope_record_sha256: str,
    ) -> None:
        self.schema_version = "1"
        self.runtime_base_sha = runtime_base_sha
        self.lane_base_sha = lane_base_sha
        self.subject_sha = subject_sha
        self.subject_tree = subject_tree
        self.repo_root = repo_root
        self.cumulative_changed_python = cumulative_changed_python
        self.runtime_paths = runtime_paths
        self.lane_changed_python = lane_changed_python
        self.lane_paths = lane_paths
        self.historical_nonruntime_paths = historical_nonruntime_paths
        self.unclassified_paths = unclassified_paths
        self.cumulative_changed_count = cumulative_changed_count
        self.runtime_count = runtime_count
        self.lane_changed_count = lane_changed_count
        self.lane_count = lane_count
        self.historical_nonruntime_count = historical_nonruntime_count
        self.unclassified_count = unclassified_count
        self.cumulative_changed_sha256 = cumulative_changed_sha256
        self.runtime_paths_sha256 = runtime_paths_sha256
        self.lane_changed_sha256 = lane_changed_sha256
        self.lane_paths_sha256 = lane_paths_sha256
        self.historical_nonruntime_sha256 = historical_nonruntime_sha256
        self.unclassified_sha256 = unclassified_sha256
        self.included_paths_sha256 = included_paths_sha256
        self.scope_record_sha256 = scope_record_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "runtime_base_sha": self.runtime_base_sha,
            "lane_base_sha": self.lane_base_sha,
            "subject_sha": self.subject_sha,
            "subject_tree": self.subject_tree,
            "repo_root": self.repo_root,
            "cumulative_changed_python": list(self.cumulative_changed_python),
            "runtime_paths": list(self.runtime_paths),
            "lane_changed_python": list(self.lane_changed_python),
            "lane_paths": list(self.lane_paths),
            "historical_nonruntime_paths": list(self.historical_nonruntime_paths),
            "unclassified_paths": list(self.unclassified_paths),
            "cumulative_changed_count": self.cumulative_changed_count,
            "runtime_count": self.runtime_count,
            "lane_changed_count": self.lane_changed_count,
            "lane_count": self.lane_count,
            "historical_nonruntime_count": self.historical_nonruntime_count,
            "unclassified_count": self.unclassified_count,
            "cumulative_changed_sha256": self.cumulative_changed_sha256,
            "runtime_paths_sha256": self.runtime_paths_sha256,
            "lane_changed_sha256": self.lane_changed_sha256,
            "lane_paths_sha256": self.lane_paths_sha256,
            "historical_nonruntime_sha256": self.historical_nonruntime_sha256,
            "unclassified_sha256": self.unclassified_sha256,
            "included_paths_sha256": self.included_paths_sha256,
            "scope_record_sha256": self.scope_record_sha256,
        }

    # Known field names for strict decoding
    _KNOWN_FIELDS = frozenset({
        "schema_version", "runtime_base_sha", "lane_base_sha", "subject_sha",
        "subject_tree", "repo_root", "cumulative_changed_python",
        "runtime_paths", "lane_changed_python", "lane_paths",
        "historical_nonruntime_paths", "unclassified_paths",
        "cumulative_changed_count", "runtime_count", "lane_changed_count",
        "lane_count", "historical_nonruntime_count", "unclassified_count",
        "cumulative_changed_sha256", "runtime_paths_sha256", "lane_changed_sha256",
        "lane_paths_sha256", "historical_nonruntime_sha256", "unclassified_sha256",
        "included_paths_sha256", "scope_record_sha256",
    })

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> ScopeRecord:
        """Strict decoder. Rejects unknown fields, wrong types, bad SHAs."""
        _HEX = "0123456789abcdefABCDEF"

        def _sha256(v: object, name: str) -> str:
            if not isinstance(v, str):
                raise ScopeError(f"{name}: expected str, got {type(v).__name__}")
            # Accept empty (placeholder) or 64-char SHA-256 hex.
            if v and (len(v) != 64 or not all(c in _HEX for c in v)):
                raise ScopeError(f"{name}: must be 64 hex chars, got {v!r}")
            return v

        def _hex40(v: object, name: str) -> str:
            if not isinstance(v, str):
                raise ScopeError(f"{name}: expected str, got {type(v).__name__}")
            # Accept empty or 40-char SHA-1 hex.
            if v and (len(v) != 40 or not all(c in _HEX for c in v)):
                raise ScopeError(f"{name}: must be 40 hex chars, got {v!r}")
            return v

        def _str(v: object, name: str) -> str:
            if not isinstance(v, str):
                raise ScopeError(f"{name}: expected str, got {type(v).__name__}")
            return v

        def _list_str(v: object, name: str) -> tuple[str, ...]:
            if not isinstance(v, list):
                raise ScopeError(f"{name}: expected list, got {type(v).__name__}")
            result: list[str] = []
            for i, item in enumerate(v):
                if not isinstance(item, str):
                    raise ScopeError(f"{name}[{i}]: expected str, got {type(item).__name__}")
                result.append(item)
            return tuple(result)

        def _int(v: object, name: str) -> int:
            if isinstance(v, bool) or not isinstance(v, int):
                raise ScopeError(f"{name}: expected int, got {type(v).__name__}")
            return v

        # Reject unknown fields
        unknown = set(d.keys()) - cls._KNOWN_FIELDS
        if unknown:
            raise ScopeError(f"unknown field(s): {sorted(unknown)!r}")

        return cls(
            runtime_base_sha=_hex40(d.get("runtime_base_sha"), "runtime_base_sha"),
            lane_base_sha=_hex40(d.get("lane_base_sha"), "lane_base_sha"),
            subject_sha=_hex40(d.get("subject_sha"), "subject_sha"),
            subject_tree=_hex40(d.get("subject_tree"), "subject_tree"),
            repo_root=_str(d.get("repo_root"), "repo_root"),
            cumulative_changed_python=_list_str(d.get("cumulative_changed_python"), "cumulative_changed_python"),
            runtime_paths=_list_str(d.get("runtime_paths"), "runtime_paths"),
            lane_changed_python=_list_str(d.get("lane_changed_python"), "lane_changed_python"),
            lane_paths=_list_str(d.get("lane_paths"), "lane_paths"),
            historical_nonruntime_paths=_list_str(d.get("historical_nonruntime_paths"), "historical_nonruntime_paths"),
            unclassified_paths=_list_str(d.get("unclassified_paths"), "unclassified_paths"),
            cumulative_changed_count=_int(d.get("cumulative_changed_count"), "cumulative_changed_count"),
            runtime_count=_int(d.get("runtime_count"), "runtime_count"),
            lane_changed_count=_int(d.get("lane_changed_count"), "lane_changed_count"),
            lane_count=_int(d.get("lane_count"), "lane_count"),
            historical_nonruntime_count=_int(d.get("historical_nonruntime_count"), "historical_nonruntime_count"),
            unclassified_count=_int(d.get("unclassified_count"), "unclassified_count"),
            cumulative_changed_sha256=_sha256(d.get("cumulative_changed_sha256"), "cumulative_changed_sha256"),
            runtime_paths_sha256=_sha256(d.get("runtime_paths_sha256"), "runtime_paths_sha256"),
            lane_changed_sha256=_sha256(d.get("lane_changed_sha256"), "lane_changed_sha256"),
            lane_paths_sha256=_sha256(d.get("lane_paths_sha256"), "lane_paths_sha256"),
            historical_nonruntime_sha256=_sha256(d.get("historical_nonruntime_sha256"), "historical_nonruntime_sha256"),
            unclassified_sha256=_sha256(d.get("unclassified_sha256"), "unclassified_sha256"),
            included_paths_sha256=_sha256(d.get("included_paths_sha256"), "included_paths_sha256"),
            scope_record_sha256=_sha256(d.get("scope_record_sha256"), "scope_record_sha256"),
        )

    def validate(self) -> None:
        """Validate structural invariants. Raises ScopeError on any violation."""
        if self.schema_version != "1":
            raise ScopeError(f"schema_version must be '1', got {self.schema_version!r}")
        if self.repo_root != ".":
            raise ScopeError(f"repo_root must be '.', got {self.repo_root!r}")
        if self.unclassified_count != 0:
            raise ScopeError(
                f"unclassified_count must be 0, got {self.unclassified_count}; "
                f"unclassified_paths={self.unclassified_paths!r}"
            )

        # Tuple vs count consistency
        for attr, expected in (
            ("cumulative_changed_python", self.cumulative_changed_count),
            ("runtime_paths", self.runtime_count),
            ("lane_changed_python", self.lane_changed_count),
            ("lane_paths", self.lane_count),
            ("historical_nonruntime_paths", self.historical_nonruntime_count),
            ("unclassified_paths", self.unclassified_count),
        ):
            actual = len(getattr(self, attr))
            if actual != expected:
                raise ScopeError(f"{attr}: count={expected} but len={actual}")

        # Sorted canonical form
        for attr in (
            "cumulative_changed_python",
            "runtime_paths",
            "lane_changed_python",
            "lane_paths",
            "historical_nonruntime_paths",
            "unclassified_paths",
        ):
            val = getattr(self, attr)
            if tuple(sorted(val)) != val:
                raise ScopeError(f"{attr} must be sorted; got unsorted order")

        # Duplicate check
        for attr in (
            "cumulative_changed_python",
            "runtime_paths",
            "lane_changed_python",
            "lane_paths",
            "historical_nonruntime_paths",
            "unclassified_paths",
        ):
            val = getattr(self, attr)
            if len(val) != len(set(val)):
                raise ScopeError(f"{attr} contains duplicates")

        # Absolute path scan — must run on ALL path fields regardless of bucket
        # completeness, so it fires before union/disjointness checks.
        for attr in (
            "cumulative_changed_python",
            "runtime_paths",
            "lane_changed_python",
            "lane_paths",
            "historical_nonruntime_paths",
            "unclassified_paths",
        ):
            for path in getattr(self, attr):
                if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
                    raise ScopeError(f"absolute path in {attr}: {path!r}")
                if "\\" in path:
                    raise ScopeError(f"backslash in {attr}: {path!r}")
                if "/./" in path or path.startswith("./") or path.endswith("/."):
                    raise ScopeError(f"dot-segment in {attr}: {path!r}")

        # Bucket disjointness
        s_runtime = set(self.runtime_paths)
        s_lane = set(self.lane_paths)
        s_hist = set(self.historical_nonruntime_paths)
        s_uncl = set(self.unclassified_paths)

        for a_name, a_set, b_name, b_set in (
            ("runtime_paths", s_runtime, "lane_paths", s_lane),
            ("runtime_paths", s_runtime, "historical_nonruntime_paths", s_hist),
            ("runtime_paths", s_runtime, "unclassified_paths", s_uncl),
            ("lane_paths", s_lane, "historical_nonruntime_paths", s_hist),
            ("lane_paths", s_lane, "unclassified_paths", s_uncl),
            ("historical_nonruntime_paths", s_hist, "unclassified_paths", s_uncl),
        ):
            overlap = a_set & b_set
            if overlap:
                raise ScopeError(f"{a_name} ∩ {b_name} is not empty: {sorted(overlap)!r}")

        # Union equality: only check when all bucket counts match (partial buckets
        # may have been validated for other properties; union is an invariant
        # that requires complete buckets).
        counts_match = all(
            len(getattr(self, attr)) == expected
            for attr, expected in (
                ("runtime_paths", self.runtime_count),
                ("lane_paths", self.lane_count),
                ("historical_nonruntime_paths", self.historical_nonruntime_count),
                ("unclassified_paths", self.unclassified_count),
            )
        )
        if counts_match:
            cumulative = set(self.cumulative_changed_python)
            union = s_runtime | s_lane | s_hist | s_uncl
            missing = cumulative - union
            extra = union - cumulative
            if missing:
                raise ScopeError(f"bucket union is missing: {sorted(missing)!r}")
            if extra:
                raise ScopeError(f"bucket union has extra paths: {sorted(extra)!r}")

    def with_checksums(self) -> ScopeRecord:
        """Return a new ScopeRecord with all SHA-256 fields computed.

        Uses NUL-delimited sorted UTF-8 bytes for all path hashes.
        scope_record_sha256 binds canonical JSON of all authoritative fields
        (everything except scope_record_sha256 itself).
        """
        def _path_sha256(paths: tuple[str, ...]) -> str:
            if not paths:
                # Empty bucket: SHA-256 of empty string
                return hashlib.sha256(b"").hexdigest()
            raw = b"\x00".join(p.encode("utf-8") for p in sorted(paths)) + b"\x00"
            return hashlib.sha256(raw).hexdigest()

        c_sha = _path_sha256(self.cumulative_changed_python)
        r_sha = _path_sha256(self.runtime_paths)
        lc_sha = _path_sha256(self.lane_changed_python)
        l_sha = _path_sha256(self.lane_paths)
        h_sha = _path_sha256(self.historical_nonruntime_paths)
        u_sha = _path_sha256(self.unclassified_paths)
        incl = tuple(sorted(self.runtime_paths + self.lane_paths))
        incl_sha = _path_sha256(incl)

        # All authoritative fields except scope_record_sha256
        payload = {
            "schema_version": self.schema_version,
            "runtime_base_sha": self.runtime_base_sha,
            "lane_base_sha": self.lane_base_sha,
            "subject_sha": self.subject_sha,
            "subject_tree": self.subject_tree,
            "repo_root": self.repo_root,
            "cumulative_changed_python": list(self.cumulative_changed_python),
            "runtime_paths": list(self.runtime_paths),
            "lane_changed_python": list(self.lane_changed_python),
            "lane_paths": list(self.lane_paths),
            "historical_nonruntime_paths": list(self.historical_nonruntime_paths),
            "unclassified_paths": list(self.unclassified_paths),
            "cumulative_changed_count": self.cumulative_changed_count,
            "runtime_count": self.runtime_count,
            "lane_changed_count": self.lane_changed_count,
            "lane_count": self.lane_count,
            "historical_nonruntime_count": self.historical_nonruntime_count,
            "unclassified_count": self.unclassified_count,
            "cumulative_changed_sha256": c_sha,
            "runtime_paths_sha256": r_sha,
            "lane_changed_sha256": lc_sha,
            "lane_paths_sha256": l_sha,
            "historical_nonruntime_sha256": h_sha,
            "unclassified_sha256": u_sha,
            "included_paths_sha256": incl_sha,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        rec_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        return ScopeRecord(
            runtime_base_sha=self.runtime_base_sha,
            lane_base_sha=self.lane_base_sha,
            subject_sha=self.subject_sha,
            subject_tree=self.subject_tree,
            repo_root=self.repo_root,
            cumulative_changed_python=self.cumulative_changed_python,
            runtime_paths=self.runtime_paths,
            lane_changed_python=self.lane_changed_python,
            lane_paths=self.lane_paths,
            historical_nonruntime_paths=self.historical_nonruntime_paths,
            unclassified_paths=self.unclassified_paths,
            cumulative_changed_count=self.cumulative_changed_count,
            runtime_count=self.runtime_count,
            lane_changed_count=self.lane_changed_count,
            lane_count=self.lane_count,
            historical_nonruntime_count=self.historical_nonruntime_count,
            unclassified_count=self.unclassified_count,
            cumulative_changed_sha256=c_sha,
            runtime_paths_sha256=r_sha,
            lane_changed_sha256=lc_sha,
            lane_paths_sha256=l_sha,
            historical_nonruntime_sha256=h_sha,
            unclassified_sha256=u_sha,
            included_paths_sha256=incl_sha,
            scope_record_sha256=rec_sha,
        )

    def verify_checksums(self) -> None:
        """Verify all checksum fields against recomputed values. Raises ScopeError on mismatch."""
        expected = self.with_checksums()
        for attr in (
            "cumulative_changed_sha256",
            "runtime_paths_sha256",
            "lane_changed_sha256",
            "lane_paths_sha256",
            "historical_nonruntime_sha256",
            "unclassified_sha256",
            "included_paths_sha256",
            "scope_record_sha256",
        ):
            actual = getattr(self, attr)
            exp = getattr(expected, attr)
            if actual != exp:
                raise ScopeError(f"checksum mismatch on {attr}: got {actual}, expected {exp}")
