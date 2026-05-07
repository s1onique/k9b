"""Tests for deanonymization module."""

from __future__ import annotations

import pytest

from k8s_diag_agent.security.deanonymization import (
    ALIAS_PATTERN,
    assert_no_provider_aliases,
    deanonymize_command,
    deanonymize_next_check_candidate,
    deanonymize_payload,
    deanonymize_review_enrichment,
    deanonymize_text,
)


class TestDeanonymizeText:
    """Tests for deanonymize_text function."""

    def test_simple_alias_replacement(self) -> None:
        """Test basic alias to label replacement in prose."""
        mapping = {"cluster-a": "cluster1", "cluster-b": "cluster2"}
        result = deanonymize_text("High latency in cluster-a", mapping)
        assert result == "High latency in cluster1"

    def test_multiple_aliases(self) -> None:
        """Test replacing multiple aliases in one string."""
        mapping = {"cluster-a": "cluster1", "cluster-b": "cluster2"}
        result = deanonymize_text(
            "cluster-a shows failures, cluster-b shows latency", mapping
        )
        assert result == "cluster1 shows failures, cluster2 shows latency"

    def test_no_partial_replacement(self) -> None:
        """Test that partial word matches are NOT replaced."""
        mapping = {"cluster-a": "cluster1"}
        # "cluster-audit" should NOT become "cluster1udit"
        result = deanonymize_text("cluster-audit results", mapping)
        assert result == "cluster-audit results"

    def test_unknown_alias_unchanged(self) -> None:
        """Test that unknown aliases remain unchanged."""
        mapping = {"cluster-a": "cluster1"}
        result = deanonymize_text("cluster-b shows issues", mapping)
        assert result == "cluster-b shows issues"

    def test_empty_text(self) -> None:
        """Test empty text returns empty."""
        mapping = {"cluster-a": "cluster1"}
        result = deanonymize_text("", mapping)
        assert result == ""

    def test_empty_mapping(self) -> None:
        """Test empty mapping returns original text."""
        result = deanonymize_text("cluster-a shows issues", {})
        assert result == "cluster-a shows issues"

    def test_none_text(self) -> None:
        """Test None text returns None."""
        mapping = {"cluster-a": "cluster1"}
        result = deanonymize_text(None, mapping)
        assert result is None

    def test_word_boundaries_with_punctuation(self) -> None:
        """Test aliases with punctuation boundaries."""
        mapping = {"cluster-a": "prod"}
        # Should match even with trailing punctuation
        result = deanonymize_text("cluster-a, cluster-b, and cluster-c", mapping)
        assert result == "prod, cluster-b, and cluster-c"

    def test_longer_alias_formats(self) -> None:
        """Test various alias formats."""
        mapping = {
            "cluster-aa": "prod-cluster",
            "namespace-b": "monitoring",
        }
        result = deanonymize_text(
            "Issues in cluster-aa namespace namespace-b", mapping
        )
        assert result == "Issues in prod-cluster namespace monitoring"


class TestDeanonymizeCommand:
    """Tests for deanonymize_command function."""

    def test_kubectl_context_replacement(self) -> None:
        """Test replacing cluster alias in kubectl --context."""
        mapping = {"cluster-a": "prod-cluster"}
        result = deanonymize_command(
            "kubectl get pods --context cluster-a", mapping
        )
        assert result == "kubectl get pods --context prod-cluster"

    def test_multiple_contexts_in_command(self) -> None:
        """Test replacing multiple cluster aliases in command."""
        mapping = {"cluster-a": "prod", "cluster-b": "stage"}
        result = deanonymize_command(
            "kubectl get pods --context cluster-a -n default --context cluster-b",
            mapping,
        )
        assert result == "kubectl get pods --context prod -n default --context stage"

    def test_command_without_alias(self) -> None:
        """Test command without matching aliases."""
        mapping = {"cluster-a": "prod"}
        result = deanonymize_command(
            "kubectl get pods --context other-cluster", mapping
        )
        assert result == "kubectl get pods --context other-cluster"

    def test_empty_command(self) -> None:
        """Test empty command returns empty."""
        mapping = {"cluster-a": "prod"}
        result = deanonymize_command("", mapping)
        assert result == ""

    def test_command_preview_example(self) -> None:
        """Test realistic command preview format."""
        mapping = {"cluster-a": "prod-cluster", "cluster-b": "stage-cluster"}
        result = deanonymize_command(
            "kubectl logs deployment/control-plane --context cluster-b -n kube-system",
            mapping,
        )
        assert result == (
            "kubectl logs deployment/control-plane --context stage-cluster -n kube-system"
        )


