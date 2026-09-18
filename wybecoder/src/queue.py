# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import pickle
import queue
import signal
import threading
import time
from collections import deque
from logging import getLogger
from multiprocessing import Process
from queue import Queue
from typing import Any, Protocol

from src.utils import initialize_logger, get_master_port, get_master_addr

import zmq

logger = getLogger(__name__)


EXPIRED = b"__EXPIRED__"


class InterProcessQueue(Protocol):
    """Defines the common interface for all queue implementations."""

    def put(self, x: Any) -> None: ...
    def get(self, block: bool = True, timeout: float | None = None) -> Any: ...
    def qsize(self) -> int: ...
    def empty(self) -> bool: ...
    def close(self) -> None: ...


class ZmqQueueServer:
    """
    Server process for a one-to-one (REQ/ROUTER) queue.
    """

    def __init__(self, host: str = "localhost", port: int = 5555) -> None:
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.ROUTER)
        self.socket.bind(f"tcp://{host}:{port}")
        self.queue: deque = deque()
        self.pending_gets: deque = deque()
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Signals the server to stop its main loop and shut down."""
        self._stop_event.set()

    def run(self) -> None:
        """Runs the server's main event loop until stop() is called."""
        try:
            while not self._stop_event.is_set():
                if self.socket.poll(100):
                    client_id, empty, message = self.socket.recv_multipart()
                    command, data = pickle.loads(message)

                    if command == "PUT":
                        self.socket.send_multipart([client_id, b"", pickle.dumps("OK")])
                        self.queue.append(data)
                    elif command == "GET":
                        expiry_time = data
                        self.pending_gets.append((client_id, expiry_time))
                    elif command == "QSIZE":
                        self.socket.send_multipart(
                            [client_id, b"", pickle.dumps(len(self.queue))]
                        )

                # Purge timed-out GET requests
                now = time.monotonic()
                # Iterate safely while modifying the deque
                for _ in range(len(self.pending_gets)):
                    if not self.pending_gets:
                        break
                    client_id, expiry_time = self.pending_gets.popleft()
                    if expiry_time is not None and now > expiry_time:
                        self.socket.send_multipart([client_id, b"", EXPIRED])
                    else:
                        self.pending_gets.append((client_id, expiry_time))

                # Fulfill pending GET requests if items are in the queue
                while self.pending_gets and self.queue:
                    data = self.queue.popleft()
                    pending_client_id, _ = self.pending_gets.popleft()
                    self.socket.send_multipart(
                        [pending_client_id, b"", pickle.dumps(data)]
                    )
        finally:
            self.close()

    def close(self) -> None:
        """Closes the socket and terminates the ZMQ context."""
        # Set linger to 0 to discard pending messages immediately on close
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.close()
        self.context.term()


def _zmq_server_target(h: str, p: int):
    initialize_logger()
    server = ZmqQueueServer(h, p)

    def handle_sigterm(signum, frame):
        server.stop()

    signal.signal(signal.SIGTERM, handle_sigterm)
    server.run()


