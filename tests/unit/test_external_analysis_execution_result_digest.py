"""Tests for ExecutionResultDigest and execution context integration.

This file re-exports from the split test modules to maintain backward compatibility.
Actual tests are organized in:
- test_external_analysis_execution_result_digest_core.py: Core class and builder tests
- test_external_analysis_execution_result_digest_signals.py: Signal extraction tests
- test_external_analysis_execution_result_digest_provenance.py: Provenance attachment tests

Import tests from split modules directly if needed.
"""

# Re-export all tests from split modules for backward compatibility
from tests.unit.test_external_analysis_execution_result_digest_core import (
    TestBuildExecutionContext,
    TestBuildExecutionResultDigest,
    TestBuildExecutionResultDigests,
    TestExecutionContextToDict,
    TestExecutionResultDigestClass,
)
from tests.unit.test_external_analysis_execution_result_digest_provenance import (
    TestProvenanceAttachment,
)
from tests.unit.test_external_analysis_execution_result_digest_signals import (
    TestExecutionResultDigestSignalExtraction,
)

if __name__ == "__main__":
    import unittest
    
    # Load all test modules
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestExecutionResultDigestClass))
    suite.addTests(loader.loadTestsFromTestCase(TestBuildExecutionResultDigest))
    suite.addTests(loader.loadTestsFromTestCase(TestBuildExecutionResultDigests))
    suite.addTests(loader.loadTestsFromTestCase(TestBuildExecutionContext))
    suite.addTests(loader.loadTestsFromTestCase(TestExecutionContextToDict))
    suite.addTests(loader.loadTestsFromTestCase(TestExecutionResultDigestSignalExtraction))
    suite.addTests(loader.loadTestsFromTestCase(TestProvenanceAttachment))
    
    unittest.TextTestRunner(verbosity=2).run(suite)