class TestDeanonymizePayload:
    """Tests for deanonymize_payload function."""

    def test_simple_payload(self) -> None:
        """Test basic payload de-anonymization."""
        mapping = {"cluster-a": "cluster1", "cluster-b": "cluster2"}
        payload = {
            "triageOrder": ["cluster-a", "cluster-b"],
            "topConcerns": ["High latency in cluster-a"],
        }
        result = deanonymize_payload(payload, mapping)
        assert result["triageOrder"] == ["cluster1", "cluster2"]
        assert result["topConcerns"] == ["High latency in cluster1"]

    def test_nested_payload(self) -> None:
        """Test nested structure de-anonymization."""
        mapping = {"cluster-a": "prod"}
        payload = {
            "clusters": [
                {"label": "cluster-a", "status": "healthy"},
                {"label": "cluster-b", "status": "degraded"},
            ]
        }
        result = deanonymize_payload(payload, mapping)
        assert result["clusters"][0]["label"] == "prod"
        assert result["clusters"][1]["label"] == "cluster-b"  # unchanged

    def test_payload_preserves_structure(self) -> None:
        """Test that payload structure is preserved."""
        mapping = {"cluster-a": "prod"}
        payload = {
            "count": 5,
            "enabled": True,
            "ratio": 0.75,
            "metadata": None,
            "description": "cluster-a is primary",
        }
        result = deanonymize_payload(payload, mapping)
        # Non-string values should be unchanged
        assert result["count"] == 5
        assert result["enabled"] is True
        assert result["ratio"] == 0.75
        assert result["metadata"] is None
        # String values should be de-anonymized
        assert result["description"] == "prod is primary"

    def test_list_payload(self) -> None:
        """Test list payload de-anonymization."""
        mapping = {"cluster-a": "prod"}
        payload = ["cluster-a", "cluster-b", "other"]
        result = deanonymize_payload(payload, mapping)
        assert result == ["prod", "cluster-b", "other"]

    def test_tuple_payload(self) -> None:
        """Test tuple payload de-anonymization."""
        mapping = {"cluster-a": "prod"}
        payload = ("cluster-a", "cluster-b")
        result = deanonymize_payload(payload, mapping)
        # Tuples are converted to lists during de-anonymization
        assert result == ["prod", "cluster-b"]

    def test_none_payload(self) -> None:
        """Test None payload returns None."""
        result = deanonymize_payload(None, {"cluster-a": "prod"})
        assert result is None


class TestDeanonymizeReviewEnrichment:
    """Tests for deanonymize_review_enrichment function."""

    def test_review_enrichment_payload(self) -> None:
        """Test standard review enrichment payload shape."""
        mapping = {"cluster-a": "prod-cluster", "cluster-b": "stage-cluster"}
        enrichment = {
            "summary": "Multi-cluster issues detected",
            "triageOrder": ["cluster-a", "cluster-b"],
            "topConcerns": [
                "High API latency in cluster-a",
                "Pod restarts in cluster-b kube-system",
            ],
            "nextChecks": [
                "kubectl get pods --context cluster-a",
                "kubectl describe node --context cluster-b",
            ],
            "focusNotes": [
                "Prioritize cluster-a due to active alerts",
                "Investigate cluster-b storage",
            ],
        }
        result = deanonymize_review_enrichment(enrichment, mapping)

        assert result["summary"] == "Multi-cluster issues detected"
        assert result["triageOrder"] == ["prod-cluster", "stage-cluster"]
        assert result["topConcerns"] == [
            "High API latency in prod-cluster",
            "Pod restarts in stage-cluster kube-system",
        ]
        assert result["nextChecks"] == [
            "kubectl get pods --context prod-cluster",
            "kubectl describe node --context stage-cluster",
        ]
        assert result["focusNotes"] == [
            "Prioritize prod-cluster due to active alerts",
            "Investigate stage-cluster storage",
        ]

    def test_empty_enrichment(self) -> None:
        """Test empty enrichment returns empty."""
        result = deanonymize_review_enrichment({}, {"cluster-a": "prod"})
        assert result == {}

    def test_enrichment_with_evidence_gaps(self) -> None:
        """Test enrichment with evidence gaps."""
        mapping = {"cluster-a": "prod"}
        enrichment = {
            "evidenceGaps": [
                "Missing metrics for cluster-a",
                "No logs from cluster-a monitoring namespace",
            ]
        }
        result = deanonymize_review_enrichment(enrichment, mapping)
        assert result["evidenceGaps"] == [
            "Missing metrics for prod",
            "No logs from prod monitoring namespace",
        ]


