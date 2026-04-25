#!/usr/bin/env python3
"""Smoke test for llama.cpp JSON generation.

This script tests that the configured llama.cpp endpoint can generate valid JSON
with minimal settings, without requiring Kubernetes or a health loop.

Usage:
    python scripts/smoke_llamacpp_json.py

Environment variables (required):
    LLAMA_CPP_BASE_URL: The llama.cpp endpoint URL
    LLAMA_CPP_MODEL: The model name

Environment variables (optional):
    LLAMA_CPP_API_KEY: API key if required
    LLAMA_CPP_TIMEOUT_SECONDS: Timeout in seconds (default: 120)
    LLAMA_CPP_TEMPERATURE: Temperature setting (default: 0.0)
    LLAMA_CPP_TOP_P: Top-p setting
    LLAMA_CPP_SEED: Seed for deterministic generation
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

# Add repo/src to path for imports
_repo_root = Path(__file__).resolve().parents[1]
_src_path = _repo_root / "src"
sys.path.insert(0, str(_src_path))

# noqa: E402 - required for script to find package
from k8s_diag_agent.llm.base import LLMAssessmentInput
from k8s_diag_agent.llm.llamacpp_provider import (  # noqa: E402
    LlamaCppProvider,
    LlamaCppProviderConfig,
    LLMResponseParseError,
    classify_llm_failure,
)


def run_smoke_test() -> dict[str, Any]:
    """Run the llama.cpp JSON smoke test.
    
    Returns:
        Dict with test results:
        - success: bool
        - response_parsed: bool
        - failure_class: str | None
        - exception_type: str | None
        - response_content_prefix: str | None
        - generation_settings: dict
        - elapsed_ms: int | None
        - error: str | None
        - finish_reason: str | None
        - response_content_chars: int | None
        - completion_stopped_by_length: bool | None
        - max_tokens: int | None
    """
    result: dict[str, Any] = {
        "success": False,
        "response_parsed": False,
        "failure_class": None,
        "exception_type": None,
        "response_content_prefix": None,
        "generation_settings": {},
        "elapsed_ms": None,
        "error": None,
        "finish_reason": None,
        "response_content_chars": None,
        "completion_stopped_by_length": None,
        "max_tokens": None,
    }
    
    start = time.perf_counter()
    max_tokens = 64
    
    try:
        # Load config from environment
        config = LlamaCppProviderConfig.from_env()
        
        # Record generation settings used
        result["generation_settings"] = {
            "temperature": config.temperature,
            "top_p": config.top_p,
            "top_k": config.top_k,
            "repeat_penalty": config.repeat_penalty,
            "seed": config.seed,
            "stop_count": len(config.stop) if config.stop else 0,
            "enable_thinking": config.enable_thinking,
        }
        result["max_tokens"] = max_tokens
        
        provider = LlamaCppProvider(config=config)
        
        # Tiny prompt that should produce valid JSON
        prompt = 'Return valid JSON: {"ok": true}'
        
        payload = LLMAssessmentInput(
            primary_snapshot={"test": "data"},
            secondary_snapshot={},
            comparison={},
            comparison_metadata=None,
            collection_statuses={},
        )
        
        # Make the call - we expect valid JSON output
        try:
            response = provider.assess(
                prompt,
                payload,
                validate_schema=False,  # Skip schema validation for smoke test
                max_tokens=max_tokens,
            )
            
            # Check if response is valid JSON object
            if isinstance(response, dict):
                result["response_parsed"] = True
                result["success"] = True
                
                # Include a prefix of the parsed response
                response_str = json.dumps(response, ensure_ascii=False)
                result["response_content_prefix"] = response_str[:200]
            else:
                result["failure_class"] = "invalid_response_type"
                result["exception_type"] = type(response).__name__
                
        except LLMResponseParseError as exc:
            # Structured output failure - use classify_llm_failure for classification
            result["failure_class"], result["exception_type"] = classify_llm_failure(exc)
            result["error"] = str(exc)[:500]
            
            # Include structured diagnostics from the exception
            diagnostics = exc.to_diagnostics()
            if diagnostics.get("finish_reason"):
                result["finish_reason"] = diagnostics["finish_reason"]
            if diagnostics.get("response_content_chars"):
                result["response_content_chars"] = diagnostics["response_content_chars"]
            if diagnostics.get("response_content_prefix"):
                result["response_content_prefix"] = diagnostics["response_content_prefix"]
            if diagnostics.get("completion_stopped_by_length") is not None:
                result["completion_stopped_by_length"] = diagnostics["completion_stopped_by_length"]
                
        except Exception as exc:
            # Record the failure details using classify_llm_failure
            result["failure_class"], result["exception_type"] = classify_llm_failure(exc)
            result["error"] = str(exc)[:500]
                
    except RuntimeError as exc:
        # Config loading failed
        result["failure_class"] = "config_error"
        result["exception_type"] = "RuntimeError"
        result["error"] = str(exc)
    except Exception as exc:
        result["failure_class"] = "unknown_error"
        result["exception_type"] = exc.__class__.__name__
        result["error"] = str(exc)[:500]
    
    result["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
    
    return result


def main() -> int:
    """Main entry point for smoke test."""
    print("llama.cpp JSON Smoke Test")
    print("=" * 50)
    
    result = run_smoke_test()
    
    print(f"Success: {result['success']}")
    print(f"Response parsed: {result['response_parsed']}")
    print(f"Elapsed: {result['elapsed_ms']}ms")
    print(f"Failure class: {result['failure_class']}")
    print(f"Exception type: {result['exception_type']}")
    
    if result['response_content_prefix']:
        print(f"Response prefix: {result['response_content_prefix']}")
    
    print("\nGeneration settings used:")
    for key, value in result['generation_settings'].items():
        print(f"  {key}: {value}")
    
    # Include additional diagnostics if present
    if result.get('finish_reason'):
        print("\nDiagnostics:")
        print(f"  finish_reason: {result['finish_reason']}")
        if result.get('response_content_chars') is not None:
            print(f"  response_content_chars: {result['response_content_chars']}")
        if result.get('completion_stopped_by_length') is not None:
            print(f"  completion_stopped_by_length: {result['completion_stopped_by_length']}")
    
    if result['error']:
        print(f"\nError: {result['error']}")
    
    print("\n" + "=" * 50)
    if result['success']:
        print("SMOKE TEST: PASSED")
        return 0
    else:
        print("SMOKE TEST: FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
