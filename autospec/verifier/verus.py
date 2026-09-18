"""Verus verification wrapper."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import List

from .verdict import Verdict, VerdictType


class VerusVerifier:
    """Wrapper for Verus verification."""

    def __init__(self, timeout: int = 120, verus_cmd: str = "verus"):
        self.timeout = timeout
        self.verus_cmd = verus_cmd

    def verify(self, rust_file: Path) -> Verdict:
        """Run Verus on a Rust file and return a normalized verdict."""
        if not rust_file.exists():
            return Verdict(
                verdict_type=VerdictType.UNKNOWN,
                message=f"File not found: {rust_file}",
            )

        try:
            rust_file = rust_file.resolve()
            with tempfile.TemporaryDirectory(prefix="verus-work-") as work_dir:
                result = subprocess.run(
                    self._build_cmd(rust_file),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    cwd=work_dir,
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
                message=f"Verus timed out after {self.timeout}s",
                details=details or None,
            )
        except FileNotFoundError:
            return Verdict(
                verdict_type=VerdictType.UNKNOWN,
                message=(
                    "Verus not found. Install Verus or set VERUS_BIN "
                    f"to the correct executable; tried '{self.verus_cmd}'."
                ),
            )
        except Exception as exc:
            return Verdict(
                verdict_type=VerdictType.UNKNOWN,
                message=f"Verus verification error: {exc}",
            )

    def _build_cmd(self, rust_file: Path) -> List[str]:
        return [self.verus_cmd, str(rust_file)]

    def _parse_output(self, stdout: str, stderr: str, returncode: int) -> Verdict:
        output = stdout + stderr
        lowered = output.lower()

        if returncode == 0:
            return Verdict(
                verdict_type=VerdictType.VALID,
                message="Verus completed successfully",
                details=output,
            )

        if "timeout" in lowered or "timed out" in lowered:
            return Verdict(
                verdict_type=VerdictType.TIMEOUT,
                message="Verus timed out or reported a timeout",
                details=output,
            )

        if "error" in lowered or "verification results" in lowered:
            return Verdict(
                verdict_type=VerdictType.INVALID,
                message="Verus reported verification, type-checking, or compilation errors",
                details=output,
            )

        return Verdict(
            verdict_type=VerdictType.UNKNOWN,
            message=f"Verus exited with status {returncode}",
            details=output,
        )
