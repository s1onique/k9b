"""Tests for incident_diagnosis_auto_loop_entrypoints module.

Focused tests for:
1. Budget propagation through the config chain
2. _positive_int validation helper
3. collect_automatic_diagnosis_evidence entrypoint
"""


from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
)
from k8s_diag_agent.collect.incident_diagnosis_auto_loop_entrypoints import (
    _positive_int,
    collect_automatic_diagnosis_evidence,
)


class TestPositiveInt:
    """Tests for _positive_int coercion helper."""

    def test_positive_int_returns_value_for_positive_integers(self) -> None:
        """Positive integers pass through unchanged."""
        assert _positive_int(1, 10) == 1
        assert _positive_int(5, 10) == 5
        assert _positive_int(100, 10) == 100

    def test_positive_int_returns_default_for_zero(self) -> None:
        """Zero returns default (zero is not a valid budget)."""
        assert _positive_int(0, 10) == 10

    def test_positive_int_returns_default_for_negative(self) -> None:
        """Negative integers return default."""
        assert _positive_int(-1, 10) == 10
        assert _positive_int(-100, 10) == 10

    def test_positive_int_returns_default_for_boolean(self) -> None:
        """Booleans return default (JSON booleans are distinct from integers)."""
        assert _positive_int(True, 10) == 10
        assert _positive_int(False, 10) == 10

    def test_positive_int_returns_default_for_string(self) -> None:
        """Strings return default."""
        assert _positive_int("5", 10) == 10
        assert _positive_int("", 10) == 10

    def test_positive_int_returns_default_for_none(self) -> None:
        """None returns default."""
        assert _positive_int(None, 10) == 10

    def test_positive_int_returns_default_for_float(self) -> None:
        """Floats return default (budget fields are integers)."""
        assert _positive_int(5.0, 10) == 10
        assert _positive_int(3.14, 10) == 10

    def test_positive_int_returns_default_for_list(self) -> None:
        """Lists return default."""
        assert _positive_int([1, 2, 3], 10) == 10

    def test_positive_int_returns_default_for_dict(self) -> None:
        """Dicts return default."""
        assert _positive_int({"key": "value"}, 10) == 10

    def test_positive_int_respects_default_value(self) -> None:
        """Default value is used correctly."""
        assert _positive_int(-1, 5) == 5
        assert _positive_int(0, 1) == 1
        assert _positive_int(True, 99) == 99


class TestAutomaticDiagnosisLoopConfigDefaults:
    """Tests for AutomaticDiagnosisLoopConfig default values."""

    def test_default_max_passes_per_incident_is_one(self) -> None:
        """Default max_passes_per_incident should be 1."""
        config = AutomaticDiagnosisLoopConfig()
        assert config.max_passes_per_incident == 1

    def test_default_max_checks_per_pass(self) -> None:
        """Default max_checks_per_pass should be 5."""
        config = AutomaticDiagnosisLoopConfig()
        assert config.max_checks_per_pass == 5

    def test_config_can_be_constructed_with_custom_values(self) -> None:
        """Config can be constructed with custom values for lab scenarios."""
        config = AutomaticDiagnosisLoopConfig(
            max_passes_per_incident=5,
            max_checks_per_pass=10,
            max_incidents_per_run=20,
        )
        assert config.max_passes_per_incident == 5
        assert config.max_checks_per_pass == 10
        assert config.max_incidents_per_run == 20

    def test_p4c_scenario_requires_minimum_two_passes(self) -> None:
        """P4c lab scenario requires at least 2 passes (MIN_REQUIRED_PASSES=2).

        This test documents the contract: when P4c requires 2 passes,
        the budget must be set to >= 2.
        """
        # P4c with MIN_REQUIRED_PASSES=2 requires budget >= 2
        config = AutomaticDiagnosisLoopConfig(max_passes_per_incident=2)
        assert config.max_passes_per_incident >= 2


class TestCollectAutomaticDiagnosisEvidence:
    """Tests for collect_automatic_diagnosis_evidence entrypoint."""

    def test_entrypoint_accepts_config_parameter(self) -> None:
        """Entry point should accept optional config parameter.

        This test verifies the contract that allows lab scenarios
        to override the default budget limit.
        """
        # This test verifies the function signature accepts config
        # We can't fully test without a running incident store,
        # but we verify the signature is correct
        import inspect
        sig = inspect.signature(collect_automatic_diagnosis_evidence)
        params = list(sig.parameters.keys())
        assert "incident_id" in params
        assert "external_analysis_dir" in params
        assert "config" in params

        # Verify config has a default of None
        config_param = sig.parameters["config"]
        assert config_param.default is None
