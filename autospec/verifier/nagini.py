"""Nagini verification wrapper."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from .verdict import Verdict, VerdictType


class NaginiVerifier:
    """Wrapper for Nagini verification."""

    def __init__(self, timeout: int = 120, nagini_cmd: str = "nagini"):
        self.timeout = timeout
        self.nagini_cmd = nagini_cmd

    def verify(self, python_file: Path) -> Verdict:
        """Run Nagini on a Python file and return a normalized verdict."""
        if not python_file.exists():
            return Verdict(
                verdict_type=VerdictType.UNKNOWN,
                message=f"File not found: {python_file}",
            )

        try:
            result = subprocess.run(
                self._build_cmd(python_file),
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return self._parse_output(result.stdout, result.stderr, result.returncode)
        except subprocess.TimeoutExpired as exc:
            details = ""
            if exc.stdout:
                details += str(exc.stdout)
            if exc.stderr:
                details += str(exc.stderr)
            return Verdict(
                verdict_type=VerdictType.TIMEOUT,
                message=f"Nagini timed out after {self.timeout}s",
                details=details or None,
            )
        except FileNotFoundError:
            return Verdict(
                verdict_type=VerdictType.UNKNOWN,
                message=(
                    "Nagini not found. Install Nagini or set NAGINI_BIN "
                    f"to the correct executable; tried '{self.nagini_cmd}'."
                ),
            )
        except Exception as exc:
            return Verdict(
                verdict_type=VerdictType.UNKNOWN,
                message=f"Nagini verification error: {exc}",
            )

    def _build_cmd(self, python_file: Path) -> List[str]:
        return [self.nagini_cmd, str(python_file)]

    def _parse_output(self, stdout: str, stderr: str, returncode: int) -> Verdict:
        output = stdout + stderr
        lowered = output.lower()

        if returncode == 0:
            return Verdict(
                verdict_type=VerdictType.VALID,
                message="Nagini completed successfully",
                details=output,
            )

        if "timeout" in lowered or "timed out" in lowered:
            return Verdict(
                verdict_type=VerdictType.TIMEOUT,
                message="Nagini timed out or reported a timeout",
                details=output,
            )

        if "error" in lowered or "failed" in lowered or "exception" in lowered:
            return Verdict(
                verdict_type=VerdictType.INVALID,
                message="Nagini reported verification, type-checking, or runtime errors",
                details=output,
            )

        return Verdict(
            verdict_type=VerdictType.UNKNOWN,
            message=f"Nagini exited with status {returncode}",
            details=output,
        )
