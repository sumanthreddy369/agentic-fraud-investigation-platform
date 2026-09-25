"""Run tests against a disposable PostgreSQL cluster, without touching system databases."""

from __future__ import annotations

import argparse
import os
import secrets
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin-dir", type=Path, required=True)
    args = parser.parse_args()
    binary = args.bin_dir.resolve()
    suffix = ".exe" if os.name == "nt" else ""
    for name in ("initdb", "pg_ctl"):
        if not (binary / (name + suffix)).is_file():
            parser.error(f"Missing PostgreSQL binary: {name}")
    workspace = Path(__file__).resolve().parents[1]
    scratch = workspace / ".test-runtime"
    scratch.mkdir(exist_ok=True)
    if not scratch.resolve().is_relative_to(workspace):
        raise RuntimeError("Test scratch directory must stay within the workspace")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with tempfile.TemporaryDirectory(prefix="postgres-", dir=scratch) as temporary:
        root = Path(temporary).resolve()
        if not root.is_relative_to(scratch.resolve()):
            raise RuntimeError("Unexpected test directory")
        cluster = root / "data"
        password = secrets.token_hex(24)
        password_file = root / "password"
        password_file.write_text(password, encoding="utf-8")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]

        def run(arguments):
            # A spawned PostgreSQL process may inherit pipe handles on Windows.
            # Use a file so communicate() never waits on a long-lived server.
            output_path = root / "command.log"
            with output_path.open("w", encoding="utf-8") as output:
                result = subprocess.run(
                    arguments,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    creationflags=flags,
                    timeout=60,
                )
            print(output_path.read_text(encoding="utf-8", errors="replace"), end="", flush=True)
            result.check_returncode()
            return result

        run(
            [
                str(binary / ("initdb" + suffix)),
                "-D",
                str(cluster),
                "-U",
                "risk_test",
                "--auth=scram-sha-256",
                "--encoding=UTF8",
                "--locale=C",
                f"--pwfile={password_file}",
            ]
        )
        password_file.unlink()
        control = str(binary / ("pg_ctl" + suffix))
        try:
            run(
                [
                    control,
                    "-D",
                    str(cluster),
                    "-l",
                    str(root / "postgres.log"),
                    "-o",
                    f"-h 127.0.0.1 -p {port}",
                    "-w",
                    "start",
                ]
            )
            environment = os.environ.copy()
            environment["RISK_TEST_DATABASE_URL"] = (
                f"postgresql+psycopg://risk_test:{password}@127.0.0.1:{port}/postgres"
            )
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q"],
                env=environment,
                cwd=workspace,
                creationflags=flags,
                capture_output=True,
                text=True,
            )
            print(result.stdout.replace(password, "<redacted>"), end="", flush=True)
            print(
                result.stderr.replace(password, "<redacted>"), end="", file=sys.stderr, flush=True
            )
            return result.returncode
        finally:
            if (cluster / "postmaster.pid").exists():
                run([control, "-D", str(cluster), "-m", "fast", "-w", "stop"])


if __name__ == "__main__":
    raise SystemExit(main())
