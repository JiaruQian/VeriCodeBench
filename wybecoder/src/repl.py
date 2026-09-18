# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import json
import platform
import tempfile
import re
from logging import getLogger
import os
from pathlib import Path
import subprocess
import selectors
import signal
from subprocess import TimeoutExpired
from time import monotonic as timer
import resource
import glob
from typing import Iterable

from src.utils import initialize_logger, method_spec_line

logger = getLogger()


def get_loom_path() -> str:
    """Get the path to the Loom package.

    Resolution order:
      1. LOOM_PATH environment variable (if set)
      2. <SVAGENT_ROOT>/.lake/packages/Loom  (auto-detected from this file's location)

    Raises RuntimeError when no valid path is found.
    """
    env_path = os.getenv("LOOM_PATH")
    if env_path:
        return env_path

    # Auto-detect: repo root is two levels up from this file (src/repl.py)
    repo_root = Path(__file__).resolve().parent.parent
    candidate = repo_root / ".lake" / "packages" / "Loom"
    if candidate.exists():
        return str(candidate)

    raise RuntimeError(
        "Could not determine Loom path. Set the LOOM_PATH environment variable."
    )


def disable_core_dumps():
    """Disable core dump generation to prevent massive disk usage."""
    try:
        # Set the core dump size limit to 0 (disable core dumps)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        logger.debug("Core dumps disabled (RLIMIT_CORE set to 0)")
    except Exception as e:
        logger.warning(f"Failed to disable core dumps: {e}")


def cleanup_core_dumps(loom_path: str):
    """Delete existing core dump files in the Loom directory."""
    try:
        core_files = glob.glob(os.path.join(loom_path, "core.*"))
        nfs_files = glob.glob(os.path.join(loom_path, ".nfs*"))
        all_files = core_files + nfs_files
        if all_files:
            for dump_file in all_files:
                try:
                    os.remove(dump_file)
                    logger.info(f"Deleted core dump: {dump_file}")
                except OSError as e:
                    logger.warning(f"Failed to delete {dump_file}: {e}")
            logger.info(f"Cleaned up {len(dump_file)} core dump files")
    except Exception as e:
        logger.warning(f"Error during core dump cleanup: {e}")


