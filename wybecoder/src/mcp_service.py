# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import asyncio
import threading
import atexit
from logging import getLogger
from typing import Any, TypeVar, Callable, Coroutine
from concurrent.futures import Future
from asyncio import Queue

from src.mcp_client import LeanLspMcpClient

logger = getLogger()

T = TypeVar("T")

CoroutineFactory = Callable[[], Coroutine[Any, Any, T]]
WorkItem = tuple[CoroutineFactory[T] | None, Future[T]]


class _SyncMcpClient:
    """
    Internal class for handling an asyncio event loop,
    its hosting thread and an asyncio queue for providing
    a sync interface to async LeanLspMcpClient.

    Do not use directly, use the module level public interface.
    """

    def __init__(self):
        self._client: LeanLspMcpClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._work_queue: Queue[WorkItem] | None = None
        self._loop_start_event = threading.Event()

    def _start_loop_thread(self):
        """Target function for the background thread."""
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._work_queue = asyncio.Queue()
            self._loop.create_task(self._async_worker())
            self._loop.run_forever()
        finally:
            if self._loop:
                self._loop.close()
            self._loop = None
            self._work_queue = None

    async def _async_worker(self):
        """The single, persistent task that runs on the event loop."""
        client = LeanLspMcpClient()
        try:
            async with client:
                self._client = client  # Set *after* __aenter__ succeeds
                self._loop_start_event.set()  # Signal main thread

                while True:
                    coro_factory, result_future = await self._work_queue.get()

                    if coro_factory is None:  # Shutdown signal
                        result_future.set_result(None)
                        self._work_queue.task_done()
                        break

                    try:
                        result = await coro_factory()
                        result_future.set_result(result)
                    except Exception as e:
                        result_future.set_exception(e)
                    finally:
                        self._work_queue.task_done()
        except Exception as e:
            logger.error(f"Critical error in async worker: {e}")
            if not self._loop_start_event.is_set():
                self._loop_start_event.set()
        finally:
            self._client = None
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)

    def _submit_work(self, coro_factory: CoroutineFactory[T]) -> T:
        """Submits work to the async thread and blocks for a result."""
        if not self._loop or not self._loop.is_running() or not self._work_queue:
            raise RuntimeError("Event loop is not running. Client is not initialized.")

        result_future: Future[T] = Future()
        work_item: WorkItem = (coro_factory, result_future)
        self._loop.call_soon_threadsafe(self._work_queue.put_nowait, work_item)
        return result_future.result()

    def start(self):
        """Starts the background thread and waits for it to be ready."""
        if self._thread is not None:
            return

        self._loop_start_event.clear()
        self._thread = threading.Thread(
            target=self._start_loop_thread, daemon=True, name="MCPClientLoop"
        )
        self._thread.start()
        self._loop_start_event.wait()

        if self._client is None:
            self._thread.join()
            self._thread = None
            raise RuntimeError("Failed to initialize MCP client in background thread.")

        logger.info("MCP service initialized.")

    def stop(self):
        """Signals the background thread to shut down and waits for it."""
        if self._thread is None or self._loop is None or self._work_queue is None:
            return

        logger.info("Shutting down MCP service...")
        try:
            shutdown_future: Future[None] = Future()
            self._loop.call_soon_threadsafe(
                self._work_queue.put_nowait, (None, shutdown_future)
            )
            shutdown_future.result()
        except Exception as e:
            logger.error(f"Error during MCP service shutdown signal: {e}")
        finally:
            self._thread.join()
            self._thread = None
            self._loop = None
            self._client = None
            logger.info("MCP service shut down complete.")

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("Client is not running or has been shut down.")
        return self._submit_work(lambda: self._client.call_tool(tool_name, arguments))

    def list_tools(self, filter_names: list[str] | None = None) -> list[dict[str, Any]]:
        if self._client is None:
            raise RuntimeError("Client is not running or has been shut down.")
        return self._submit_work(lambda: self._client.list_tools(filter_names))


_GLOBAL_CLIENT: _SyncMcpClient | None = None


def initialize():
    """
    Initializes the MCP service.

    Starts the background event loop and registers the
    shutdown function to be called on program exit.
    """
    global _GLOBAL_CLIENT
    if _GLOBAL_CLIENT is not None:
        return

    _GLOBAL_CLIENT = _SyncMcpClient()
    try:
        _GLOBAL_CLIENT.start()
        atexit.register(shutdown)
    except Exception:
        _GLOBAL_CLIENT = None
        raise


def shutdown():
    """
    Shuts down the MCP service.
    Called automatically at exit by atexit.
    """
    global _GLOBAL_CLIENT
    if _GLOBAL_CLIENT is not None:
        _GLOBAL_CLIENT.stop()
        _GLOBAL_CLIENT = None


def call_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Call an MCP tool with the given arguments.

    Args:
        tool_name: Name of the tool to call
        arguments: Dictionary of arguments for the tool

    Returns:
        dict: The result from the tool execution
    """
    assert _GLOBAL_CLIENT is not None, (
        "MCP service not initialized, call initialize() first."
    )
    return _GLOBAL_CLIENT.call_tool(tool_name, arguments)


def list_tools(filter_names: list[str] | None = None) -> list[dict[str, Any]]:
    """
    List all available MCP tools.

    Args:
        filter_names: Optional list of tool names to include. If None, returns all tools.

    Returns:
        List of tool definitions compatible with Gemini function calling
    """
    assert _GLOBAL_CLIENT is not None, (
        "MCP service not initialized, call initialize() first."
    )
    return _GLOBAL_CLIENT.list_tools(filter_names)
