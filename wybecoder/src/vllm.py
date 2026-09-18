# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
Distributed vLLM server launcher for SLURM environments.

Adapted from the reference implementation to work with SLURM-based distributed systems.
Supports both single-GPU and multi-GPU tensor parallelism.
"""

import atexit
import json
import logging
import socket
import subprocess
import time
from pathlib import Path

from src.args import RunArgs
from src.utils import get_local_rank, get_node_id

logger = logging.getLogger(__name__)


class VLLMServer:
    """
    vLLM server with optional tensor-parallel support for SLURM environments.

    This class handles:
    - Automatic port allocation
    - Server startup and health checking
    - URL sharing across SLURM tasks via shared file
    - Graceful shutdown

    Example:
        >>> server = VLLMServer(
        ...     model="/path/to/model",
        ...     dump_dir="runs/dumps/my_run",
        ...     host="0.0.0.0",
        ...     tensor_parallel_size=2,
        ... )
        >>> server.start()
        >>> # Use server.base_url for API calls
        >>> server.stop()
    """

    def __init__(
        self,
        model: str,
        dump_dir: str,
        host: str = "0.0.0.0",
        timeout: float = 300.0,
        python_interpreter: str = "python",
        extra_engine_args: dict[str, str | int | float | bool | None] | None = None,
        log_dir: str | None = None,
        tensor_parallel_size: int = 1,
    ):
        """
        Initialize vLLM server configuration.

        Args:
            model: Model name or path to serve
            host: Host to bind the server to (0.0.0.0 for all interfaces)
            timeout: Timeout in seconds to wait for server startup
            python_interpreter: Python interpreter to use for launching server
            extra_engine_args: Additional CLI arguments for vLLM
            log_dir: Directory to save server logs
            tensor_parallel_size: Number of GPUs for tensor parallelism
            dump_dir: Shared directory for coordination files
            world_size: Total number of SLURM tasks
            local_rank: Local rank within the node (if None, auto-detected)
            node_id: Node ID in multi-node job (if None, auto-detected)
        """
        self.model = model
        self.host = host
        self.timeout = timeout
        self.python_interpreter = python_interpreter
        self.extra_engine_args = extra_engine_args or {}
        self.log_dir = log_dir
        self.tensor_parallel_size = tensor_parallel_size
        self.dump_dir = dump_dir
        self.local_rank = get_local_rank()
        self.node_id = get_node_id()

        self.base_url: str | None = None
        self._server_proc: subprocess.Popen | None = None
        self._port: int | None = None

    def __enter__(self):
        """Context manager entry - starts the server."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Context manager exit - stops the server."""
        if exc_type is None:
            self.stop(wait=True)
        else:
            logger.error(f"Error during vLLM server execution: {exc_value}")
            self.stop(wait=False)

    def start(self) -> None:
        """
        Start the vLLM server (local rank 0 only on each node) and share URL with all ranks.
        """
        assert self._server_proc is None, "Server is already running"

        # Only the local rank 0 on each node starts the server process
        if self.local_rank == 0:
            self._start_server_process()

        # All ranks wait for server URL to be ready
        self._load_server_url()

    def _start_server_process(self) -> None:
        """Start the vLLM server process (local rank 0 only)."""
        port = self._find_free_port()
        self._port = port

        # Prepare log files
        if self.log_dir:
            log_path = Path(self.log_dir)
            log_path.mkdir(exist_ok=True, parents=True)
            logger.info(f"vLLM server logs will be written to {self.log_dir}")
            stdout_file = open(log_path / f"vllm_node_{self.node_id}.out", "w")
            stderr_file = open(log_path / f"vllm_node_{self.node_id}.err", "w")
        else:
            stdout_file = None
            stderr_file = None

        # Build command
        cmd = [
            self.python_interpreter,
            "-m",
            "vllm.entrypoints.openai.api_server",
            f"--model={self.model}",
            f"--host={self.host}",
            f"--port={port}",
        ]

        # Add tensor parallelism if needed
        if self.tensor_parallel_size > 1:
            cmd.append(f"--tensor-parallel-size={self.tensor_parallel_size}")

        # Add extra engine arguments
        for k, v in self.extra_engine_args.items():
            if v is None:
                cmd.append(f"--{k}")
            else:
                cmd.append(f"--{k}={v}")

        logger.info(f"Launching vLLM server: {' '.join(cmd)}")

        # Launch server
        self._server_proc = subprocess.Popen(
            cmd,
            stdout=stdout_file,
            stderr=stderr_file,
        )

        if stdout_file and stderr_file:
            stdout_file.close()
            stderr_file.close()

        # Wait for server to be ready
        self._wait_for_server(port)

        # Save server URL to shared file
        self.base_url = f"http://{self.host}:{port}/v1"
        self._save_server_url(self.base_url)

        logger.info(f"vLLM server started successfully at {self.base_url}")

    def _find_free_port(self) -> int:
        """Find a free port on the host."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((self.host if self.host != "0.0.0.0" else "localhost", 0))
        port = sock.getsockname()[1]
        sock.close()
        return port

    def _wait_for_server(self, port: int) -> None:
        """Wait for server to be ready to accept connections."""
        deadline = time.time() + self.timeout
        logger.info(f"Waiting for vLLM server to start on port {port}...")

        while time.time() < deadline:
            try:
                # Try to connect to the port
                with socket.create_connection(("localhost", port), timeout=1):
                    logger.info("vLLM server is ready!")
                    return
            except (OSError, ConnectionRefusedError):
                time.sleep(1)

        # Timeout reached
        logger.error(f"vLLM server failed to start within {self.timeout}s")
        self.stop(wait=False)
        raise RuntimeError(
            f"vLLM server failed to start within {self.timeout}s on port {port}"
        )

    def _save_server_url(self, url: str) -> None:
        """Save server URL to per-node shared file for other ranks to read."""
        url_file = Path(self.dump_dir) / f"vllm_server_url_node_{self.node_id}.json"
        url_file.parent.mkdir(exist_ok=True, parents=True)

        data = {
            "base_url": url,
            "node_id": self.node_id,
            "local_rank": self.local_rank,
            "timestamp": time.time(),
        }

        with open(url_file, "w") as f:
            json.dump(data, f)

        logger.info(f"Saved vLLM server URL for node {self.node_id} to {url_file}")

    def _load_server_url(self) -> None:
        """Load server URL from per-node shared file."""
        url_file = Path(self.dump_dir) / f"vllm_server_url_node_{self.node_id}.json"

        # Wait for file to exist
        deadline = time.time() + self.timeout
        while not url_file.exists():
            if time.time() > deadline:
                raise RuntimeError(
                    f"Server URL file for node {self.node_id} not found after {self.timeout}s: {url_file}"
                )
            time.sleep(0.5)

        # Read URL
        with open(url_file, "r") as f:
            data = json.load(f)

        self.base_url = data["base_url"]

        # Convert 0.0.0.0 to localhost for same-node communication
        # Since we're using per-node servers, ranks on the same node should use localhost
        if "0.0.0.0" in self.base_url:
            self.base_url = self.base_url.replace("0.0.0.0", "localhost")

        logger.info(f"Loaded vLLM server URL for node {self.node_id}: {self.base_url}")

    def stop(self, wait: bool = True) -> None:
        """
        Stop the vLLM server.

        Args:
            wait: Whether to wait for graceful shutdown
        """
        if self.local_rank == 0 and self._server_proc is not None:
            if self._server_proc.poll() is None:  # Process still running
                logger.info(f"Stopping vLLM server on node {self.node_id}...")
                self._server_proc.terminate()

                if wait:
                    try:
                        self._server_proc.wait(timeout=5)
                        logger.info("vLLM server stopped gracefully")
                    except subprocess.TimeoutExpired:
                        logger.warning("vLLM server did not stop, killing...")
                        self._server_proc.kill()
                        self._server_proc.wait()
                        logger.info("vLLM server killed")

                self._server_proc = None


_VLLM_SERVER: VLLMServer | None = None
_VLLM_BASE_URL: str | None = None
_VLLM_MODEL_PATH: str | None = None


def init_vllm(args: RunArgs) -> None:
    global _VLLM_SERVER, _VLLM_BASE_URL, _VLLM_MODEL_PATH
    _VLLM_MODEL_PATH = args.vllm_model_path

    if args.vllm_base_url is not None:
        logger.info(f"Using VLLM server at {args.vllm_base_url}")
        _VLLM_BASE_URL = args.vllm_base_url
        return

    if _VLLM_SERVER is not None:
        return  # Already initialized

    _VLLM_SERVER = VLLMServer(
        model=args.vllm_model_path,
        dump_dir=args.dump_dir,
        tensor_parallel_size=args.vllm_tensor_parallel_size,
        extra_engine_args=args.vllm_extra_args,
        timeout=args.vllm_server_timeout,
        log_dir=str(Path(args.dump_dir) / "vllm_logs"),
    )
    _VLLM_SERVER.start()
    _VLLM_BASE_URL = _VLLM_SERVER.base_url

    atexit.register(_VLLM_SERVER.stop, wait=True)


def get_vllm_base_url() -> str:
    global _VLLM_BASE_URL
    if _VLLM_BASE_URL is None:
        raise RuntimeError("vLLM not configured")
    return _VLLM_BASE_URL


def get_vllm_model_path() -> str:
    """Get the model path served by vLLM."""
    global _VLLM_MODEL_PATH
    if _VLLM_MODEL_PATH is None:
        raise RuntimeError("vLLM not configured")
    return _VLLM_MODEL_PATH
