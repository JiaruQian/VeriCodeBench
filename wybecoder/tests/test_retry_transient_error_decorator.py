# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

# Run tests with:
# python -m pytest tests/test_retry_transient_error_decorator.py -v
import pytest
from unittest.mock import Mock
from src.utils import retry_on_transient_errors


class TestRetryOnTransientErrors:
    """Tests for the retry_on_transient_errors decorator."""

    def test_retry_when_response_is_none(self):
        """Test that decorator retries when function returns None."""
        mock_func = Mock(side_effect=[None, None, "success"])
        
        @retry_on_transient_errors(max_attempts=10, base_backoff=0.5)
        def func_returns_none():
            return mock_func()
        
        result = func_returns_none()
        assert result == "success"
        assert mock_func.call_count == 3

    def test_retry_when_response_is_empty_string(self):
        """Test that decorator retries when function returns empty string."""
        mock_func = Mock(side_effect=["", None, "", "success"])
        
        @retry_on_transient_errors(max_attempts=5, base_backoff=0.5)
        def func_returns_empty_string_or_None():
            return mock_func()
        
        result = func_returns_empty_string_or_None()
        assert result == "success"
        assert mock_func.call_count == 4
    
    
    def test_retry_when_response_is_empty_string_after_max_retry(self):
        """Test that decorator retries when function returns empty string."""
        mock_func = Mock(side_effect=["", "", "", ""])
        
        @retry_on_transient_errors(max_attempts=4, base_backoff=0.5)
        def func_returns_empty_string_or_None():
            return mock_func()
        
        with pytest.raises(RuntimeError, match="Failed after 4 attempts: returned None"):
            result = func_returns_empty_string_or_None()

    def test_retry_on_transient_error_internal_server_error(self):
        """Test that decorator retries on 'internal server error' message."""
        mock_func = Mock(
            side_effect=[
                RuntimeError("Internal server error occurred"),
                RuntimeError("Timeout"),
                RuntimeError("Internal server error occurred"),
                RuntimeError("Internal server error occurred"),
                "success"
            ]
        )
        
        @retry_on_transient_errors(max_attempts=5, base_backoff=0.01)
        def func_with_transient_error():
            return mock_func()
        
        result = func_with_transient_error()
        assert result == "success"
        assert mock_func.call_count == 5

    def test_retry_on_transient_error_timeout(self):
        """Test that decorator retries on 'timeout' error."""
        mock_func = Mock(
            side_effect=[
                TimeoutError("Request timeout"),
                "success"
            ]
        )
        
        @retry_on_transient_errors(max_attempts=5, base_backoff=0.01)
        def func_with_timeout():
            return mock_func()
        
        result = func_with_timeout()
        assert result == "success"
        assert mock_func.call_count == 2