class TestDeanonymizeNextCheckCandidate:
    """Tests for deanonymize_next_check_candidate function."""

    def test_candidate_with_all_fields(self) -> None:
        """Test candidate with description, targetCluster, and commandPreview."""
        mapping = {"cluster-a": "prod-cluster", "cluster-b": "stage-cluster"}
        candidate = {
            "description": "Check pods in cluster-a",
            "targetCluster": "cluster-a",
            "targetContext": "cluster-a",
            "commandPreview": "kubectl get pods --context cluster-a -n kube-system",
            "priorityLabel": "high",
        }
        result = deanonymize_next_check_candidate(candidate, mapping)

        assert result["description"] == "Check pods in prod-cluster"
        assert result["targetCluster"] == "prod-cluster"
        assert result["targetContext"] == "prod-cluster"
        assert result["commandPreview"] == (
            "kubectl get pods --context prod-cluster -n kube-system"
        )
        # Non-de-anonymized fields unchanged
        assert result["priorityLabel"] == "high"

    def test_candidate_partial_fields(self) -> None:
        """Test candidate with only some fields."""
        mapping = {"cluster-a": "prod"}
        candidate = {
            "description": "Check cluster-a",
            "priorityLabel": "medium",
        }
        result = deanonymize_next_check_candidate(candidate, mapping)

        assert result["description"] == "Check prod"
        assert result["priorityLabel"] == "medium"

    def test_candidate_non_dict_input(self) -> None:
        """Test that non-dict input returns unchanged."""
        result = deanonymize_next_check_candidate("not a dict", {"cluster-a": "prod"})
        assert result == "not a dict"

    def test_candidate_with_multiple_contexts(self) -> None:
        """Test candidate with multiple cluster references."""
        mapping = {"cluster-a": "prod", "cluster-b": "stage"}
        candidate = {
            "description": "Compare cluster-a vs cluster-b latency",
            "commandPreview": "kubectl top nodes --context cluster-a && kubectl top nodes --context cluster-b",
        }
        result = deanonymize_next_check_candidate(candidate, mapping)

        assert result["description"] == "Compare prod vs stage latency"
        assert result["commandPreview"] == (
            "kubectl top nodes --context prod && kubectl top nodes --context stage"
        )