class LeanRepl:
    def __init__(
        self,
        header: str | None = None,
        path: str | None = None,
        max_mem_mb: int = 10240,
        init_timeout: float = 300.0,
    ):
        if path is None:
            path = get_loom_path()
        self.path = path
        self.header = header
        self.header_env_id = None

        # Disable core dumps for this process and all children
        disable_core_dumps()

        # Clean up any existing core dumps from previous runs
        # cleanup_core_dumps(self.path)

        wrapper_script_path = Path(__file__).parent / "run_with_limit.sh"
        lake_command = ["lake", "exe", "repl"]

        # Build the final command list
        if platform.system() != "Darwin":
            # Prepend the wrapper script and the memory limit to the command
            command_to_run = [str(wrapper_script_path), str(max_mem_mb)] + lake_command
        else:
            # no memory limiting on MacOS
            command_to_run = lake_command

        self.process = subprocess.Popen(
            command_to_run,
            cwd=self.path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logger.info(f"Started Lean REPL with {max_mem_mb} MiB maximum memory")

        if self.header is not None:
            start = timer()
            response = self._run(header, timeout=init_timeout)
            logger.info(f"Cached header in {timer() - start:.2f}s")
            if errors := filter_errors(response.get("messages", [])):
                raise RuntimeError(f"broken header: {errors}")
            self.header_env_id = response["env"]

    def run(self, code: str, timeout: float = 600.0) -> dict:
        """
        Raises TimeoutExpired upon timeouts, and RuntimeError if the Lean
        process dies unexpectedly.
        """

        start = timer()
        use_header = False
        if self.header is not None and code.startswith(self.header):
            body = code[len(self.header) :]
            if not any(line.startswith("import") for line in body.splitlines()):
                use_header = True

        if use_header:
            env_id = self.header_env_id
            assert env_id is not None
            response = self._run(body, env_id=env_id, timeout=timeout)
            response["executed_code"] = body
            logger.info(f"Ran code in {timer() - start:.2f}s using cached header.")
        else:
            response = self._run(code, timeout=timeout)
            response["executed_code"] = code
            logger.warning(
                f"Unmatched header: ran code in {timer() - start:.2f}s without caching!"
            )
        return response

    def _run(
        self, code: str, env_id: int | None = None, timeout: float = 600.0
    ) -> dict:
        assert self.process is not None
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        assert self.process.stderr is not None

        def fmt_err(prefix: str, rc: int | None, stderr_buf: bytes) -> RuntimeError:
            stderr = stderr_buf.decode("utf-8", "replace")
            return RuntimeError(
                f"{prefix}\nreturncode={rc}\nstderr:\n{stderr if stderr else '<empty>'}"
            )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".lean", delete=True) as f:
            f.write(code)
            f.flush()

            request = {"path": f.name, "allTactics": True}
            if env_id is not None:
                request["env"] = env_id

            req_bytes = (json.dumps(request) + "\n\n").encode("utf-8")

            # Keep stderr for diagnostics without blocking
            stderr_buf = b""

            # Write request
            try:
                self.process.stdin.write(req_bytes)
                self.process.stdin.flush()
            except BrokenPipeError:
                rc = self.process.poll()
                # try to grab anything already written to stderr without blocking
                try:
                    stderr_buf += os.read(self.process.stderr.fileno(), 65536)
                except Exception:
                    pass
                raise fmt_err(
                    "Lean REPL broken pipe (process likely exited).", rc, stderr_buf
                )

            # Read response
            with selectors.DefaultSelector() as sel:
                sel.register(self.process.stdout, selectors.EVENT_READ, "stdout")
                sel.register(self.process.stderr, selectors.EVENT_READ, "stderr")

                response_buf = b""
                end_time = timer() + timeout

                while True:
                    remaining = end_time - timer()
                    if remaining <= 0:
                        self._kill_process_tree()
                        raise TimeoutExpired(cmd=self.process.args, timeout=timeout)

                    for key, _ in sel.select(timeout=remaining):
                        if key.data == "stderr":
                            chunk = os.read(self.process.stderr.fileno(), 4096)
                            if chunk:
                                stderr_buf += chunk
                                logger.error(
                                    "Lean REPL stderr: %s",
                                    chunk.decode("utf-8", "replace"),
                                )
                            continue

                        # stdout
                        chunk = os.read(self.process.stdout.fileno(), 4096)
                        if not chunk:
                            rc = self.process.poll()
                            raise fmt_err(
                                "Lean REPL terminated unexpectedly (stdout closed).",
                                rc,
                                stderr_buf,
                            )

                        response_buf += chunk
                        if b"\n\n" in response_buf:
                            msg, _, _ = response_buf.partition(b"\n\n")
                            try:
                                return json.loads(msg.decode("utf-8"))
                            except json.JSONDecodeError:
                                rc = self.process.poll()
                                raise fmt_err(
                                    "Failed to decode Lean REPL JSON response.",
                                    rc,
                                    stderr_buf + b"\n--- partial stdout ---\n" + msg,
                                )

    def close(self, grace_period: float = 2.0):
        """Close the subprocess gracefully, kill it if necessary."""
        if not self.process or self.process.poll() is not None:
            # already closed
            return

        try:
            if self.process.stdin:
                self.process.stdin.close()
            self.process.wait(timeout=grace_period)
            logger.info("Lean REPL process terminated gracefully.")

        except TimeoutExpired:
            logger.warning(
                f"Lean REPL did not terminate within {grace_period}s. "
                "Forcibly killing the process tree."
            )
            self._kill_process_tree()

        finally:
            self.process = None  # don't reuse a closed process

    def _kill_process_tree(self):
        """Kills the subprocess and all its descendants."""
        if not self.process or self.process.poll() is not None:
            return

        try:
            # On Unix, send SIGKILL to the entire process group.
            # Because the script used 'setsid', the process's PID is the group ID.
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            # Process already terminated, which is fine.
            pass


