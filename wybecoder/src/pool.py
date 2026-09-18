# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import queue
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from logging import getLogger
import time
from typing import Any
from src.repl import LeanRepl as Env
from src.utils import initialize_logger
from typing import Callable

logger = getLogger()


class MockEnv:
    def run(self, data):
        return {}

    def close(self):
        pass


class ResourcePool:
    """
    Manages a pool of "Env" resources, processing execution requests from a queue.
    Envs are lazily initialized and replaced if they reach a max usage
    count or encounter an error.
    """

    # Private wrapper class
    class _ManagedEnv:
        """A wrapper that bundles an env instance with its metadata."""

        def __init__(self, env: Any, env_id: int):
            self.env = env
            self.id = env_id  # unique id
            self.uses = 0  # usage counter

        def run(self, data: Any) -> Any:
            self.uses += 1
            return self.env.run(data)

        def close(self) -> None:
            self.env.close()

    def __init__(self, capacity: int, max_usage: int, env_ctor: Callable = Env):
        """
        Initializes the EnvPool.

        Args:
            capacity: The maximum number of environments to manage.
            max_usage: The number of times an environment can be used before being replaced.
        """
        assert capacity > 0
        assert max_usage > 0
        self.env_ctor = env_ctor
        logger.info(f"EnvPool with capacity {capacity} and max_usage {max_usage}")
        self.capacity = capacity
        self.max_usage = max_usage
        self.running = False

        self.env_pool: queue.Queue = queue.Queue(maxsize=capacity)

        self.lock = threading.Lock()  # guards n_active and running_id
        self.n_active = 0
        self.running_id: int = 0

        self.request_queue: queue.Queue[tuple[Any, Future]] = queue.Queue()
        self.executor = ThreadPoolExecutor(
            max_workers=capacity, thread_name_prefix="EnvWorker"
        )
        self.dispatcher_thread = None

    def start(self):
        assert not self.running
        self.running = True
        self.dispatcher_thread = threading.Thread(target=self._dispatch, daemon=True)
        self.dispatcher_thread.start()
        logger.info("EnvPool: Dispatcher thread started.")

    def _new_env(self, env_id: int) -> None:
        try:
            env = self._ManagedEnv(self.env_ctor(), env_id)
            self.env_pool.put(env)
        except Exception as e:
            with self.lock:
                self.n_active -= 1
            logger.error(f"Failed to create Env {env_id}: {e}")

    def _dispatch(self):
        """
        Pulls requests from the queue and assigns them to an available environment.
        Creates new environments on-demand up to the pool's capacity.
        """
        while self.running:
            try:
                data, future = self.request_queue.get(timeout=1.0)
            except queue.Empty:
                # Timeout allows the loop to check self.running periodically
                continue

            start = time.monotonic()
            try:
                env = self.env_pool.get_nowait()
            except queue.Empty:
                # If the pool is empty, check if we can create a new one
                with self.lock:
                    if self.n_active < self.capacity:
                        # Reserve a slot and schedule environment creation
                        self.n_active += 1
                        self.executor.submit(self._new_env, self.running_id)
                        logger.info(
                            f"Scheduled creation for Env {self.running_id} (total active: {self.n_active}/{self.capacity})"
                        )
                        self.running_id += 1

                # Wait for any environment to become available (new or returned)
                env = self.env_pool.get()
            elapsed = time.monotonic() - start
            logger.info(f"Assigned Env {env.id} after waiting {elapsed:.2f}s")
            self.executor.submit(self._worker, env, data, future)

    def _worker(self, env: _ManagedEnv, data: Any, future: Future):
        """
        Executes the task using an env. Decides whether to return the env
        to the pool, or discard it if it's worn out or has errored.
        """
        should_replace = False
        try:
            result = env.run(data)
            future.set_result(result)
            if env.uses >= self.max_usage:
                logger.info(
                    f"Env {env.id} reached max usage ({env.uses}/{self.max_usage}). Replacing."
                )
                should_replace = True
        except Exception as e:
            logger.error(
                f"Exception in Env {env.id}, replacing it. Data: {data}",
                exc_info=e,
            )
            future.set_exception(e)
            should_replace = True
        finally:
            if should_replace:
                try:
                    env.close()
                except Exception as e:
                    logger.error(f"Error closing Env {env.id}: {e}")
                with self.lock:
                    self.n_active -= 1
            else:
                logger.info(f"Releasing Env {env.id}")
                self.env_pool.put(env)

    def submit(self, request_data: Any) -> Future:
        assert self.running
        future = Future()
        self.request_queue.put((request_data, future))
        return future

    def run(self, request_data: Any) -> Any:
        future = self.submit(request_data)
        return future.result()

    def shutdown(self, wait: bool = True):
        assert self.running
        self.running = False
        if self.dispatcher_thread:
            self.dispatcher_thread.join()
        logger.info("EnvPool: Dispatcher thread stopped.")

        logger.info("EnvPool: Closing all remaining environments in the pool...")
        while not self.env_pool.empty():
            try:
                env = self.env_pool.get_nowait()
                try:
                    env.close()
                    logger.info(f"Closed Env {env.id}")
                except Exception as e:
                    logger.error(f"Error closing Env {env.id}: {e}")
            except queue.Empty:
                break

        logger.info("EnvPool: Shutting down executor (waiting for active tasks)...")
        self.executor.shutdown(wait=wait)
        logger.info("EnvPool: Shutdown complete.")


if __name__ == "__main__":
    initialize_logger()

    pool = ResourcePool(capacity=2, max_usage=2, env_cls=MockEnv)
    pool.start()
    with open("data/example.lean") as f:
        code = f.read()

    def run(data):
        return pool.run(data)

    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = [executor.submit(run, i) for i in range(7)]
        for f in futures:
            f.result()

    pool.shutdown()