class TestDeanonymizationEdgeCases:
    """Edge case tests for de-anonymization functions."""

    def test_special_characters_in_alias(self) -> None:
        """Test aliases with special regex characters."""
        # Aliases like "cluster.prod" or "cluster@email" have regex special chars
        mapping = {"cluster.prod": "prod-cluster", "cluster@email": "email-cluster"}
        result = deanonymize_text(
            "Issues with cluster.prod and cluster@email", mapping
        )
        assert result == "Issues with prod-cluster and email-cluster"

    def test_alias_with_dashes(self) -> None:
        """Test aliases containing dashes."""
        mapping = {"my-cluster": "prod-us-east"}
        result = deanonymize_text("Deploying to my-cluster", mapping)
        assert result == "Deploying to prod-us-east"

    def test_alias_with_numbers(self) -> None:
        """Test aliases containing numbers."""
        mapping = {"cluster1": "prod-primary"}
        result = deanonymize_text("Issues on cluster1", mapping)
        assert result == "Issues on prod-primary"

    def test_overlapping_aliases(self) -> None:
        """Test handling of overlapping aliases (prefix collision).

        When multiple aliases could match (e.g., "cluster" and "cluster-a"),
        the implementation processes them in dict iteration order.
        The key property is that partial words are NOT replaced.
        """
        # Test that "cluster-a" is not matched inside a larger word like "my-cluster-a"
        mapping = {"cluster-a": "prod"}
        result = deanonymize_text("Issues on my-cluster-a node", mapping)
        # "cluster-a" should NOT match inside "my-cluster-a" (different prefix)
        assert result == "Issues on my-cluster-a node"

    def test_non_overlapping_aliases_ordered(self) -> None:
        """Test non-overlapping aliases are all replaced correctly."""
        mapping = {"cluster-x": "prod", "cluster-y": "stage"}
        result = deanonymize_text("cluster-x and cluster-y are affected", mapping)
        assert result == "prod and stage are affected"

    def test_preserves_numeric_and_boolean_values(self) -> None:
        """Test that numeric and boolean values are preserved in payloads."""
        mapping = {"cluster-a": "prod"}
        payload = {
            "count": 42,
            "ratio": 0.5,
            "enabled": True,
            "disabled": False,
            "nullField": None,
            "description": "cluster-a issues",
        }
        result = deanonymize_payload(payload, mapping)

        assert result["count"] == 42
        assert result["ratio"] == 0.5
        assert result["enabled"] is True
        assert result["disabled"] is False
        assert result["nullField"] is None
        assert result["description"] == "prod issues"


class TestFlattenAliasMappings:
    """Tests for flatten_alias_mappings() helper."""

    def test_cluster_and_namespace_mappings(self) -> None:
        """Test flattening cluster and namespace mappings together."""
        from k8s_diag_agent.security.deanonymization import flatten_alias_mappings
        all_mappings = {
            "cluster": {"cluster-a": "prod-cluster", "cluster-b": "stage-cluster"},
            "namespace": {"namespace-c": "production", "namespace-d": "staging"},
        }
        result = flatten_alias_mappings(all_mappings)
        expected = {
            "cluster-a": "prod-cluster",
            "cluster-b": "stage-cluster",
            "namespace-c": "production",
            "namespace-d": "staging",
        }
        assert result == expected

    def test_empty_mapping_returns_empty_dict(self) -> None:
        """Test that empty mapping returns empty dict."""
        from k8s_diag_agent.security.deanonymization import flatten_alias_mappings
        result = flatten_alias_mappings({})
        assert result == {}

    def test_non_string_values_are_filtered(self) -> None:
        """Test that non-string values are filtered out."""
        from k8s_diag_agent.security.deanonymization import flatten_alias_mappings
        all_mappings = {
            "cluster": {
                "cluster-a": "prod-cluster",  # string - included
                "cluster-b": 123,  # int - filtered
                "cluster-c": {"nested": "dict"},  # dict - filtered
                "cluster-d": ["list"],  # list - filtered
                "cluster-e": None,  # None - filtered
            },
        }
        result = flatten_alias_mappings(all_mappings)
        expected = {"cluster-a": "prod-cluster"}
        assert result == expected

    def test_non_mapping_category_values_are_skipped(self) -> None:
        """Test that non-Mapping category values are skipped."""
        from k8s_diag_agent.security.deanonymization import flatten_alias_mappings
        all_mappings = {
            "cluster": {"cluster-a": "prod"},  # valid
            "invalid": "not-a-mapping",  # skipped
            "also_invalid": 42,  # skipped
        }
        result = flatten_alias_mappings(all_mappings)
        expected = {"cluster-a": "prod"}
        assert result == expected


