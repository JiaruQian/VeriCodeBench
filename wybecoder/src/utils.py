# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from collections import defaultdict
import difflib
import json
import logging
import math
import os
import random
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextlib import AbstractContextManager, contextmanager, suppress
from datetime import timedelta
from functools import lru_cache, wraps
from logging import getLogger
from pathlib import Path
from time import sleep
from typing import Any, Generic, ParamSpec, TypeVar

import google
import numpy as np
import psutil
import resource
import re

logger = getLogger()


T = TypeVar("T")


@lru_cache
def get_is_torch_run() -> bool:
    return os.environ.get("LOCAL_RANK") is not None


@lru_cache
def get_is_slurm_job() -> bool:
    return (
        "SLURM_JOB_ID" in os.environ
        and "SLURM_PROCID" in os.environ
        and not get_is_torch_run()
    )


@lru_cache
def get_global_rank() -> int:
    if get_is_torch_run():
        return int(os.environ["RANK"])
    if get_is_slurm_job():
        return int(os.environ["SLURM_PROCID"])
    return 0


@lru_cache
def get_local_rank() -> int:
    if get_is_torch_run():
        return int(os.environ["LOCAL_RANK"])
    if get_is_slurm_job():
        return int(os.environ["SLURM_LOCALID"])
    return 0


@lru_cache
def get_node_id() -> int:
    """Get the node ID in a multi-node job."""
    if get_is_slurm_job():
        return int(os.environ.get("SLURM_NODEID", 0))
    return 0


@lru_cache
def get_world_size() -> int:
    if get_is_torch_run():
        return int(os.environ["WORLD_SIZE"])
    if get_is_slurm_job():
        return int(os.environ["SLURM_NTASKS"])
    return 1


@lru_cache
def get_master_port() -> int:
    if get_is_torch_run():
        return int(os.environ["MASTER_PORT"])
    MIN_MASTER_PORT, MAX_MASTER_PORT = (20000, 60000)
    rng = random.Random(int(os.environ.get("SLURM_JOB_ID", -1)))
    return rng.randint(MIN_MASTER_PORT, MAX_MASTER_PORT)


@lru_cache
def get_master_addr() -> str:
    if get_is_torch_run():
        return os.environ["MASTER_ADDR"]
    if get_is_slurm_job():
        hostnames = subprocess.check_output(
            ["scontrol", "show", "hostnames", os.environ["SLURM_JOB_NODELIST"]],
        )
        return hostnames.split()[0].decode("utf-8")
    return "127.0.0.1"


class LogFormatter(logging.Formatter):
    """Custom logger for distributed jobs, displaying rank
    and preserving indent from the custom prefix format.
    """

    def __init__(self, display_name: bool = False) -> None:
        self.start_time = time.time()
        self.rank = get_global_rank()
        self.display_rank = not get_is_slurm_job()  # srun has --label
        self.display_name = display_name  # useful for finer debugging

    def format_time(self, record: logging.LogRecord) -> str:
        subsecond, seconds = math.modf(record.created)
        curr_date = (
            time.strftime("%y-%m-%d %H:%M:%S", time.localtime(seconds))
            + f".{int(subsecond * 1_000_000):06d}"
        )
        delta = timedelta(seconds=round(record.created - self.start_time))
        return f"{curr_date} - {delta}"

    def format_prefix(self, record: logging.LogRecord) -> str:
        fmt_time = self.format_time(record)
        prefix = ""
        if self.display_rank:
            prefix += f"{self.rank}: "
        prefix += f"{record.levelname:<7} {fmt_time} - "
        if self.display_name:
            prefix += f"{record.name} - "
        prefix += f"{record.filename}:{record.lineno} - "
        return prefix

    def format_message_with_indent(self, record: logging.LogRecord, indent: str) -> str:
        content = record.getMessage()
        content = content.replace("\n", "\n" + indent)
        # Exception handling as in the default formatter, albeit with indenting
        # according to our custom prefix

        # Cache the traceback text to avoid converting it multiple times
        # (it's constant anyway)
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            if content[-1:] != "\n":
                content = content + "\n" + indent
            content = content + indent.join(
                [line + "\n" for line in record.exc_text.splitlines()],
            )
            if content[-1:] == "\n":
                content = content[:-1]
        if record.stack_info:
            if content[-1:] != "\n":
                content = content + "\n" + indent
            stack_text = self.formatStack(record.stack_info)
            content = content + indent.join(
                [line + "\n" for line in stack_text.splitlines()],
            )
            if content[-1:] == "\n":
                content = content[:-1]

        return content

    def format(self, record: logging.LogRecord) -> str:
        prefix = self.format_prefix(record)
        indent = " " * len(prefix)
        content = self.format_message_with_indent(record, indent)
        return prefix + content