class ZmqQueue(InterProcessQueue):
    """
    A point-to-point inter-process queue using ZeroMQ.

    Args:
        is_server: If True, this instance will fork a background server process.
        host: The hostname for the server to bind to or the client to connect to.
        port: The port to use.

    If host or port is None, set up via Slurm environment.
    """

    def __init__(
        self, is_server: bool, host: str | None = None, port: int | None = None
    ) -> None:
        self.is_server = is_server
        self.host = host or get_master_addr()
        self.port = port or get_master_port()
        self.server_process: Process | None = None

        if is_server:
            self.server_process = Process(
                target=_zmq_server_target, args=(self.host, self.port)
            )
            self.server_process.start()
            logger.info(
                f"ZmqQueueServer process started on {self.host}:{self.port}, PID {self.server_process.pid}"
            )

        self.context = zmq.Context()
        # thread-local storage for ZMQ sockets which have to be closed by the creating thread
        self._thread_local = threading.local()

    def _get_socket(self) -> zmq.Socket:
        if not hasattr(self._thread_local, "socket"):
            sock = self.context.socket(zmq.REQ)
            sock.setsockopt(zmq.LINGER, 0)
            sock.connect(f"tcp://{self.host}:{self.port}")
            self._thread_local.socket = sock
        return self._thread_local.socket

    @property
    def socket(self) -> zmq.Socket:
        return self._get_socket()

    def close_thread(self) -> None:
        """
        Must be called by each worker thread that used this queue,
        before the thread exits (and before ZmqQueue.close()).
        """
        if hasattr(self._thread_local, "socket"):
            sock = self._thread_local.socket
            sock.setsockopt(zmq.LINGER, 0)
            sock.close()
            del self._thread_local.socket

    def _reset_socket(self) -> None:
        # reset is a thread-local operation, so close it right here
        self.close_thread()

    def put(self, x: Any) -> None:
        self.socket.send(pickle.dumps(("PUT", x)))
        response = pickle.loads(self.socket.recv())
        assert response == "OK"

    def get(self, block: bool = True, timeout: float | None = None) -> Any:
        """
        Retrieves an object from the queue. This implementation is resilient to
        both client-side and server-side timeouts.
        """
        timeout = 0.0 if not block else timeout
        expiry_time = time.monotonic() + timeout if timeout is not None else None

        current_socket = self.socket
        current_socket.send(pickle.dumps(("GET", expiry_time)))
        if timeout is not None:
            if not current_socket.poll(int(timeout * 1000)):
                # The client gave up waiting, breaking the send-recv cycle.
                # The socket is now in a broken state and MUST be reset.
                self._reset_socket()
                raise queue.Empty

        # If we get here, the poll succeeded or it was a fully blocking call.
        # A reply is guaranteed to be ready.
        data = current_socket.recv()
        if data == EXPIRED:
            # The server timed out and replied with None.
            # The client successfully received it, completing the send-recv cycle.
            # The socket is healthy and does NOT need a reset.
            raise queue.Empty

        return pickle.loads(data)

    def qsize(self) -> int:
        self.socket.send(pickle.dumps(("QSIZE", None)))
        return pickle.loads(self.socket.recv())

    def close(self) -> None:
        """
        Close this queue instance.
        Shutdown contract:
        - This class creates one ZMQ REQ socket per thread (stored in thread-local storage).
        ZMQ sockets must be closed by the thread that created/used them.
        - Therefore, every thread that used this queue MUST call `close_thread()` before
        it exits (typically in a `finally:` block in the worker).
        - Only after all such threads have exited (and have been joined) is it safe to call
        `close()`, which terminates the underlying ZMQ context (and, if `is_server=True`,
        stops the server process).
        """
        if self.is_server and self.server_process and self.server_process.is_alive():
            logger.info(
                f"Sending SIGTERM to ZmqQueueServer process {self.server_process.pid}."
            )
            self.server_process.terminate()
            self.server_process.join(timeout=5)
            if self.server_process.is_alive():
                logger.warning(
                    f"Server process {self.server_process.pid} did not terminate gracefully. Killing."
                )
                self.server_process.kill()
                self.server_process.join()
            logger.info(f"ZmqQueueServer process {self.server_process.pid} terminated.")

        # By the time close() is called, all worker threads should have
        # terminated, and their thread-local sockets should have been closed.
        # It's now safe to terminate the context.
        if not self.context.closed:
            logger.info("Terminating ZMQ context.")
            self.context.term()
        logger.info("ZmqQueue closed.")

    def empty(self) -> bool:
        return self.qsize() == 0


class ZmqBarrier:
    def __init__(
        self, world_size: int, is_server: bool, arrival_port: int, release_port: int
    ):
        """
        Barrier made from two ZmqQueues.
        """
        self.world_size = world_size
        self.is_server = is_server
        self.arrive_q = ZmqQueue(is_server=is_server, port=arrival_port)
        self.release_q = ZmqQueue(is_server=is_server, port=release_port)

    def wait(self):
        # 1) announce arrival
        self.arrive_q.put(1)

        if self.is_server:
            # 2) collect arrivals from all N workers
            for _ in range(self.world_size):
                self.arrive_q.get()

            # 3) release all N workers
            for _ in range(self.world_size):
                self.release_q.put(1)

        # 4) wait for release
        self.release_q.get()

    def close(self):
        self.arrive_q.close()
        self.release_q.close()


class ZmqMulticastServer:
    """Server process for a one-to-many (ROUTER/DEALER) queue."""

    def __init__(
        self, n_subscribers: int, host: str = "localhost", port: int = 5555
    ) -> None:
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.ROUTER)
        self.socket.bind(f"tcp://{host}:{port}")
        self.registered: list[bytes] = []
        self.n_subscribers = n_subscribers
        self.buffer: deque = deque()

    def publish(self, data: Any) -> None:
        payload = pickle.dumps(data)
        for subscriber in self.registered:
            self.socket.send_multipart([subscriber, b"", payload])

    def run(self) -> None:
        try:
            while True:
                client_id, _, message = self.socket.recv_multipart()
                command, data = pickle.loads(message)

                if command == "REGISTER":
                    self.socket.send_multipart([client_id, b"", pickle.dumps("OK")])
                    if client_id not in self.registered:
                        self.registered.append(client_id)
                        logger.info(
                            f"REGISTER: {len(self.registered)}/{self.n_subscribers} registered"
                        )
                    if len(self.registered) == self.n_subscribers:
                        logger.info(
                            f"All subscribers registered, sending {len(self.buffer)} buffered items"
                        )
                        while self.buffer:
                            self.publish(self.buffer.popleft())
                elif command == "PUT":
                    self.socket.send_multipart([client_id, b"", pickle.dumps("OK")])
                    if len(self.registered) < self.n_subscribers:
                        self.buffer.append(data)
                    else:
                        self.publish(data)
                elif command == "QSIZE":
                    self.socket.send_multipart(
                        [client_id, b"", pickle.dumps(len(self.buffer))]
                    )
        finally:
            self.close()

    def close(self) -> None:
        self.socket.close()
        self.context.term()


