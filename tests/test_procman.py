"""Test procman.py: bat log tien trinh con vao ring buffer trong bo nho.

Dung Popen gia (khong chay tien trinh that, khong ghi file).
"""
import io
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.procman import (
    MAX_LINES,
    ManagedProcess,
    ProcessManager,
)


class FakePopen:
    """Popen gia: stdout/stderr la StringIO, poll/terminate/wait/kill."""

    def __init__(self, out_lines=(), err_lines=(), rc=None):
        self.stdout = io.StringIO("".join(out_lines))
        self.stderr = io.StringIO("".join(err_lines))
        self._rc = rc
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def poll(self):
        return self._rc

    @property
    def returncode(self):
        return self._rc

    def terminate(self):
        self.terminated = True
        self._rc = 0

    def wait(self, timeout=None):
        self.wait_calls += 1
        return self._rc if self._rc is not None else 0

    def kill(self):
        self.killed = True
        self._rc = 0


class StubbornFakePopen(FakePopen):
    """Popen gia bo qua terminate; chi chet khi kill."""

    def terminate(self):
        self.terminated = True  # ghi nhan nhung khong thoat

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.killed:
            return self._rc
        raise subprocess.TimeoutExpired(cmd=["fake"], timeout=timeout)


def _wait_total(managed, expected, timeout=5.0):
    """Doi den khi buffer co du `expected` dong (reader thread bat dong bo)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        total, _ = managed.lines()
        if total >= expected:
            return total
        time.sleep(0.02)
    total, _ = managed.lines()
    return total


def test_lines_captured_in_order():
    proc = FakePopen(out_lines=["dong 1\n", "dong 2\n", "dong 3\n"],
                     err_lines=["loi A\n"])
    managed = ManagedProcess("live", proc)
    assert _wait_total(managed, 4) == 4
    total, lines = managed.lines()
    assert total == 4
    assert lines == ["dong 1", "dong 2", "dong 3", "loi A"] or \
        set(lines) == {"dong 1", "dong 2", "dong 3", "loi A"}
    # Thu tu trong tung stream duoc giu nguyen.
    assert lines.index("dong 1") < lines.index("dong 2") < \
        lines.index("dong 3")


def test_lines_after_cursor():
    proc = FakePopen(out_lines=["a\n", "b\n", "c\n"])
    managed = ManagedProcess("live", proc)
    assert _wait_total(managed, 3) == 3
    total, lines = managed.lines(after=1)
    assert total == 3
    assert lines == ["b", "c"]
    total, lines = managed.lines(after=3)
    assert total == 3 and lines == []
    total, lines = managed.lines(after=99)
    assert total == 3 and lines == []
    total, lines = managed.lines(after=-5)
    assert total == 3 and len(lines) == 3


def test_ring_buffer_caps_at_max_lines():
    proc = FakePopen(out_lines=[f"dong {i}\n" for i in range(600)])
    managed = ManagedProcess("live", proc)
    assert _wait_total(managed, MAX_LINES) == MAX_LINES
    total, lines = managed.lines()
    assert total == MAX_LINES
    assert lines[0] == f"dong {600 - MAX_LINES}"
    assert lines[-1] == "dong 599"


def test_exit_code_recorded_when_process_ends():
    proc = FakePopen(out_lines=["x\n"])
    managed = ManagedProcess("live", proc)
    assert managed.running is True
    assert managed.exit_code is None
    proc._rc = 3  # tien trinh thoat ben ngoai
    assert managed.running is False
    assert managed.exit_code == 3


def test_stop_terminates_process():
    proc = FakePopen(out_lines=["x\n"])
    managed = ManagedProcess("live", proc)
    assert managed.stop() is True
    assert proc.terminated is True
    assert managed.running is False
    assert managed.exit_code == 0
    # Stop lan nua van ok (da dung roi).
    assert managed.stop() is True


def test_stop_kills_stubborn_process():
    proc = StubbornFakePopen()
    managed = ManagedProcess("live", proc)
    assert managed.stop(timeout=1) is True
    assert proc.terminated is True
    assert proc.killed is True
    assert managed.running is False


def test_status_reflects_running_stopped():
    manager = ProcessManager(popen_factory=lambda argv, **kw: FakePopen())
    ok, _reason, _m = manager.start("live", ["fake", "live"])
    assert ok is True
    status = manager.status("live")
    assert status["running"] is True
    assert status["started_utc"]
    assert status["exit_code"] is None
    assert manager.stop("live") is True
    status = manager.status("live")
    assert status["running"] is False
    assert status["exit_code"] == 0
    assert status["started_utc"]  # van giu thoi gian bat dau


def test_manager_start_twice_refuses_second():
    manager = ProcessManager(popen_factory=lambda argv, **kw: FakePopen())
    ok, _r, _m = manager.start("listener", ["fake"])
    assert ok is True
    ok, reason, managed = manager.start("listener", ["fake"])
    assert ok is False
    assert managed is None
    assert "đang chạy" in reason
    # Dung roi thi khoi dong lai duoc.
    assert manager.stop("listener") is True
    ok, _r, _m = manager.start("listener", ["fake"])
    assert ok is True


def test_manager_spawn_failure_reports_reason():
    def _boom(argv, **kwargs):
        raise FileNotFoundError("khong co file chay")

    manager = ProcessManager(popen_factory=_boom)
    ok, reason, managed = manager.start("live", ["khong-co"])
    assert ok is False
    assert managed is None
    assert "Không khởi động được Live" in reason


def test_manager_start_reasons_translated():
    """Ly do cua ProcessManager.start dich theo lang: mac dinh "vi"
    (co dau day du), lang="en" thi tieng Anh; ten noi bo khong lo."""
    manager = ProcessManager(popen_factory=lambda argv, **kw: FakePopen())
    ok, reason, _m = manager.start("listener", ["fake"])
    assert ok is True
    assert reason == "Đã khởi động Telegram listener"
    # Da chay thi tu choi (ca 2 ngon ngu).
    ok, reason, managed = manager.start("listener", ["fake"])
    assert ok is False and managed is None
    assert reason == "Telegram listener đang chạy"
    assert manager.stop("listener") is True
    # Tieng Anh: khong con manh tieng Viet khong dau nao.
    ok, reason, _m = manager.start("listener", ["fake"], lang="en")
    assert ok is True
    assert reason == "Telegram listener started"
    ok, reason, managed = manager.start("listener", ["fake"], lang="en")
    assert ok is False and managed is None
    assert reason == "Telegram listener is already running"
    assert manager.stop("listener") is True
    # Spawn loi, tieng Anh, chi tiet loi giu nguyen dang goc.
    def _boom_en(argv, **kwargs):
        raise FileNotFoundError("khong co file chay")

    manager_en = ProcessManager(popen_factory=_boom_en)
    ok, reason, managed = manager_en.start("live", ["khong-co"],
                                           lang="en")
    assert ok is False and managed is None
    assert reason == "Could not start Live: khong co file chay"
    for fragment in ("da khoi dong", "da chay", "khong khoi dong",
                     "thoat ngay"):
        assert fragment not in reason


def test_manager_start_passes_pipes_and_lines():
    seen = {}

    def _factory(argv, **kwargs):
        seen.update(kwargs)
        return FakePopen(out_lines=["hello log\n"])

    manager = ProcessManager(popen_factory=_factory)
    ok, _r, managed = manager.start("live", ["fake", "live"])
    assert ok is True
    assert seen["stdout"] == subprocess.PIPE
    assert seen["stderr"] == subprocess.PIPE
    assert seen["text"] is True
    assert _wait_total(managed, 1) == 1
    total, lines = manager.lines("live")
    assert total == 1 and lines == ["hello log"]


def test_manager_unknown_process_empty():
    manager = ProcessManager()
    assert manager.status("chua-co") == {
        "running": False, "started_utc": None, "exit_code": None}
    assert manager.lines("chua-co") == (0, [])
    assert manager.get("chua-co") is None
    assert manager.stop("chua-co") is True


def test_register_wraps_existing_popen():
    proc = FakePopen(out_lines=["da chay san\n"])
    manager = ProcessManager()
    managed = manager.register("live", proc, started_utc="2026-11-27T00:00:00+00:00")
    assert managed.started_utc == "2026-11-27T00:00:00+00:00"
    assert _wait_total(managed, 1) == 1
    assert manager.status("live")["running"] is True