def set_root_log_level(log_level: str) -> None:
    logger = logging.getLogger()
    level: int | str = log_level.upper()
    with suppress(ValueError):
        level = int(log_level)
    try:
        logger.setLevel(level)
    except (TypeError, ValueError):
        logger.warning(
            f"Failed to set logging level to {log_level}, using default 'NOTSET'",
        )
        logger.setLevel(logging.NOTSET)


def initialize_logger(name: str | None = None, level: str = "NOTSET") -> None:
    """Setup logging.

    Args:
        name: The name of the logger to configure, by default the root logger.
        level: The logging level to use.
    """
    set_root_log_level(level)
    logger = logging.getLogger()
    log_formatter = LogFormatter(display_name=False)

    # silent fsspec and objectstore heavy logging
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("aiobotocore").setLevel(logging.WARNING)
    logging.getLogger("s3fs").setLevel(logging.WARNING)
    logging.getLogger("fsspec").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # logging.getLogger("httpx").setLevel(logging.WARNING)

    # stdout: everything
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.NOTSET)
    stdout_handler.setFormatter(log_formatter)

    # stderr: warnings / errors and above
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(log_formatter)

    # set stream handlers
    logger.handlers.clear()
    assert len(logger.handlers) == 0, logger.handlers
    logger.handlers.append(stdout_handler)
    logger.handlers.append(stderr_handler)


def add_logger_file_handler(log_file: str | Path) -> None:
    logger = logging.getLogger()
    if get_global_rank() == 0:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        # build file handler
        file_handler = logging.FileHandler(log_file, "a")
        file_handler.setLevel(logging.NOTSET)
        file_handler.setFormatter(LogFormatter())
        # update logger
        logger.handlers.append(file_handler)


@contextmanager
def log_timing(
    message: str,
    level: int = logging.INFO,
    clock: Callable[[], float] = time.monotonic,
    precision: int = 3,
) -> Iterator[None]:
    logger = logging.getLogger()
    logger.log(level, f"{message}: starting")
    t0 = clock()
    try:
        yield
    finally:
        t1 = clock()
        logger.log(level, f"{message}: completed in {t1 - t0:.{precision}f}s")


def log_time(func):
    """Decorator that logs when a function starts and ends with elapsed time."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(f"{func.__name__} started")
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            logger.info(f"{func.__name__} ended after {elapsed:.3f} seconds")

    return wrapper


class LoggedClosing(AbstractContextManager, Generic[T]):
    """Util to log when closing an object.
    It also log when an error is raised while closing
    Useful to debug jobs that hang when an error is raised
    """

    def __init__(self, thing: T, name: str) -> None:
        self.thing = thing
        self.name = name

    def __enter__(self) -> T:
        logging.info(f"Entering 'closing' context for {self.name}")
        return self.thing

    def __exit__(self, *args) -> None:
        try:
            self.close()
        except Exception:
            logging.exception(
                f"Caught error while closing {self.name}, aborting closing...",
            )
            raise

    def close(self) -> None:
        logging.info(f"Closing {self.name} ...")
        if isinstance(self.thing, dict):
            for t in self.thing.values():
                t.close()
        else:
            self.thing.close()
        logging.info(f"Closed {self.name}")


class ThreadGroup:
    """
    A context manager to start a group of threads and automatically
    join them all upon exiting the 'with' block.
    """

    def __init__(self):
        self._threads = []

    def go(self, target, name: str | None = None, *args, **kwargs):
        """
        Creates and starts a standard thread, adding it to the group.
        """
        name = name or target.__name__
        thread = threading.Thread(target=target, name=name, args=args, kwargs=kwargs)
        self._threads.append(thread)
        thread.start()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Wait for all threads to join.
        """
        for thread in self._threads:
            thread.join()