class TestWordBoundaryRegex:
    """Tests for word boundary regex pattern that verify fixed-width lookbehind."""

    def test_punctuation_separated_aliases(self) -> None:
        """Test that punctuation-separated aliases are replaced (the critical fix).

        This is the specific case that would fail with variable-width lookbehind:
        "cluster-a, cluster-b" with mapping {"cluster-a": "prod"} should give "prod, cluster-b"

        With variable-width lookbehind (?<=^|(?<=[^a-zA-Z0-9-])), Python's re module
        would raise an error or behave unexpectedly. With fixed-width lookbehind,
        this works correctly.
        """
        from k8s_diag_agent.security.deanonymization import deanonymize_text
        mapping = {"cluster-a": "prod"}
        result = deanonymize_text("cluster-a, cluster-b", mapping)
        assert result == "prod, cluster-b"

    def test_semicolon_separated_aliases(self) -> None:
        """Test semicolon-separated aliases are replaced."""
        from k8s_diag_agent.security.deanonymization import deanonymize_text
        mapping = {"cluster-a": "prod", "cluster-b": "stage"}
        result = deanonymize_text("cluster-a; cluster-b", mapping)
        assert result == "prod; stage"

    def test_parenthesis_enclosed_alias(self) -> None:
        """Test alias inside parentheses is replaced."""
        from k8s_diag_agent.security.deanonymization import deanonymize_text
        mapping = {"cluster-a": "prod"}
        result = deanonymize_text("(cluster-a)", mapping)
        assert result == "(prod)"

    def test_alias_inside_compound_word_not_replaced(self) -> None:
        """Test that alias inside compound word is NOT replaced.

        This is the key property: "cluster-audit" should not become "prod-udit"
        because "cluster-a" is a substring of "cluster-audit", not a whole token.
        """
        from k8s_diag_agent.security.deanonymization import deanonymize_text
        mapping = {"cluster-a": "prod"}
        result = deanonymize_text("See cluster-audit logs", mapping)
        # "cluster-audit" should NOT be modified because "cluster-a" is not
        # a whole token in "cluster-audit"
        assert result == "See cluster-audit logs"

    def test_alias_at_start_of_string(self) -> None:
        """Test alias at start of string is replaced."""
        from k8s_diag_agent.security.deanonymization import deanonymize_text
        mapping = {"cluster-a": "prod"}
        result = deanonymize_text("cluster-a is affected", mapping)
        assert result == "prod is affected"

    def test_alias_at_end_of_string(self) -> None:
        """Test alias at end of string is replaced."""
        from k8s_diag_agent.security.deanonymization import deanonymize_text
        mapping = {"cluster-a": "prod"}
        result = deanonymize_text("Issues in cluster-a", mapping)
        assert result == "Issues in prod"


