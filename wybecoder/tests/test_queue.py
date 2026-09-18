# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from logging import getLogger
import os
import threading

from src.queue import ZmqQueue
from src.utils import initialize_logger


RANK = int(os.environ.get("RANK", 0))
WORLD_SIZE = int(os.environ.get("WORLD_SIZE", 1))

HOST = "127.0.0.1"
PORT = 55555
NUM_ITEMS = 10000
DONE = "DONE"

logger = getLogger()


def feed(q: ZmqQueue) -> None:
    logger.info(f"Producer sending {NUM_ITEMS} items...")
    for i in range(NUM_ITEMS):
        q.put(i)

    logger.info(f"Producer sending {WORLD_SIZE} DONE sentinels...")
    for _ in range(WORLD_SIZE):
        q.put(DONE)
    logger.info("Producer finished sending.")


def main():
    q = ZmqQueue(is_server=RANK == 0, host=HOST, port=PORT)

    if RANK == 0:
        threading.Thread(target=feed, args=(q,)).start()

    n_recv = 0
    while True:
        item = q.get()
        logger.info(f"Received {item}")
        if item == DONE:
            logger.info("Received DONE sentinel. Shutting down worker.")
            break
        n_recv += 1

    logger.info(f"Worker received a total of {n_recv} items.")

    q.close()


if __name__ == "__main__":
    initialize_logger()
    main()