def get_load():
    """
    Retrieves the current CPU load and memory statistics.

    Returns:
        dict: A dictionary containing:
              - 'cpu_load' (float): The current CPU utilization percentage.
              - 'memory_percent' (float): The percentage of memory used.
              - 'memory_total_gb' (float): Total physical memory in gigabytes.
              - 'memory_available_gb' (float): Available memory in gigabytes.
              - 'memory_used_gb' (float): Used memory in gigabytes.
    """
    cpu_load = psutil.cpu_percent()
    memory_stats = psutil.virtual_memory()
    bytes_to_gb = 1024**3
    memory_total_gb = memory_stats.total / bytes_to_gb
    memory_available_gb = memory_stats.available / bytes_to_gb
    memory_used_gb = memory_stats.used / bytes_to_gb
    memory_percent = memory_stats.percent
    return {
        "cpu_load": cpu_load,
        "memory_percent": memory_percent,
        "memory_total_gb": memory_total_gb,
        "memory_available_gb": memory_available_gb,
        "memory_used_gb": memory_used_gb,
    }


def set_memory_limit(max_mem_mb: int):
    "Set the memory limit for current process."
    max_mem_bytes = max_mem_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (max_mem_bytes, max_mem_bytes))


def read_jsonl_or_jsonl_dir(path: str | Path) -> list[dict]:
    path = Path(path)
    if path.is_dir():
        jsonls = path.rglob("*.jsonl")
    else:
        jsonls = [path]
    data: list[dict] = []
    for fn in jsonls:
        with fn.open() as f:
            data.extend(json.loads(line) for line in f)
    return data


def render_diff(
    old_code: str,
    new_code: str,
    old_file_name: str | None = None,
    new_file_name: str | None = None,
    remove_header: bool = True,
) -> str:
    "Render a unified diff between old_code and new_code."
    if not old_code.endswith("\n"):
        old_code += "\n"
    if not new_code.endswith("\n"):
        new_code += "\n"

    old_lines = old_code.splitlines(keepends=True)
    new_lines = new_code.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=old_file_name or "<old>",
        tofile=new_file_name or "<new>",
        lineterm="",  # no extra newlines
    )
    if remove_header:
        # Keep only lines starting with ' ' (context), '+' or '-' (changes),
        # and drop the '---', '+++', and '@@' header/hunk lines
        filtered = [
            line
            for line in diff
            if line
            and not (
                line.startswith("---")
                or line.startswith("+++")
                or line.startswith("@@")
            )
        ]
    else:
        filtered = list(diff)
    return "".join(filtered)


def remove_multiline_comments(s: str) -> str:
    """
    Removes all Lean multiline comments (delimited by /- and -/) from the input string,
    handling nested comments correctly.
    """
    i = 0
    n = len(s)
    result = []
    nesting = 0
    while i < n:
        # Check for start of comment
        if s.startswith("/-", i):
            nesting += 1
            i += 2
            continue
        # Check for end of comment
        if s.startswith("-/", i) and nesting > 0:
            nesting -= 1
            i += 2
            continue
        # If not in a comment, output the character
        if nesting == 0:
            result.append(s[i])
        i += 1
    return "".join(result)


