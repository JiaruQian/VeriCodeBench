#!/bin/bash
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

# Start local loogle server on port 8088

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Navigate to the loogle package directory
LOOGLE_DIR="$SCRIPT_DIR/../.lake/packages/loogle"

if [ ! -d "$LOOGLE_DIR" ]; then
    echo "Error: loogle directory not found at $LOOGLE_DIR"
    echo "Make sure loogle is installed as a Lake dependency"
    exit 1
fi

echo "Starting loogle server on http://localhost:8088..."
cd "$LOOGLE_DIR"

# patch Syntax error in server.py:
sed -i 's/except _:/except:/g' server.py

exec python server.py