def extract_code_context(
    code: str, line_start: int, line_end: int | None = None, context_lines: int = 3
) -> str:
    """Extract relevant code section with context lines around the error."""
    lines = code.split("\n")

    if line_end is None:
        line_end = line_start

    # Adjust for 1-based indexing
    start_idx = max(0, line_start - context_lines - 1)
    end_idx = min(len(lines), line_end + context_lines)

    result_lines = []
    for i in range(start_idx, end_idx):
        line_num = i + 1
        marker = ">>> " if line_start <= line_num <= line_end else "    "
        result_lines.append(f"{marker}{line_num:3d} | {lines[i]}")

    return "\n".join(result_lines)


def sorry_errors(diagnostics: dict, start_line_idx: int | None = None) -> list:
    """Convert sorries list into error format.

    If start_line is provided, only include sorries at or after that line (1-based).

    Sorries are formatted as errors with severity='error' and a message
    indicating the proof uses 'sorry' at a specific proof state.
    """
    sorries = diagnostics.get("sorries", [])
    if start_line_idx is not None:
        sorries = [
            d for d in sorries if d.get("pos", {}).get("line", 0) >= start_line_idx
        ]
    return [
        {
            "severity": "error",
            "data": f"proof uses 'sorry' at proof state:\n{d['goal']}",
            **d,
        }
        for d in sorries
    ]


def parse_axioms_from_messages(messages: list) -> dict[str, list[str]]:
    """Extract axiom lists from #print axioms command output in messages.

    Returns a dict mapping method names to lists of axioms.
    """
    axiom_map = {}
    for msg in messages:
        data = msg.get("data", "")

        # #print axioms output appears in "info" messages
        # Look for pattern: '...' depends on axioms: [...]
        if "depends on axioms:" in data:
            # Extract the axiom list
            # Format: "'name' depends on axioms: [axiom1, axiom2, ...]"
            match = re.search(
                r"'([^']+)' depends on axioms:\s*\[(.*?)\]", data, re.DOTALL
            )
            if match:
                name = match.group(1)
                axiom_str = match.group(2)
                # Parse comma-separated axioms, handling whitespace
                axiom_list = [ax.strip() for ax in axiom_str.split(",") if ax.strip()]
                axiom_map[name] = axiom_list
            else:
                raise ValueError(f"Failed to parse axioms from message: {data}")
        # Also check for "does not depend on any axioms" - means empty list
        elif "does not depend on any axioms" in data:
            match = re.search(r"'([^']+)' does not depend on any axioms", data)
            if match:
                name = match.group(1)
                axiom_map[name] = []

    return axiom_map


def check_axioms(
    diagnostics: dict,
    allowed_axioms: list[str] = None,
    smt_sorry_check: bool = True,
    axiom_string_check: bool = True,
) -> list:
    """Check if code uses non-allowed axioms.

    Args:
        diagnostics: The diagnostics dictionary from runner.run()
        allowed_axioms: List of allowed axiom names. Defaults to trusted Lean axioms.
        smt_sorry_check: Whether to check the code for mentions of 'autoSMTSorry'.
        axiom_string_check: Whether to check the code for mentions of 'axiom'.

    Returns:
        List of error dictionaries for non-allowed axioms found.
    """
    if allowed_axioms is None:
        allowed_axioms = [
            "Classical.choice",
            "propext",
            "Quot.sound",
            "Lean.trustCompiler",
            "Lean.ofReduceBool",
            "Lean.ofReduceNat",
            "autoSMTSorry",  # trusted output of SMT solvers
        ]

    messages = diagnostics.get("messages", [])
    axiom_map = parse_axioms_from_messages(messages)

    if smt_sorry_check:
        if "autoSMTSorry" in diagnostics.get("executed_code", ""):
            # Add a dummy entry to axiom_map to trigger an error
            axiom_map["<code>"] = ["manual use of `autoSMTSorry`"]

    if axiom_string_check:
        if "axiom " in diagnostics.get("executed_code", ""):
            # Add a dummy entry to axiom_map to trigger an error
            axiom_map["<code>"] = ["use of `axiom` keyword"]

    errors = []
    for name, axioms in axiom_map.items():
        non_allowed = [ax for ax in axioms if ax not in allowed_axioms]
        if non_allowed:
            errors.append(
                {
                    "severity": "error",
                    "data": f"Method '{name}' uses non-allowed axioms: {', '.join(non_allowed)}. "
                    f"Only the following axioms are allowed: {', '.join(allowed_axioms)}. "
                    f"Please remove the use of these non-standard axioms.",
                    # No position info as requested
                }
            )

    return errors


