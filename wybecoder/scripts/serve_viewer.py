#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Local dev server for the trajectory viewer.

Serves docs/ as static files over HTTP, which is required for fetch() to work.
Also provides an API endpoint for large decomp rollouts that exceed the
static file size limit (marked with too_large: true).

Usage:
    python scripts/build_viewer_data.py   # one-time: generate dialog data
    python scripts/serve_viewer.py        # serve at http://localhost:8000/viewer.html
"""

import argparse
import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"


class ViewerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/rollout":
            self._handle_rollout(parsed)
        else:
            super().do_GET()

    def _handle_rollout(self, parsed):
        """Fetch a single sub-agent's dialog from a large JSONL file on demand."""
        params = parse_qs(parsed.query)
        run = params.get("run", [None])[0]
        file = params.get("file", [None])[0]
        line = params.get("line", [None])[0]
        sub = params.get("sub", [None])[0]

        if not all([run, file, line]):
            self._json_error(400, "Missing required params: run, file, line")
            return

        try:
            line_num = int(line)
        except ValueError:
            self._json_error(400, "line must be an integer")
            return

        if ".." in run or ".." in file:
            self._json_error(400, "Invalid path")
            return

        filepath = REPO_ROOT / run / file
        if not filepath.is_file():
            self._json_error(404, f"File not found: {run}/{file}")
            return

        try:
            target_line = None
            with open(filepath) as f:
                for i, raw_line in enumerate(f):
                    if i == line_num:
                        target_line = raw_line
                        break

            if target_line is None:
                self._json_error(404, f"Line {line_num} not found")
                return

            obj = json.loads(target_line)

            if sub is not None:
                # Return single sub-agent dialog
                dialogs = obj.get("dialogs", {})
                if sub in dialogs:
                    dlg = dialogs[sub]
                    result = {"dialog": dlg}
                else:
                    self._json_error(404, f"Sub-agent {sub} not found")
                    return
            else:
                # Return revisions + agent_results (no dialogs)
                result = {
                    "revisions": obj.get("revisions", []),
                    "agent_results": obj.get("agent_results", {}),
                }

            payload = json.dumps(result)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(payload))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload.encode())

        except json.JSONDecodeError as e:
            self._json_error(500, f"JSON parse error: {e}")
        except Exception as e:
            self._json_error(500, str(e))

    def _json_error(self, code, msg):
        payload = json.dumps({"error": msg})
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(payload))
        self.end_headers()
        self.wfile.write(payload.encode())

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description="Serve trajectory viewer locally")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    viewer_data = DOCS_DIR / "viewer_data" / "dialogs"
    if not viewer_data.exists():
        print("Warning: docs/viewer_data/dialogs/ not found.")
        print("Run 'python scripts/build_viewer_data.py' first.\n")

    server = HTTPServer(("localhost", args.port), ViewerHandler)
    print(f"Serving viewer at http://localhost:{args.port}/viewer.html")
    print(f"Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