def remove_line_comments(s: str) -> str:
    """
    Removes all Lean line comments (starting with --) from the input string.
    """
    lines = s.splitlines()
    result = []
    for line in lines:
        # Find the position of '--' that marks the start of a line comment
        comment_start = line.find("--")
        if comment_start != -1:
            # Keep only the part before the comment
            result.append(line[:comment_start].rstrip())
        else:
            result.append(line)
    return "\n".join(result)


def remove_whitespace_only_lines(s: str) -> str:
    """
    Removes all lines that contain only whitespace from the input string.
    """
    lines = s.splitlines()
    result = [line for line in lines if line.strip() != ""]
    return "\n".join(result)


def normalize_newlines(text: str) -> str:
    "Replace multiple by single newlines."
    return re.sub(r"\n+", "\n", text)


def normalize_empty_lines(text: str) -> str:
    "Replace multiple whitespace lines by single empty line."
    return re.sub(r"(?:[ \t]*\n){2,}", "\n\n", text)


def normalize_whitespace(text: str) -> str:
    "Replace multiple spaces/tabs/newlines by single space."
    return re.sub(r"[ \t\n]+", " ", text)


def remove_imports(text: str) -> str:
    "Remove Lean import statements from the text."
    lines = text.splitlines(keepends=True)
    return "".join(line for line in lines if not line.startswith("import "))


def normalize_lean(text: str, hard: bool = True) -> str:
    "Normalize Lean code by removing comments, imports and extra whitespace-only lines."
    text = remove_multiline_comments(text)
    text = remove_line_comments(text)
    text = remove_imports(text)
    text = remove_whitespace_only_lines(text)
    text = normalize_newlines(text)
    if hard:
        text = normalize_whitespace(text)
    return text


def header_unmodified(code: str, header: str, stop_word: str = "do") -> bool:
    """
    Check whether the beginning of the file is identical to the given header,
    up to the last occurrence of `stop_word` in the header.

    Up to comments, whitespace and imports.
    """
    idx = header.rfind(stop_word)
    header_cut = header[:idx] if idx != -1 else header
    code_norm = normalize_lean(code.strip(), hard=True)
    header_cut_norm = normalize_lean(header_cut.strip(), hard=True)
    return code_norm.startswith(header_cut_norm)


def contains_normalized(code: str, snippet: str, stop_word: str | None = None) -> bool:
    if stop_word:
        idx = snippet.rfind(stop_word)
        snippet = snippet[:idx] if idx != -1 else snippet

    code_norm = normalize_whitespace(code.strip())
    snippet_norm = normalize_whitespace(snippet.strip())
    return snippet_norm in code_norm


def includes_guard_statements(code: str) -> bool:
    """Returns True if there are guard statements in `code`

    This function treats any line starting with optional whitespace followed by
    "#guard" as a guard statement.
    """
    if not code:
        return False
    code_norm = normalize_newlines(code.strip())
    if re.search(r"(?m)^[ \t]*#guard\b", code_norm):
        return True
    return False


def extract_method_name(loom_header: str) -> str:
    """Extract the *last* method name from loom_header."""
    # last in given loom_header is safe from reward hacking
    matches = re.findall(r"\bmethod\s+(\w+)", loom_header)
    if not matches:
        raise ValueError(
            f"Failed to extract method name from loom_header: {loom_header}"
        )
    return matches[-1]


def first_line_idx(code: str, pattern: str) -> int:
    """
    Given a text `code` and a regex pattern `pattern`, return the 1-based line index
    of the first occurrence of `pattern` in `code` using re.DOTALL.

    This can be used to check where a theorem or method is defined in the code.
    """
    match = re.search(pattern, code, re.DOTALL)
    if not match:
        raise ValueError(f"Failed to find pattern {pattern} in code:\n{code}")
    return code.count("\n", 0, match.start()) + 1