def parse_test_failures_from_messages(messages: list, executed_code: str) -> list[dict]:
    """Extract test failures from diagnostic messages.

    Test cases using #guard statements will produce error messages if they fail.
    The error pattern is: "Expression\n  ...\ndid not evaluate to `true`"
    If a test passes, there is no error message.

    Args:
        messages: List of diagnostic messages
        executed_code: The code that was executed (to find test case locations)

    Returns:
        List of error dictionaries for failed test cases.
    """
    errors = []
    code_lines = executed_code.split("\n")

    # Track which lines contain #guard statements
    guard_lines = {}
    for i, line in enumerate(code_lines, start=1):
        if line.strip().startswith("#guard"):
            guard_lines[i] = line.strip()

    # Check error messages for test failures
    for msg in messages:
        data = msg.get("data", "")
        pos = msg.get("pos", {})
        line = pos.get("line", 0)
        severity = msg.get("severity", "")

        # Pattern 1: Check for the specific #guard failure pattern
        # "Expression\n  ...\ndid not evaluate to `true`"
        if "did not evaluate to `true`" in data:
            # This is definitely a test failure
            # Try to find the corresponding #guard line
            test_case = None
            if line in guard_lines:
                test_case = guard_lines[line]
            else:
                # Search for the closest #guard line before this error
                for guard_line_num in sorted(guard_lines.keys(), reverse=True):
                    if guard_line_num <= line:
                        test_case = guard_lines[guard_line_num]
                        break

            if test_case:
                errors.append(
                    {
                        "severity": "error",
                        "data": f"Test case failed: {test_case}",
                        # No position info as requested for test failures
                    }
                )
            else:
                # Still report it as a test failure even if we can't find the guard line
                errors.append(
                    {
                        "severity": "error",
                        "data": f"Test case failed (could not locate #guard statement)\n"
                        f"Error message: {data}",
                        # No position info
                    }
                )
        # Pattern 2: Check if this error is on a line with a #guard statement
        elif line in guard_lines and severity == "error":
            # This is likely a test case failure
            test_case = guard_lines[line]
            errors.append(
                {
                    "severity": "error",
                    "data": f"Test case failed: {test_case}\nError message: {data}",
                    # No position info
                }
            )

    return errors


def check_test_validity(diagnostics: dict) -> list:
    """Check if test cases pass.

    Test cases are identified by #guard statements. If a #guard statement
    produces an error, it means the test case failed.

    Args:
        diagnostics: The diagnostics dictionary from runner.run()

    Returns:
        List of error dictionaries for failed test cases.
    """
    messages = diagnostics.get("messages", [])
    executed_code = diagnostics.get("executed_code", "")

    # Filter to only error messages (warnings/info are not test failures)
    # Note: We check all messages, not just errors, because some test failures
    # might be reported with different severities
    error_messages = [
        msg for msg in messages if msg.get("severity") in ["error", "warning"]
    ]

    # Parse test failures from error messages
    test_failures = parse_test_failures_from_messages(error_messages, executed_code)

    return test_failures


