from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import pytest


SMOKE_TEST_PREFIX = "tests/test_index_smoke.py::"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("poshy-smoke-timing")
    group.addoption(
        "--smoke-timing",
        action="store_true",
        default=False,
        help="Collect semantic timing checkpoints for browser smoke tests.",
    )
    group.addoption(
        "--smoke-timing-json",
        action="store",
        metavar="PATH",
        default=None,
        help="Write browser smoke timing records to PATH as JSON.",
    )


def pytest_configure(config: pytest.Config) -> None:
    plugin = SmokeTimingPlugin(config)
    config.pluginmanager.register(plugin, "poshy-smoke-timing")


@dataclass
class SmokeStepRecord:
    label: str
    elapsed_ms: float
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SmokeTestRecord:
    nodeid: str
    elapsed_ms: float | None = None
    outcome: str = "unknown"
    phase_outcomes: dict[str, str] = field(default_factory=dict)
    steps: list[SmokeStepRecord] = field(default_factory=list)


class SmokeTimingPlugin:
    def __init__(self, config: pytest.Config) -> None:
        json_path = config.getoption("--smoke-timing-json")
        self.enabled = bool(config.getoption("--smoke-timing") or json_path)
        self.json_path = Path(json_path).expanduser() if json_path else None
        self.records: dict[str, SmokeTestRecord] = {}

    def is_smoke_test(self, nodeid: str) -> bool:
        return nodeid.startswith(SMOKE_TEST_PREFIX)

    def ensure_record(self, nodeid: str) -> SmokeTestRecord:
        record = self.records.get(nodeid)
        if record is None:
            record = SmokeTestRecord(nodeid=nodeid)
            self.records[nodeid] = record
        return record

    def record_step(
        self,
        nodeid: str,
        label: str,
        elapsed_ms: float,
        *,
        status: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        record = self.ensure_record(nodeid)
        record.steps.append(
            SmokeStepRecord(
                label=label,
                elapsed_ms=round(elapsed_ms, 3),
                status=status,
                metadata=dict(metadata or {}),
            )
        )

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item: pytest.Item, nextitem: pytest.Item | None):
        if not self.enabled or not self.is_smoke_test(item.nodeid):
            yield
            return

        record = self.ensure_record(item.nodeid)
        started_at = perf_counter()
        yield
        record.elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
        record.outcome = self._resolve_outcome(record.phase_outcomes)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo[Any]):
        outcome = yield
        if not self.enabled or not self.is_smoke_test(item.nodeid):
            return

        report = outcome.get_result()
        record = self.ensure_record(item.nodeid)
        record.phase_outcomes[report.when] = report.outcome

    def pytest_terminal_summary(
        self,
        terminalreporter: pytest.TerminalReporter,
        exitstatus: int,
        config: pytest.Config,
    ) -> None:
        if not self.enabled or not self.records:
            return

        test_rows = [
            record
            for record in self.records.values()
            if record.elapsed_ms is not None
        ]
        if not test_rows:
            return

        step_rows = [
            (record.nodeid, step)
            for record in self.records.values()
            for step in record.steps
        ]
        total_ms = sum(record.elapsed_ms or 0 for record in test_rows)

        terminalreporter.section("smoke timing", sep="=")
        terminalreporter.write_line(
            f"Timed smoke runtime: {total_ms / 1000:.2f}s across {len(test_rows)} tests"
        )
        terminalreporter.write_line("Slowest smoke tests:")
        for record in sorted(test_rows, key=lambda entry: entry.elapsed_ms or 0, reverse=True)[:10]:
            terminalreporter.write_line(
                f"  {(record.elapsed_ms or 0) / 1000:.2f}s  {record.outcome:7}  {record.nodeid}"
            )

        if step_rows:
            terminalreporter.write_line("Slowest smoke checkpoints:")
            for nodeid, step in sorted(
                step_rows,
                key=lambda entry: entry[1].elapsed_ms,
                reverse=True,
            )[:20]:
                terminalreporter.write_line(
                    f"  {step.elapsed_ms / 1000:.2f}s  {step.status:6}  {nodeid} :: {step.label}"
                )

        if self.json_path:
            terminalreporter.write_line(f"Smoke timing JSON: {self.json_path}")

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        if not self.enabled or not self.json_path:
            return

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "test_count": len(self.records),
                "step_count": sum(len(record.steps) for record in self.records.values()),
                "total_elapsed_ms": round(
                    sum(record.elapsed_ms or 0 for record in self.records.values()),
                    3,
                ),
            },
            "tests": [
                {
                    "kind": "test",
                    "test": record.nodeid,
                    "elapsed_ms": record.elapsed_ms,
                    "outcome": record.outcome,
                    "metadata": {
                        "step_count": len(record.steps),
                    },
                }
                for record in self.records.values()
            ],
            "steps": [
                {
                    "kind": "step",
                    "test": record.nodeid,
                    "step": step.label,
                    "elapsed_ms": step.elapsed_ms,
                    "status": step.status,
                    "outcome": record.outcome,
                    "metadata": step.metadata,
                }
                for record in self.records.values()
                for step in record.steps
            ],
        }
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        self.json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _resolve_outcome(self, phase_outcomes: dict[str, str]) -> str:
        if "failed" in phase_outcomes.values():
            return "failed"
        if "skipped" in phase_outcomes.values():
            return "skipped"
        if phase_outcomes.get("call") == "passed":
            return "passed"
        return "unknown"


