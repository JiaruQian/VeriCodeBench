# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""HTTP proxy server for leanexplore MCP server.

This provides an HTTP API wrapper around the leanexplore MCP server,
enabling stateless HTTP requests and natural parallelism.
"""

import json
import socket
from typing import Any
from logging import getLogger
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import threading

from src.leanexplore_mcp import (
    start_server as _mcp_start_server,
    stop_server as _mcp_stop_server,
    search as _mcp_search,
)

logger = getLogger()

_HTTP_SERVER: HTTPServer | None = None
_HTTP_THREAD: threading.Thread | None = None


class LeanExploreHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for leanexplore API."""
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query_params = urllib.parse.parse_qs(parsed_path.query)
        
        if path == "/search":
            self._handle_search(query_params)
        elif path == "/health":
            self._handle_health()
        else:
            self._send_error(404, "Not Found")
    
    def do_POST(self):
        """Handle POST requests with JSON body."""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        
        if path == "/search":
            self._handle_search_post()
        else:
            self._send_error(404, "Not Found")
    
    def _handle_search(self, query_params: dict):
        """Handle GET /search?query=...&limit=...&package_filters=..."""
        try:
            query = query_params.get("query", [""])[0]
            if not query:
                self._send_error(400, "Missing 'query' parameter")
                return
            
            limit = int(query_params.get("limit", ["10"])[0])
            package_filters = query_params.get("package_filters", [])
            if package_filters:
                package_filters = package_filters[0].split(",") if isinstance(package_filters[0], str) else package_filters
            else:
                package_filters = None
            
            result = _mcp_search(query, limit, package_filters)
            self._send_json(200, result)
        except Exception as e:
            logger.error(f"Error in search: {e}", exc_info=True)
            self._send_error(500, str(e))
    
    def _handle_search_post(self):
        """Handle POST /search with JSON body."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            
            query = data.get("query")
            if not query:
                self._send_error(400, "Missing 'query' in request body")
                return
            
            limit = data.get("limit", 10)
            package_filters = data.get("package_filters")
            
            result = _mcp_search(query, limit, package_filters)
            self._send_json(200, result)
        except Exception as e:
            logger.error(f"Error in search: {e}", exc_info=True)
            self._send_error(500, str(e))
    
    def _handle_health(self):
        """Handle GET /health"""
        self._send_json(200, {"status": "ok"})
    
    def _send_json(self, status_code: int, data: Any):
        """Send JSON response."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        
        json_data = json.dumps(data, ensure_ascii=False)
        self.wfile.write(json_data.encode("utf-8"))
    
    def _send_error(self, status_code: int, message: str):
        """Send error response."""
        self._send_json(status_code, {"error": message})
    
    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.debug(f"{self.address_string()} - {format % args}")


def start_http_proxy(port: int = 8089, backend: str = "local") -> None:
    """
    Start the HTTP proxy server for leanexplore.
    
    Args:
        port: Port to listen on (default: 8089)
        backend: Backend for leanexplore ("local" or "api")
    """
    global _HTTP_SERVER, _HTTP_THREAD
    
    if _HTTP_SERVER is not None:
        logger.info("HTTP proxy already running")
        return
    
    # Start the underlying MCP server
    _mcp_start_server(backend=backend, log_level="ERROR")
    
    server_address = ("localhost", port)
    
    class ServerWithBacklog(HTTPServer):
        def server_bind(self):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(self.server_address)
            self.socket.listen(128)
    
    _HTTP_SERVER = ServerWithBacklog(server_address, LeanExploreHTTPHandler)
    
    def run_server():
        logger.info(f"Starting leanexplore HTTP proxy on http://localhost:{port}")
        _HTTP_SERVER.serve_forever()
    
    _HTTP_THREAD = threading.Thread(target=run_server, daemon=True, name="LeanExploreHTTPProxy")
    _HTTP_THREAD.start()
    
    logger.info(f"leanexplore HTTP proxy started on port {port}")


def stop_http_proxy() -> None:
    """Stop the HTTP proxy server."""
    global _HTTP_SERVER, _HTTP_THREAD
    
    if _HTTP_SERVER:
        logger.info("Stopping leanexplore HTTP proxy...")
        _HTTP_SERVER.shutdown()
        _HTTP_SERVER.server_close()
        _HTTP_SERVER = None
    
    if _HTTP_THREAD and _HTTP_THREAD.is_alive():
        _HTTP_THREAD.join(timeout=2)
        _HTTP_THREAD = None
    
    # Stop underlying MCP server
    _mcp_stop_server()
    
    logger.info("leanexplore HTTP proxy stopped")


def search(query: str, limit: int = 10, package_filters: list[str] | None = None) -> dict[str, Any]:
    """
    Search using HTTP proxy (for backward compatibility).
    
    This is a convenience wrapper that uses the MCP client directly.
    For true HTTP access, use the HTTP endpoints directly.
    """
    return _mcp_search(query, limit, package_filters)
