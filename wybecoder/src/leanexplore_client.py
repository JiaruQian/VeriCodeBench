# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""HTTP client for leanexplore HTTP proxy.

This provides a simple HTTP client interface to the leanexplore HTTP proxy.
"""

import json
import urllib.request
import urllib.parse
from typing import Any
from logging import getLogger

logger = getLogger()


class LeanExploreHTTPClient:
    """HTTP client for leanexplore API."""
    
    def __init__(self, base_url: str = "http://localhost:8089"):
        """
        Initialize the HTTP client.
        
        Args:
            base_url: Base URL of the HTTP proxy server
        """
        self.base_url = base_url.rstrip("/")
    
    def search(
        self, query: str, limit: int = 10, package_filters: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Search for Lean definitions and theorems.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            package_filters: Optional list of package names to filter by
        
        Returns:
            Dictionary with search results
        """
        # Use POST for better parameter handling
        url = f"{self.base_url}/search"
        data = {"query": query, "limit": limit}
        if package_filters:
            data["package_filters"] = package_filters
        
        return self._post(url, data)
    
    def health(self) -> dict[str, Any]:
        """Check server health."""
        url = f"{self.base_url}/health"
        return self._get(url)
    
    def _get(self, url: str) -> dict[str, Any]:
        """Make GET request."""
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    
    def _post(self, url: str, data: dict[str, Any]) -> dict[str, Any]:
        """Make POST request with JSON body."""
        json_data = json.dumps(data).encode("utf-8")
        
        req = urllib.request.Request(url, data=json_data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


# Global client instance
_client: LeanExploreHTTPClient | None = None


def get_client(base_url: str = "http://localhost:8089") -> LeanExploreHTTPClient:
    """Get or create the global HTTP client."""
    global _client
    if _client is None:
        _client = LeanExploreHTTPClient(base_url)
    return _client


def search(query: str, limit: int = 10, package_filters: list[str] | None = None) -> dict[str, Any]:
    return get_client().search(query, limit, package_filters)