class _SmokeTimingStepContext:
    def __init__(
        self,
        plugin: SmokeTimingPlugin,
        nodeid: str,
        label: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.plugin = plugin
        self.nodeid = nodeid
        self.label = label
        self.metadata = dict(metadata or {})
        self.started_at = 0.0

    def __enter__(self) -> _SmokeTimingStepContext:
        self.started_at = perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        elapsed_ms = (perf_counter() - self.started_at) * 1000
        self.plugin.record_step(
            self.nodeid,
            self.label,
            elapsed_ms,
            status="failed" if exc_type else "passed",
            metadata=self.metadata,
        )
        return False


class _NoopStepContext:
    def __init__(self, metadata: dict[str, Any] | None = None) -> None:
        self.metadata = dict(metadata or {})

    def __enter__(self) -> _NoopStepContext:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class NullSmokeTimingRecorder:
    enabled = False

    def step(self, label: str, *, metadata: dict[str, Any] | None = None) -> _NoopStepContext:
        return _NoopStepContext(metadata=metadata)

    def run(
        self,
        label: str,
        *,
        action=None,
        wait=None,
        metadata: dict[str, Any] | None = None,
    ):
        result = None
        if action is not None:
            result = action()
        if wait is not None:
            wait()
        return result

    def check(self, label: str, assertion, *, metadata: dict[str, Any] | None = None):
        return self.run(label, action=assertion, metadata=metadata)


class SmokeTimingRecorder(NullSmokeTimingRecorder):
    enabled = True

    def __init__(self, plugin: SmokeTimingPlugin, nodeid: str) -> None:
        self.plugin = plugin
        self.nodeid = nodeid

    def step(
        self,
        label: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> _SmokeTimingStepContext:
        return _SmokeTimingStepContext(
            self.plugin,
            self.nodeid,
            label,
            metadata=metadata,
        )

    def run(
        self,
        label: str,
        *,
        action=None,
        wait=None,
        metadata: dict[str, Any] | None = None,
    ):
        with self.step(label, metadata=metadata):
            return super().run(label, action=action, wait=wait, metadata=metadata)


@pytest.fixture
def smoke_timing(request: pytest.FixtureRequest) -> SmokeTimingRecorder | NullSmokeTimingRecorder:
    plugin = request.config.pluginmanager.get_plugin("poshy-smoke-timing")
    if (
        plugin is None
        or not plugin.enabled
        or not plugin.is_smoke_test(request.node.nodeid)
    ):
        return NullSmokeTimingRecorder()

    plugin.ensure_record(request.node.nodeid)
    return SmokeTimingRecorder(plugin, request.node.nodeid)