def raw_first_line_idx(code: str, sub: str) -> int:
    """
    Same as first_line_idx but with a substring instead of regex.
    """
    pattern = re.escape(sub)
    return first_line_idx(code, pattern)


def method_spec_line(code: str) -> int:
    """Compute the 1-based line number of the beginning of the method spec in code."""
    # first occurrence in model generated code is safe because we enforce that it starts with the loom_header
    method_name = extract_method_name(code)
    pattern = rf"\bmethod\s+{re.escape(method_name)}\b"
    return first_line_idx(code, pattern)


def pprint(dialog: list[dict[str, str]]):
    for msg in dialog:
        logger.info(f"{msg['role'].upper()}: {msg['content']}\n\n")


P = ParamSpec("P")
T = TypeVar("T")


def retry_on_resource_exhausted(func: Callable[P, T]) -> Callable[P, T]:
    """Retry function calls on ResourceExhausted errors."""

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        attempt = 1
        while True:
            try:
                return func(*args, **kwargs)
            except google.api_core.exceptions.ResourceExhausted as e:
                to_sleep_sec = 100 * random.random()
                error_msg = str(e)
                if error_msg.startswith("429 You exceeded your current quota"):
                    error_msg = "429 You exceeded your current quota"
                logger.warning(
                    f"Caught '{error_msg}', retrying with attempt {attempt} after {to_sleep_sec:.2f} s"
                )
                attempt += 1
                sleep(to_sleep_sec)

    return wrapper


def timeout_in_thread(seconds: float):
    """
    Run the wrapped function in an ad-hoc worker thread and enforce a hard timeout.
    - On success: shutdown(wait=True) to cleanly join the worker.
    - On timeout: shutdown(wait=False) so we don't block waiting for a hung thread.
      The stuck thread may remain running until process exit.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix=f"{func.__name__}-TimeoutWrapper"
            )
            future = executor.submit(func, *args, **kwargs)
            try:
                result = future.result(timeout=seconds)
                # Clean shutdown on success: join the worker
                executor.shutdown(wait=True)
                return result
            except FuturesTimeoutError:
                logger.warning(
                    f"Function {func.__name__} exceeded hard timeout of {seconds} s, "
                    "raising RuntimeError and letting the thread linger"
                )
                # Don't wait for the worker; don't block here
                executor.shutdown(wait=False)
                # The worker thread may still be running; we can't kill it in Python.
                raise RuntimeError("request timed out")

        return wrapper

    return decorator


def retry_on_transient_errors(max_attempts: int = 10, base_backoff: float = 0.5):
    """
    Decorator to retry function calls on transient errors (timeouts, temporary service issues)
    and when the response is None.

    Args:
        max_attempts: Maximum number of attempts
        base_backoff: Base backoff time in seconds
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            attempt = 0
            while attempt < max_attempts:
                try:
                    result = func(*args, **kwargs)
                    # Retry if result is None
                    if result is None or result == "":
                        attempt += 1
                        backoff = (
                            min(10, base_backoff * (2 * attempt)) + random.random()
                        )
                        logger.warning(
                            f"Received None response, retrying with attempt {attempt}/{max_attempts} after {backoff:.2f} s"
                        )
                        sleep(backoff)
                        continue
                    return result
                except Exception as e:
                    attempt += 1
                    # Check for common transient error types/messages
                    transient_errors = [
                        "system is currently experiencing high demand",
                        "internal server error",
                        "timeout",  # catches timeout_in_thread too
                        "timed out",
                        "temporarily unavailable",
                        "unavailable",
                        "rate limit",
                        "connection error",
                        "too many requests",
                        "resource has been exhausted",
                    ]
                    error_msg = str(e).lower()
                    is_transient = any(term in error_msg for term in transient_errors)

                    if not is_transient:
                        print(f"Non-transient error encountered: {e}")
                        raise RuntimeError(
                            f"Failed: non-transient error on attempt {attempt}/{max_attempts}"
                        ) from e
                    backoff = min(10, base_backoff * (2 * attempt)) + random.random()
                    logger.warning(
                        f"Caught transient error '{type(e).__name__}: {str(e)[:50]}...', retrying with attempt {attempt}/{max_attempts} after {backoff:.2f} s"
                    )
                    sleep(backoff)

            raise RuntimeError(f"Failed after {max_attempts} attempts")

        return wrapper

    return decorator