def filter_errors(
    messages: list,
    exclude_severity: Iterable[str] = ["info", "warning"],
    only_severity: Iterable[str] | None = None,
) -> list:
    """Filter out warnings and other non-errors."""
    filtered_messages = []
    for error in messages:
        severity = error.get("severity", "unknown")
        if only_severity is not None and severity not in only_severity:
            continue
        if severity in exclude_severity:
            continue
        filtered_messages.append(error)
    return filtered_messages


def goedel_errors(code: str, messages: list, error_thres: bool = True) -> str:
    errors = filter_errors(messages, only_severity=["error"])
    return get_goedel_error_str(code, errors, error_thres)


def extract_goals(messages: list) -> list[str]:
    infos = filter_errors(messages, exclude_severity=[], only_severity=["info"])
    return [msg["data"] for msg in infos if msg["data"].startswith("theorem")]


def extract_goal_tag(s: str) -> str | None:
    """
    Extract the name after 'case ' on the line following 'unsolved goals'.
    Returns the name as a string, or None if no match is found.
    """
    m = re.search(r"unsolved goals\ncase\s+(\S+)", s)
    return m.group(1) if m else None


def extraction_errors(messages: list) -> list[str]:
    """Extract mvar errors that occurred during goal extraction."""
    errors = filter_errors(messages, only_severity=["error"])
    return [
        err["data"]
        for err in errors
        if "extracted goal has metavariables" in err["data"].lower()
    ]


def extract_goals_and_tags(messages: list) -> list[tuple[str, str]]:
    goals = extract_goals(messages)
    errors = filter_errors(messages, only_severity=["error"])
    goal_tags = [extract_goal_tag(err["data"]) for err in errors]
    goal_tags = [tag for tag in goal_tags if tag is not None]
    assert len(goals) == len(goal_tags), (goals, goal_tags)
    assert not extraction_errors(messages), extraction_errors(messages)
    # Return list of (goal, tag) tuples - tags may not be unique
    return list(zip(goals, goal_tags))


def _format_errors(code: str, errors: list, max_chars_per_message: int = 2000) -> str:
    output = []
    output.append("# LEAN ERROR MESSAGES")
    output.append("")

    filtered = filter_errors(errors)

    for idx, error in enumerate(filtered, 1):
        severity = error.get("severity", "unknown")
        output.append(f"\n## ERROR {idx}/{len(filtered)}")

        pos = error.get("pos", {})
        end_pos = error.get("endPos")
        message = error.get("data", "")

        line = pos.get("line")
        column = pos.get("column")

        output.append(f"\nSeverity: `{severity.upper()}`")
        if line is not None:
            output.append(f"Location: Line {line}, Column {column}")

        if end_pos:
            end_line = end_pos.get("line")
            end_column = end_pos.get("column")
            output.append(f"End Location: Line {end_line}, Column {end_column}")

        output.append("\nError Message:")
        max_chars = max_chars_per_message
        if len(message) > max_chars:
            msg = f"```lean\n{message[:max_chars]}\n```\n(message cut after {max_chars} characters)"
        else:
            msg = f"```lean\n{message}\n```"
        output.append(msg)

        output.append("\nCode Context:")
        output.append("```lean")

        if line:
            end_line = end_pos.get("line") if end_pos else line
            code_context = extract_code_context(code, line, end_line, context_lines=5)
            output.append(code_context)

        output.append("```")

    output.append("\n# FULL CODE WITH LINE NUMBERS FOR REFERENCE")
    output.append("(possibly excluding the header)")
    output.append("```lean")

    # Add full code with line numbers
    lines = code.split("\n")
    for i, line in enumerate(lines, 1):
        output.append(f"{i:3d} | {line}")

    output.append("```")

    return "\n".join(output)


def format_errors(
    code: str,
    errors: list,
    max_chars_per_message: int = 2000,
    goedel_format: bool = False,
) -> str:
    """Format errors with code context for LLM consumption."""
    if goedel_format:
        return goedel_errors(code, errors)
    else:
        return _format_errors(code, errors, max_chars_per_message)


