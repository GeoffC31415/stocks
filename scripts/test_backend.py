"""Run the complete backend suite in one or two safely bootstrapped processes.

Every invocation collects the whole suite first. Timing hints affect scheduling
only; the actual JUnit node multiset must exactly equal the fresh collection.
Each shard invokes test_t212_synthetic.py, so its own process disables dotenv and
production database configuration before importing pytest/application modules.
Use that original launcher directly for focused development selections.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts/test_t212_synthetic.py"


def collection_nodes(output: str) -> list[str]:
    nodes = []
    for line in output.splitlines():
        line = line.strip()
        if ".py::" not in line:
            continue
        file = line.partition("::")[0]
        path = PurePosixPath(file)
        if path.is_absolute() or path.parts[:2] != ("backend", "tests") or ".." in path.parts:
            raise ValueError("Collection contains a test outside backend/tests.")
        nodes.append(line)
    totals = re.findall(r"(?:^|\n)(\d+) tests? collected\b", output)
    if not nodes or len(nodes) != len(set(nodes)) or not totals or int(totals[-1]) != len(nodes):
        raise ValueError("Fresh collection is empty, duplicated or incomplete.")
    return nodes


def collected_files(output: str) -> dict[str, int]:
    return dict(Counter(node.partition("::")[0] for node in collection_nodes(output)))


def partition(files: dict[str, int], jobs: int, hints: dict) -> list[list[str]]:
    def weight(file):
        value = hints.get(file)
        if type(value) not in (int, float):
            return float(files[file])
        try:
            value = float(value)
        except OverflowError:
            return float(files[file])
        if not math.isfinite(value) or value <= 0:
            return float(files[file])
        return min(value, 3600.0)

    groups = [[] for _ in range(jobs)]
    costs = [0.0] * jobs
    for file in sorted(files, key=lambda file: (-weight(file), file)):
        index = min(range(jobs), key=lambda index: costs[index])
        groups[index].append(file)
        costs[index] += weight(file)
    assert Counter(file for group in groups for file in group) == Counter(files.keys())
    return [group for group in groups if group]


def node_identity(node: str) -> tuple[str, str]:
    file, _, rest = node.partition("::")
    names, bracket, parameters = rest.partition("[")
    parts = names.split("::")
    classname = ".".join([file[:-3].replace("/", "."), *parts[:-1]])
    return classname, parts[-1] + (bracket + parameters if bracket else "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, choices=(1, 2), default=2)
    parser.add_argument("--output", type=Path, help="New absolute directory for logs and XML (must not exist)")
    parser.add_argument("--timings", type=Path, help="Optional previous run's timings.json; scheduling only")
    args = parser.parse_args()
    caller_umask = os.umask(0o077)
    processes = []
    streams = []
    cancelled = None
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}

    def cancel(signum, _frame):
        nonlocal cancelled
        # Never raise asynchronously: that can interrupt Popen registration or
        # even the first instruction of finally, stranding an owned child.
        cancelled = signum

    def check_cancelled():
        if cancelled is not None:
            raise SystemExit(128 + cancelled)

    def start_process(*command, **options):
        process = subprocess.Popen(*command, **options, start_new_session=True, umask=caller_umask)
        processes.append(process)
        check_cancelled()
        return process

    def wait_process(process, timeout, *, communicate=False):
        deadline = time.monotonic() + timeout
        while True:
            check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(process.args, timeout)
            try:
                operation = process.communicate if communicate else process.wait
                return operation(timeout=min(.1, remaining))
            except subprocess.TimeoutExpired:
                pass

    try:
        for sig in handlers:
            signal.signal(sig, cancel)
        return run(args, parser, start_process, wait_process, streams)
    finally:
        # The recording-only handlers stay installed throughout cleanup.
        try:
            for process in processes:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            for process in processes:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                # Also kill surviving descendants if their group leader exited.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        finally:
            for stream in streams:
                stream.close()
            os.umask(caller_umask)
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
        if cancelled is not None:
            raise SystemExit(128 + cancelled)


def run(args, parser, start_process, wait_process, streams) -> int:
    if args.output:
        if not args.output.is_absolute():
            parser.error("--output must be an absolute, new directory")
        args.output.mkdir(parents=True, exist_ok=False)
        output = args.output
    else:
        scratch = Path(os.environ.get("TMPDIR", str(Path.home() / ".cache/stocks-tests")))
        scratch.mkdir(parents=True, exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix="stocks-backend-", dir=scratch))
    environment = dict(os.environ)
    # Do not let ambient pytest filters silently turn a full gate into a subset.
    environment.pop("PYTEST_ADDOPTS", None)
    started = time.monotonic()
    command = [sys.executable, str(LAUNCHER)]
    collection = start_process(
        [*command, "backend/tests", "--collect-only", "-q"], cwd=ROOT,
        env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    stdout, stderr = wait_process(collection, 120, communicate=True)
    (output / "collection.log").write_text(stdout + stderr)
    if collection.returncode:
        print(stdout + stderr)
        return collection.returncode
    nodes = collection_nodes(stdout)
    files = collected_files(stdout)
    hints = {}
    if args.timings:
        try:
            if args.timings.stat().st_size <= 1048576:
                value = json.loads(args.timings.read_text())
                if isinstance(value, dict):
                    hints = value
        except (OSError, ValueError):
            pass  # Missing/bad hints affect speed, never admission or coverage.
    groups = partition(files, args.jobs, hints)
    (output / "plan.json").write_text(json.dumps({"collected": len(nodes), "files": groups}, indent=2))
    print(f"Collected {len(nodes)} tests; running all files in {len(groups)} isolated processes.", flush=True)
    print(f"Evidence: {output}", flush=True)
    processes = []
    codes = []
    for index, group in enumerate(groups):
        stream = (output / f"shard-{index}.log").open("w")
        streams.append(stream)
        processes.append(start_process(
            [*command, *group, "-q", f"--junitxml={output / f'shard-{index}.xml'}"],
            cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT,
        ))
    for index, process in enumerate(processes):
        code = wait_process(process, 600)
        codes.append(code)
        print(f"Shard {index + 1}: exit {code}", flush=True)
        if code:
            streams[index].flush()
            print((output / f"shard-{index}.log").read_text())
    actual = Counter()
    timings = defaultdict(float)
    known_modules = {file[:-3].replace("/", "."): file for file in files}
    for index in range(len(groups)):
        for case in ET.parse(output / f"shard-{index}.xml").iter("testcase"):
            classname = case.attrib["classname"]
            actual[classname, case.attrib["name"]] += 1
            module = classname
            while module not in known_modules and "." in module:
                module = module.rpartition(".")[0]
            if module in known_modules:
                timings[known_modules[module]] += float(case.attrib.get("time", "0"))
    expected = Counter(node_identity(node) for node in nodes)
    complete = actual == expected
    summary = {
        "collected": len(nodes), "executed": sum(actual.values()),
        "exact_node_multiset": complete, "exit_codes": codes,
        "wall_seconds": round(time.monotonic() - started, 3),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    (output / "timings.json").write_text(json.dumps(timings, indent=2, sort_keys=True))
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0 if complete and not any(codes) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
