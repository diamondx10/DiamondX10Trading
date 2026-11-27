"""Test phat hien + cai dat Playwright/Chromium cho Muse
(muse_browser.py: find_chromium_executable, is_playwright_ready,
install_playwright, ensure_muse_browser_ready).

Khong trinh duyet that, khong pip that, khong cache Playwright
that: moi test truyen search_roots gia (tmp_path) hoac runner gia
ghi lai argv. Neu module muse_browser chua co thi toan bo file nay
duoc skip, khong lam do suite hien tai.

Quy uoc: chuoi tieng Viet KHONG dau; file that chi dung tmp_path.
"""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

muse_browser = pytest.importorskip("diamondx10.muse_browser")
from diamondx10.muse_browser import (
    ensure_muse_browser_ready,
    find_chromium_executable,
    install_playwright,
    is_playwright_ready,
)

EXPECTED_PIP_ARGV = [sys.executable, "-m", "pip", "install", "playwright"]
EXPECTED_BROWSER_ARGV = [sys.executable, "-m", "playwright",
                         "install", "chromium"]


# --- Helper ------------------------------------------------------------

def _chrome_rel():
    """Duong dan tuong doi cua binary Chromium theo OS (nhu code that)."""
    if sys.platform == "win32":
        return Path("chrome-win") / "chrome.exe"
    if sys.platform == "darwin":
        return (Path("chrome-mac") / "Chromium.app" / "Contents"
                / "MacOS" / "Chromium")
    return Path("chrome-linux") / "chrome"


def _fake_chromium_root(tmp_path, name="chromium-1234", with_binary=True):
    """Thu muc cache Playwright gia; tra duong dan root.

    with_binary=True: tao file binary gia tai
    <root>/chromium-<rev>/<chrome_rel>.
    with_binary=False: chi tao thu muc chromium-<rev> rong.
    """
    root = tmp_path / "ms-playwright"
    if with_binary:
        exe = root / name / _chrome_rel()
        exe.parent.mkdir(parents=True)
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
    else:
        (root / name).mkdir(parents=True)
    return root


def _patch_find_spec(monkeypatch, present=True):
    """Gia lap goi `playwright` co / khong co (khong phu thuoc venv).

    Chi doi ket qua cho ten "playwright"; ten khac goi ham that.
    """
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name, *args, **kwargs):
        if name == "playwright":
            return SimpleNamespace(name="playwright") if present else None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)


class _FakeRunner:
    """Runner gia: ghi lai argv, tra returncode theo kich ban."""

    def __init__(self, codes=(0, 0)):
        self.codes = list(codes)
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        code = self.codes.pop(0) if self.codes else 0
        return SimpleNamespace(returncode=code)