def get_goedel_error_str(code: str, errors: list, error_thres: bool = True) -> str:
    """
    Format compilation errors as in Goedel prover.
    Taken from https://github.com/Goedel-LM/Goedel-Prover-V2/blob/2e9036e118464aa96a8bebaf9f5b9d091aa3585c/src/utils.py#L9

    Args:
        code (str): The Lean 4 code that was compiled.
        errors (list): Errors filtered from Lean REPL (severity "error").
        error_thres (bool, default True): Whether to limit the number of displayed errors to 8.
    Returns:
        str: Formatted error string with code snippets and error messages.
    """
    err_str = ""
    code_lines = code.split("\n")
    error_num_thres = 8 if error_thres else len(errors)

    for i, error in enumerate(errors[:error_num_thres]):
        start_line = error["pos"]["line"] - 1
        start_col = error["pos"]["column"]

        if error["endPos"] is None:
            end_line = start_line
            end_col = len(code_lines[start_line])
        else:
            end_line = error["endPos"]["line"] - 1
            end_col = error["endPos"]["column"]

        err_str += f"\nError {i + 1}:\n"
        err_str += "\nCorresponding Code:\n```lean4\n"

        error_code = ""
        for ii in range(-4, 0):
            if start_line + ii >= 0:
                error_code += f"{code_lines[start_line + ii]}\n"
        if start_line != end_line:
            error_code += (
                code_lines[start_line][:start_col]
                + "<error>"
                + code_lines[start_line][start_col:]
                + "\n"
            )

            if not error_thres:
                for j in range(start_line + 1, end_line):
                    error_code += f"{code_lines[j]}\n"
            else:
                show_line = 6
                for j in range(start_line + 1, min(end_line, start_line + show_line)):
                    error_code += f"{code_lines[j]}\n"
                if end_line > start_line + show_line:
                    leading_spaces = len(code_lines[j]) - len(code_lines[j].lstrip(" "))
                    error_code += (
                        "\n" + " " * leading_spaces + "... --[Truncated]-- ...\n"
                    )

            error_code += (
                code_lines[end_line][:end_col]
                + "</error>"
                + code_lines[end_line][end_col:]
                + "\n"
            )
        else:
            error_code += (
                code_lines[start_line][:start_col]
                + "<error>"
                + code_lines[start_line][start_col:end_col]
                + "</error>"
                + code_lines[start_line][end_col:]
                + "\n"
            )
        if end_line + 1 < len(code_lines):
            error_code += f"{code_lines[end_line + 1]}\n"

        err_str += error_code
        err_str += "\n```\n"
        err_str += f"\nError Message: {error['data']}\n"

    if len(errors) > error_num_thres:
        err_str += f"\n... [Omitted {len(errors) - error_num_thres} more errors] ...\n"

    return err_str


def main():
    with open("data/example3.lean") as f:
        code = f.read()

    header = code.split("-- BEGIN BODY", maxsplit=1)[0]

    env = LeanRepl(header=header, init_timeout=60)
    for _ in range(1):
        diagnostics = env.run(code, timeout=300)

    # Extract errors from response
    errors = diagnostics.get("messages", [])
    line = method_spec_line(diagnostics["executed_code"])
    logger.info(f"Method spec line: {line}")
    errors += sorry_errors(diagnostics, start_line_idx=line)
    errors += check_axioms(diagnostics)
    ran = diagnostics["executed_code"]

    extracted = extract_goals_and_tags(diagnostics["messages"])
    if not extracted:
        logger.error("No goals extracted!")
    else:
        logger.info(f"SUCCESS! Extracted {len(extracted)} goals:")

    for goal, tag in extracted:
        logger.info(f"Extracted goal {tag}: {goal}")

    if filter_errors(errors):
        formatted_output = format_errors(ran, errors)
        logger.info("\n" + formatted_output)
    else:
        logger.info("No errors found!")
        logger.info(f"Response keys: {diagnostics.keys()}")


if __name__ == "__main__":
    initialize_logger()
    main()
