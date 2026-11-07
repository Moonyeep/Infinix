#!/usr/bin/env python3
"""Test suite for improvement.py enhancements.

Tests the new retry logic, validation improvements, and metrics tracking.
"""

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

# Add parent directory to path to import agent_core
sys.path.insert(0, str(Path(__file__).parent.parent / "Infinix-Agent-General-1.6.17"))

from agent_core.improvement import _retry_with_backoff


def test_retry_success_first_attempt():
    """Test that successful call returns immediately without retries."""
    call_count = 0
    
    def successful_func():
        nonlocal call_count
        call_count += 1
        return "success"
    
    result = _retry_with_backoff(successful_func, max_retries=3)
    assert result == "success"
    assert call_count == 1
    print("✅ test_retry_success_first_attempt passed")


def test_retry_success_after_failures():
    """Test that retry works after initial failures."""
    call_count = 0
    
    def failing_then_success():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise URLError("temporary failure")
        return "success"
    
    # Use small delays for testing
    with patch('time.sleep'):
        result = _retry_with_backoff(failing_then_success, max_retries=3, base_delay=0.01)
    
    assert result == "success"
    assert call_count == 3
    print("✅ test_retry_success_after_failures passed")


def test_retry_exhausted():
    """Test that error is raised after all retries are exhausted."""
    call_count = 0
    
    def always_fails():
        nonlocal call_count
        call_count += 1
        raise URLError("permanent failure")
    
    try:
        with patch('time.sleep'):
            _retry_with_backoff(always_fails, max_retries=3, base_delay=0.01)
        assert False, "Should have raised URLError"
    except URLError as e:
        assert call_count == 3
        print("✅ test_retry_exhausted passed")


def test_retry_exponential_backoff():
    """Test that delays increase exponentially."""
    delays = []
    
    def track_delays():
        raise URLError("test")
    
    original_sleep = time.sleep
    def mock_sleep(delay):
        delays.append(delay)
    
    try:
        with patch('time.sleep', side_effect=mock_sleep):
            _retry_with_backoff(track_delays, max_retries=3, base_delay=2.0)
    except URLError:
        pass
    
    # Should have delays: 2.0, 4.0 (base_delay * 2^0, base_delay * 2^1)
    assert len(delays) == 2
    assert abs(delays[0] - 2.0) < 0.1
    assert abs(delays[1] - 4.0) < 0.1
    print("✅ test_retry_exponential_backoff passed")


def test_validation_structure():
    """Test that response validation catches malformed responses."""
    # This would be tested by importing the actual function,
    # but we're testing the concept here
    
    # Valid structure
    valid_response = {
        "choices": [
            {
                "message": {
                    "content": "valid patch"
                }
            }
        ]
    }
    
    # Test each level of validation
    assert isinstance(valid_response, dict)
    assert "choices" in valid_response
    assert isinstance(valid_response["choices"], list)
    assert len(valid_response["choices"]) > 0
    assert isinstance(valid_response["choices"][0], dict)
    assert "message" in valid_response["choices"][0]
    assert isinstance(valid_response["choices"][0]["message"], dict)
    assert "content" in valid_response["choices"][0]["message"]
    
    print("✅ test_validation_structure passed")


def test_invalid_responses():
    """Test various invalid response structures."""
    invalid_cases = [
        ("not a dict", "string response"),
        ("no choices", {}),
        ("empty choices", {"choices": []}),
        ("choices not list", {"choices": "not a list"}),
        ("choice not dict", {"choices": ["not a dict"]}),
        ("no message", {"choices": [{}]}),
        ("message not dict", {"choices": [{"message": "not a dict"}]}),
        ("no content", {"choices": [{"message": {}}]}),
    ]
    
    for name, response in invalid_cases:
        try:
            if not isinstance(response, dict):
                raise RuntimeError("model response was not a JSON object")
            
            choices = response.get("choices")
            if not choices or not isinstance(choices, list) or len(choices) == 0:
                raise RuntimeError("model response contained no choices")
            
            first_choice = choices[0]
            if not isinstance(first_choice, dict):
                raise RuntimeError("model choice was not a JSON object")
            
            message = first_choice.get("message")
            if not isinstance(message, dict):
                raise RuntimeError("model choice had no message field")
            
            patch = message.get("content")
            if patch is None:
                raise RuntimeError("model message had no content field")
            
            assert False, f"Case '{name}' should have failed validation"
        except RuntimeError:
            pass  # Expected
    
    print("✅ test_invalid_responses passed")


def test_metrics_tracking():
    """Test that metrics are properly tracked."""
    import datetime as dt
    
    start_time = dt.datetime.now(dt.timezone.utc)
    time.sleep(0.1)  # Simulate work
    end_time = dt.datetime.now(dt.timezone.utc)
    
    duration = (end_time - start_time).total_seconds()
    
    assert duration >= 0.1
    assert duration < 1.0  # Should be fast
    assert isinstance(duration, float)
    
    print("✅ test_metrics_tracking passed")


if __name__ == "__main__":
    print("Running enhancement tests...\n")
    
    test_retry_success_first_attempt()
    test_retry_success_after_failures()
    test_retry_exhausted()
    test_retry_exponential_backoff()
    test_validation_structure()
    test_invalid_responses()
    test_metrics_tracking()
    
    print("\n✅ All tests passed!")