class _RaisingRunner:
    """Runner gia: raise OSError ngay khi goi."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        raise OSError("khong chay duoc lenh gia")


# --- find_chromium_executable ------------------------------------------

def test_find_chromium_missing_dirs_returns_none(tmp_path):
    """Thu muc khong ton tai / khong co chromium-*: None, khong raise."""
    missing = tmp_path / "khong-co-thu-muc-nay"
    empty = tmp_path / "trong"
    empty.mkdir()
    assert find_chromium_executable(search_roots=[missing]) is None
    assert find_chromium_executable(search_roots=[empty]) is None
    assert find_chromium_executable(
        search_roots=[missing, empty]) is None


def test_find_chromium_finds_fake_binary(tmp_path):
    """Tim thay binary gia duoi thu muc chromium-<rev>/."""
    root = _fake_chromium_root(tmp_path)
    found = find_chromium_executable(search_roots=[root])
    assert found == root / "chromium-1234" / _chrome_rel()
    assert found.is_file()


def test_find_chromium_dir_without_binary_returns_none(tmp_path):
    """Co thu muc chromium-<rev> nhung thieu binary: None, khong raise."""
    root = _fake_chromium_root(tmp_path, with_binary=False)
    assert find_chromium_executable(search_roots=[root]) is None


def test_find_chromium_searches_roots_in_order(tmp_path):
    """Root dau tien trong thi tim tiep root sau."""
    empty = tmp_path / "trong"
    empty.mkdir()
    root = _fake_chromium_root(tmp_path / "co", name="chromium-9999")
    found = find_chromium_executable(search_roots=[empty, root])
    assert found == root / "chromium-9999" / _chrome_rel()


# --- is_playwright_ready ------------------------------------------------

def test_ready_when_package_and_browser_present(monkeypatch, tmp_path):
    """Goi co + binary co trong root gia -> san sang."""
    _patch_find_spec(monkeypatch, present=True)
    root = _fake_chromium_root(tmp_path)
    assert is_playwright_ready(search_roots=[root]) is True


def test_not_ready_when_package_missing(monkeypatch, tmp_path):
    """Goi thieu -> khong san sang, du binary co trong root gia."""
    _patch_find_spec(monkeypatch, present=False)
    root = _fake_chromium_root(tmp_path)
    assert is_playwright_ready(search_roots=[root]) is False


def test_not_ready_when_browser_missing(monkeypatch, tmp_path):
    """Goi co nhung root gia trong (khong binary) -> khong san sang."""
    _patch_find_spec(monkeypatch, present=True)
    empty = tmp_path / "trong"
    empty.mkdir()
    assert is_playwright_ready(search_roots=[empty]) is False


# --- install_playwright -------------------------------------------------

def test_install_success_calls_pip_then_browser():
    """Thanh cong: dung 2 lenh, pip truoc roi playwright install."""
    runner = _FakeRunner(codes=(0, 0))
    assert install_playwright(runner=runner) is True
    assert runner.calls == [EXPECTED_PIP_ARGV, EXPECTED_BROWSER_ARGV]


def test_install_pip_failure_skips_browser_install():
    """pip loi (returncode != 0) -> False, KHONG chay lenh browser."""
    runner = _FakeRunner(codes=(1,))
    assert install_playwright(runner=runner) is False
    assert runner.calls == [EXPECTED_PIP_ARGV]


def test_install_browser_failure_returns_false():
    """pip OK nhung playwright install loi -> False, da goi ca 2 lenh."""
    runner = _FakeRunner(codes=(0, 1))
    assert install_playwright(runner=runner) is False
    assert runner.calls == [EXPECTED_PIP_ARGV, EXPECTED_BROWSER_ARGV]


def test_install_runner_oserror_returns_false():
    """Runner raise OSError (khong chay duoc pip) -> False, khong raise."""
    runner = _RaisingRunner()
    assert install_playwright(runner=runner) is False
    assert runner.calls == [EXPECTED_PIP_ARGV]


# --- ensure_muse_browser_ready ------------------------------------------

def test_ensure_ready_calls_no_runner(monkeypatch, tmp_path):
    """Da san sang -> True ngay, KHONG goi runner lan nao."""
    _patch_find_spec(monkeypatch, present=True)
    root = _fake_chromium_root(tmp_path)
    runner = _FakeRunner()
    assert ensure_muse_browser_ready(runner=runner,
                                     search_roots=[root]) is True
    assert runner.calls == []


def test_ensure_not_ready_install_false_calls_no_runner(monkeypatch, tmp_path):
    """Chua san sang + install=False -> False, KHONG goi runner."""
    _patch_find_spec(monkeypatch, present=True)
    empty = tmp_path / "trong"
    empty.mkdir()
    runner = _FakeRunner()
    assert ensure_muse_browser_ready(install=False, runner=runner,
                                     search_roots=[empty]) is False
    assert runner.calls == []


def test_ensure_installs_when_missing(monkeypatch, tmp_path):
    """Chua san sang + install=True -> chay cai dat, tra ket qua cai."""
    _patch_find_spec(monkeypatch, present=True)
    empty = tmp_path / "trong"
    empty.mkdir()
    runner = _FakeRunner(codes=(0, 0))
    assert ensure_muse_browser_ready(runner=runner,
                                     search_roots=[empty]) is True
    assert runner.calls == [EXPECTED_PIP_ARGV, EXPECTED_BROWSER_ARGV]


def test_ensure_install_failure_returns_false(monkeypatch, tmp_path):
    """Chua san sang + cai loi -> False (ket qua cai dat la du)."""
    _patch_find_spec(monkeypatch, present=False)
    empty = tmp_path / "trong"
    empty.mkdir()
    runner = _FakeRunner(codes=(1,))
    assert ensure_muse_browser_ready(runner=runner,
                                     search_roots=[empty]) is False
    assert runner.calls == [EXPECTED_PIP_ARGV]
