import unittest

from tests.path_helper import ensure_src_in_path

ensure_src_in_path()

from k8s_diag_agent.models import ConfidenceLevel, Hypothesis, Layer
from k8s_diag_agent.recommend.next_steps import build_recommended_action, propose_next_steps


class RecommendTest(unittest.TestCase):
    def _dummy_hypothesis(self) -> Hypothesis:
        return Hypothesis(
            id="test",
            description="placeholder",
            confidence=ConfidenceLevel.LOW,
            probable_layer=Layer.WORKLOAD,
            what_would_falsify="fail",
        )

    def test_next_checks_and_action(self) -> None:
        checks = propose_next_steps([self._dummy_hypothesis()])
        self.assertTrue(checks)
        self.assertEqual(checks[0].method, "kubectl")
        action = build_recommended_action()
        self.assertEqual(action.safety_level.value, "low-risk")


if __name__ == "__main__":
    unittest.main()