class ZmqMulticastQueue(InterProcessQueue):
    """
    A one-to-many "multicast" queue. Items put by a producer are received by all subscribers.
    Each subscriber maintains its own local queue.

    Args:
        is_server: If True, this instance will fork a background server process.
        is_subscriber: If True, this instance will listen for messages.
        n_subscribers: The total number of subscribers the server should wait for.
        host: The hostname for the server to bind to or the client to connect to.
        port: The port to use.

    If host or port is None, set up via Slurm environment.
    """

    def __init__(
        self,
        is_server: bool,
        is_subscriber: bool,
        n_subscribers: int,
        host: str = "localhost",
        port: int | None = None,
    ) -> None:
        self.is_server = is_server
        self.is_subscriber = is_subscriber
        self.host = host or get_master_addr()
        self.port = port or get_master_port()

        if is_server:

            def server_target(n_sub: int, h: str, p: int):
                initialize_logger()
                server = ZmqMulticastServer(n_sub, h, p)

                def handle_sigterm(signum, frame):
                    server.close()

                signal.signal(signal.SIGTERM, handle_sigterm)
                server.run()

            self.server_process = Process(
                target=server_target, args=(n_subscribers, self.host, self.port)
            )
            self.server_process.start()
            logger.info(
                f"ZmqMulticastServer process started on PID {self.server_process.pid}"
            )

        self.context = zmq.Context()
        self.put_sockets: dict[int, zmq.Socket] = {}

        if is_subscriber:
            self.queue: Queue = Queue()
            self.sub_socket = self.context.socket(zmq.DEALER)
            self.stop_event = threading.Event()
            self.listen_thread = threading.Thread(target=self._listen, daemon=True)
            self.listen_thread.start()

    @property
    def put_socket(self) -> zmq.Socket:
        ident = threading.get_ident()
        if ident not in self.put_sockets:
            socket = self.context.socket(zmq.REQ)
            socket.connect(f"tcp://{self.host}:{self.port}")
            self.put_sockets[ident] = socket
        return self.put_sockets[ident]

    def _listen(self) -> None:
        self.sub_socket.connect(f"tcp://{self.host}:{self.port}")
        self.sub_socket.send_multipart([b"", pickle.dumps(("REGISTER", None))])
        _, response = self.sub_socket.recv_multipart()
        assert pickle.loads(response) == "OK", "Registration failed"
        logger.info(
            f"ZmqMulticastQueue subscriber connected to {self.host}:{self.port}"
        )

        poller = zmq.Poller()
        poller.register(self.sub_socket, zmq.POLLIN)
        while not self.stop_event.is_set():
            events = dict(poller.poll(100))  # Poll with timeout to check stop_event
            if self.sub_socket in events:
                _, message = self.sub_socket.recv_multipart()
                data = pickle.loads(message)
                self.queue.put(data)

    def put(self, x: Any) -> None:
        self.put_socket.send(pickle.dumps(("PUT", x)))
        response = pickle.loads(self.put_socket.recv())
        assert response == "OK"

    def get(self, block: bool = True, timeout: float | None = None) -> Any:
        if not self.is_subscriber:
            raise RuntimeError("Cannot get from a non-subscriber queue.")
        return self.queue.get(block=block, timeout=timeout)

    def qsize(self) -> int:
        self.put_socket.send(pickle.dumps(("QSIZE", None)))
        buffer_len = pickle.loads(self.put_socket.recv())
        local_len = self.queue.qsize() if self.is_subscriber else 0
        return buffer_len + local_len

    def close(self) -> None:
        if self.is_subscriber:
            self.stop_event.set()
            self.listen_thread.join(timeout=2)
            self.sub_socket.close()

        for s in self.put_sockets.values():
            s.close()

        self.context.term()

        if self.is_server and self.server_process.is_alive():
            logger.info(
                f"Sending SIGTERM to ZmqMulticastServer process {self.server_process.pid}."
            )
            self.server_process.terminate()
            self.server_process.join(timeout=5)
            logger.info(
                f"ZmqMulticastServer process {self.server_process.pid} terminated."
            )

    def empty(self) -> bool:
        return self.qsize() == 0