class TestCapitalizedAliasReplacement:
    """Tests for case-insensitive alias replacement.

    LLM output often capitalizes the first letter of aliases in sentences:
    - "Cluster-a shows issues" instead of "cluster-a shows issues"
    - "Namespace-b in default" instead of "namespace-b in default"

    The de-anonymization must handle these capitalized variants.
    """

    def test_capitalized_cluster_alias_replaced(self) -> None:
        """Test that capitalized 'Cluster-a' is replaced when mapping has 'cluster-a'."""
        mapping = {"cluster-a": "admin@rees46-k8s"}
        result = deanonymize_text("Cluster-a shows issues", mapping)
        assert result == "admin@rees46-k8s shows issues"

    def test_capitalized_cluster_alias_in_sentence(self) -> None:
        """Test mixed case aliases in a sentence are all replaced."""
        mapping = {"cluster-a": "prod", "cluster-b": "stage"}
        result = deanonymize_text("Cluster-a and cluster-b are affected", mapping)
        assert result == "prod and stage are affected"

    def test_all_capitalized_cluster_alias(self) -> None:
        """Test all-caps 'CLUSTER-A' is replaced."""
        mapping = {"cluster-a": "prod"}
        result = deanonymize_text("CLUSTER-A is primary", mapping)
        assert result == "prod is primary"

    def test_capitalized_namespace_alias_replaced(self) -> None:
        """Test capitalized 'Namespace-f' is replaced when mapping has 'namespace-f'."""
        mapping = {"namespace-f": "kube-system"}
        result = deanonymize_text("Namespace-f has issues", mapping)
        assert result == "kube-system has issues"

    def test_capitalized_name_alias_replaced(self) -> None:
        """Test capitalized 'Name-a' is replaced when mapping has 'name-a'."""
        mapping = {"name-a": "blog-regular-backup"}
        result = deanonymize_text("Name-a deployment is failing", mapping)
        assert result == "blog-regular-backup deployment is failing"

    def test_capitalized_alias_in_command(self) -> None:
        """Test capitalized aliases in kubectl commands are replaced."""
        mapping = {"cluster-a": "prod-cluster", "namespace-b": "monitoring"}
        result = deanonymize_command(
            "kubectl get pods -n Namespace-b --context Cluster-a", mapping
        )
        assert result == "kubectl get pods -n monitoring --context prod-cluster"

    def test_capitalized_alias_with_punctuation(self) -> None:
        """Test capitalized aliases with punctuation boundaries."""
        mapping = {"cluster-a": "prod"}
        result = deanonymize_text("Cluster-a, Cluster-b, and cluster-c", mapping)
        assert result == "prod, Cluster-b, and cluster-c"

    def test_capitalized_alias_in_list_payload(self) -> None:
        """Test capitalized aliases in list payloads are replaced."""
        mapping = {"cluster-a": "prod-cluster"}
        payload = ["Cluster-a", "cluster-a", "other"]
        result = deanonymize_payload(payload, mapping)
        assert result == ["prod-cluster", "prod-cluster", "other"]

    def test_capitalized_alias_in_dict_payload(self) -> None:
        """Test capitalized aliases in dict payloads are replaced."""
        mapping = {"cluster-a": "prod", "namespace-b": "default"}
        payload = {
            "triageOrder": ["Cluster-a", "namespace-b"],
            "topConcerns": ["Cluster-a latency", "Namespace-b storage"],
        }
        result = deanonymize_payload(payload, mapping)
        assert result["triageOrder"] == ["prod", "default"]
        assert result["topConcerns"] == ["prod latency", "default storage"]


class TestAssertNoProviderAliases:
    """Tests for the assert_no_provider_aliases helper."""

    def test_detects_cluster_alias(self) -> None:
        """Test that cluster-a leak is detected."""
        payload = {"summary": "cluster-a shows issues"}
        with pytest.raises(AssertionError) as exc_info:
            assert_no_provider_aliases(payload)
        assert "cluster-a" in str(exc_info.value)

    def test_detects_capitalized_cluster_alias(self) -> None:
        """Test that capitalized Cluster-a leak is detected."""
        payload = {"summary": "Cluster-a shows issues"}
        with pytest.raises(AssertionError) as exc_info:
            assert_no_provider_aliases(payload)
        # The regex normalizes to lowercase in the match output
        assert "cluster-a" in str(exc_info.value).lower()

    def test_detects_namespace_alias(self) -> None:
        """Test that namespace-f leak is detected."""
        payload = {"command": "kubectl get pods -n namespace-f"}
        with pytest.raises(AssertionError) as exc_info:
            assert_no_provider_aliases(payload)
        assert "namespace-f" in str(exc_info.value)

    def test_detects_name_alias(self) -> None:
        """Test that name-a leak is detected."""
        payload = {"description": "Check name-a deployment"}
        with pytest.raises(AssertionError) as exc_info:
            assert_no_provider_aliases(payload)
        assert "name-a" in str(exc_info.value)

    def test_allows_real_cluster_names(self) -> None:
        """Test that real cluster names are NOT detected as leaks."""
        payload = {
            "summary": "Issues in admin@rees46-k8s",
            "command": "kubectl --context prod-cluster",
        }
        # Should NOT raise
        leaks = assert_no_provider_aliases(payload)
        assert leaks == []

    def test_allows_real_cluster_with_hyphen(self) -> None:
        """Test that real cluster names with hyphens are NOT detected."""
        payload = {
            "summary": "Issues in my-cluster-prod",
            "command": "kubectl --context cluster-prod-1",
        }
        # Should NOT raise
        leaks = assert_no_provider_aliases(payload)
        assert leaks == []

    def test_skips_alias_mapping_fields(self) -> None:
        """Test that alias_mapping field contents are skipped."""
        payload = {
            "summary": "Clean summary",
            "alias_mapping": {"cluster-a": "real"},  # Should be skipped
            "provider_alias_mapping": {"cluster-b": "real2"},  # Should be skipped
        }
        # Should NOT raise
        leaks = assert_no_provider_aliases(payload)
        assert leaks == []

    def test_nested_structure_detection(self) -> None:
        """Test that aliases in nested structures are detected."""
        payload = {
            "topConcerns": [
                "Cluster-a latency",
                {"nested": "Namespace-b storage"},
            ],
            "nextChecks": [
                "kubectl --context cluster-c",
            ],
        }
        with pytest.raises(AssertionError) as exc_info:
            assert_no_provider_aliases(payload)
        error_msg = str(exc_info.value)
        # Should detect multiple leaks
        assert "Cluster-a" in error_msg or "cluster-a" in error_msg.lower()


