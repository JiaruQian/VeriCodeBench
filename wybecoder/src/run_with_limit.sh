#!/bin/bash
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

# A robust script to set a virtual memory limit and execute a command
# in a new process group. This allows a calling process to reliably
# terminate the command and all of its descendants.

# Exit immediately if a command exits with a non-zero status.
set -e

# Check if at least two arguments are provided (limit and a command).
if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <mem_limit_mb> <command_to_run> [args...]"
  exit 1
fi

# The first argument is the memory limit in megabytes.
MEM_LIMIT_MB=$1

# Convert the memory limit from megabytes to kilobytes for ulimit.
MEM_LIMIT_KB=$((MEM_LIMIT_MB * 1024))

# Remove the first argument (the memory limit) from the list of arguments.
shift

# Set the maximum virtual memory size. This limit is inherited by all
# child processes launched from this script.
ulimit -v "$MEM_LIMIT_KB"

# Execute the command in a new session.
# 'setsid': Runs the command in a new process group, making it the group
#   leader. This allows a parent process to kill the entire tree by signaling
#   the group ID (which is the same as the command's PID).
# 'exec': Replaces the current shell process with the command, which is a
#   clean and efficient way to launch it without an extra shell layer.
# '"$@"': Passes all the remaining arguments (the command and its options)
#   to setsid.
exec setsid "$@"
