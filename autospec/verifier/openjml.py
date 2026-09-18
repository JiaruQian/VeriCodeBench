"""OpenJML ESC verification wrapper."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional

from .verdict import Verdict, VerdictType


class OpenJMLVerifier:
    """Wrapper for OpenJML extended static checking."""

    def __init__(
        self,
        timeout: int = 120,
        openjml_cmd: str = "openjml",
        solver: Optional[str] = None,
    ):
        self.timeout = timeout
        self.openjml_cmd = openjml_cmd
        self.solver = solver

    def verify(self, java_file: Path) -> Verdict:
        """Run OpenJML ESC on a Java file and return a normalized verdict."""
        if not java_file.exists():
            return Verdict(
                verdict_type=VerdictType.UNKNOWN,
                message=f"File not found: {java_file}",
            )

        try:
            result = subprocess.run(
                self._build_cmd(java_file),
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
                message=f"OpenJML timed out after {self.timeout}s",
                details=details or None,
            )
        except FileNotFoundError:
            return Verdict(
                verdict_type=VerdictType.UNKNOWN,
                message=(
                    "OpenJML not found. Install OpenJML or set OPENJML_BIN "
                    f"to the correct executable; tried '{self.openjml_cmd}'."
                ),
            )
        except Exception as exc:
            return Verdict(
                verdict_type=VerdictType.UNKNOWN,
                message=f"OpenJML verification error: {exc}",
            )

    def _build_cmd(self, java_file: Path) -> List[str]:
        cmd = [self.openjml_cmd, "--esc"]
        if self.solver:
            cmd.extend(["--exec", self.solver])
        cmd.append(str(java_file))
        return cmd

    def _parse_output(self, stdout: str, stderr: str, returncode: int) -> Verdict:
        output = stdout + stderr
        lowered = output.lower()

        if returncode == 0:
            return Verdict(
                verdict_type=VerdictType.VALID,
                message="OpenJML ESC completed successfully",
                details=output,
            )

        if "timeout" in lowered or "timed out" in lowered:
            return Verdict(
                verdict_type=VerdictType.TIMEOUT,
                message="OpenJML ESC timed out or reported a timeout",
                details=output,
            )

        if "error:" in lowered or "exception" in lowered or "esc could not be completed" in lowered:
            return Verdict(
                verdict_type=VerdictType.INVALID,
                message="OpenJML ESC reported verification or compilation errors",
                details=output,
            )

        return Verdict(
            verdict_type=VerdictType.UNKNOWN,
            message=f"OpenJML exited with status {returncode}",
            details=output,
        )