class TestAliasPattern:
    """Tests for the ALIAS_PATTERN regex exported for external use.

    Note: ALIAS_PATTERN uses standard regex word boundaries (\b), which means it
    may match aliases inside hyphenated words. This is intentional for detection
    purposes (better to flag potential leaks), while deanonymize_text uses stricter
    boundaries to avoid false replacements.
    """

    def test_matches_cluster_a(self) -> None:
        """ALIAS_PATTERN matches cluster-a."""
        matches = ALIAS_PATTERN.findall("cluster-a shows issues")
        assert matches == ["cluster-a"]

    def test_matches_Cluster_a(self) -> None:
        """ALIAS_PATTERN matches Cluster-a (case-insensitive)."""
        matches = ALIAS_PATTERN.findall("Cluster-a shows issues")
        assert matches == ["Cluster-a"]

    def test_matches_namespace_f(self) -> None:
        """ALIAS_PATTERN matches namespace-f."""
        matches = ALIAS_PATTERN.findall("-n namespace-f")
        assert matches == ["namespace-f"]

    def test_matches_Name_a(self) -> None:
        """ALIAS_PATTERN matches Name-a (case-insensitive)."""
        matches = ALIAS_PATTERN.findall("Check Name-a deployment")
        assert matches == ["Name-a"]

    def test_does_not_match_admin_at_rees(self) -> None:
        """ALIAS_PATTERN does not match admin@rees46-k8s (no hyphen-letter pattern)."""
        matches = ALIAS_PATTERN.findall("Issues in admin@rees46-k8s")
        assert matches == []

    def test_matches_inside_hyphenated_word(self) -> None:
        """ALIAS_PATTERN matches cluster-a inside my-cluster-a.

        This is by design for detection - better to flag potential leaks.
        The deanonymize_text() function uses stricter boundaries to avoid
        false replacements in real usage.
        """
        matches = ALIAS_PATTERN.findall("Issues in my-cluster-a node")
        assert matches == ["cluster-a"]  # Detects the alias inside the word

    def test_does_not_match_cluster_prod_1(self) -> None:
        """ALIAS_PATTERN does not match cluster-prod-1 (requires -letter suffix)."""
        matches = ALIAS_PATTERN.findall("--context cluster-prod-1")
        assert matches == []  # No match - pattern requires -letter at end

    def test_matches_all_categories(self) -> None:
        """ALIAS_PATTERN matches all known alias categories."""
        # The pattern matches category-prefixed aliases
        text = "cluster-a namespace-b node-c pod-d service-e workload-f name-g job-h cronjob-i deployment-j statefulset-k daemonset-l host-m release-n crd-o label-p"
        matches = ALIAS_PATTERN.findall(text)
        # Each category-{letter} should match once
        expected_categories = [
            "cluster-a", "namespace-b", "node-c", "pod-d", "service-e",
            "workload-f", "name-g", "job-h", "cronjob-i", "deployment-j",
            "statefulset-k", "daemonset-l", "host-m", "release-n", "crd-o", "label-p"
        ]
        assert matches == expected_categories