def extract_benchmark_blocks(text: str) -> dict[str, str]:
    # Matches: -- benchmark @start Name\n ...content... \n-- benchmark @end Name
    pattern = re.compile(
        r"-- benchmark @start\s+([^\n]+)\n(.*?)(?:\n-- benchmark @end \1)", re.DOTALL
    )
    blocks = {m.group(1).strip(): m.group(2).rstrip() for m in pattern.finditer(text)}
    return blocks


def clean_description(nl_block_text: str) -> str:
    # NL block usually contains a /- ... -/ block; extract inner if present
    if not nl_block_text:
        return ""
    m = re.search(r"/-(.*?)-/", nl_block_text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return nl_block_text.strip()


def extract_benchmark_content_for_tag(
    benchmark_blocks: dict[str, str], tag_name: str
) -> str:
    if tag_name in benchmark_blocks:
        return benchmark_blocks[tag_name]
    raise ValueError(f"Could not extract content for tag {tag_name}")


def incremental_dump_path(dump_dir: str | Path, thread_name: str) -> Path:
    rank = get_global_rank()
    dump_dir = Path(dump_dir)
    inc_dir = dump_dir / "incremental" / f"{rank}_{thread_name}"
    return inc_dir


def incremental_dump(inc_file: Path, data: dict) -> None:
    temp_file = inc_file.with_suffix(".tmp")
    with temp_file.open("w") as f:
        f.write(json.dumps(data) + "\n")
    temp_file.rename(inc_file)


def pass_at_k(n: int, c: int, k: int) -> float:
    """
    Unbiased pass@k estimator from Codex (https://arxiv.org/abs/2107.03374):
    $ E_{x_i \\sim p, i \\leq k}[ max x_i ] $
    estimated from n samples.
    :param n: total number of samples
    :param c: number of correct samples
    :param k: k in pass@$k$
    """
    k = min(n, k)
    if n - c < k:
        return 1.0 if c > 0 else 0.0
    return 1.0 - np.prod(1.0 - k / np.arange(n - c + 1, n + 1))


def average_pass_at_k(results: list[dict[str, Any]], k: int, n_problems: int) -> float:
    """
    Computes the average pass@k across all unique problem IDs.

    :param results: A list of dictionaries, each with "id" and "pass" (bool/int).
    :param k: The 'k' value for pass@k.
    :param max_budget: Maximum allowed number of calls to consider a result as passed.
    :param n_problems: Total number of unique problems.
    (We don't rely on the number of unique problems in results, as some problems may have timed out entirely.)
    """

    # 1. Group results by problem ID and count n (total) and c (correct)
    problem_stats = defaultdict(lambda: {"n": 0, "c": 0})

    for item in results:
        problem_id = item["id"]
        success = item["pass"]
        passed = bool(success)

        stats = problem_stats[problem_id]  # Get (or create) the stats dict for this id
        stats["n"] += 1
        if passed:
            stats["c"] += 1

    # 2. Calculate pass@k for each problem
    pass_k_values = []
    for stats in problem_stats.values():
        n = stats["n"]
        c = stats["c"]
        pass_k_score = pass_at_k(n, c, k)
        pass_k_values.append(pass_k_score)

    # 3. Return the average of all pass@k scores
    if not pass_k_values:
        return 0.0  # Avoid division by zero if results list is empty

    return np.sum(pass_k_values) / n_problems
