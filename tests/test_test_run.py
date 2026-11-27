"""Test test_run.py — bo kiem tra chan doan (khong goi MT5/Telegram that).

main() chay that tren Linux: cac buoc MT5 se FAIL/SKIP gon gang (khong
co goi MetaTrader5), log van ghi day du va tra exit code 1.
"""
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_test_run():
    spec = importlib.util.spec_from_file_location(
        "test_run_under_test", REPO_ROOT / "test_run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tr = load_test_run()


def test_redact_for_test_hides_token(monkeypatch):
    monkeypatch.setenv("DIAMONDX10_TELEGRAM_TOKEN", "token-bi-mat-123")
    monkeypatch.setenv("MT5_PASSWORD", "mat-khau-bi-mat")
    text = "token=token-bi-mat-123 pass=mat-khau-bi-mat binh thuong"
    out = tr.redact_for_test(text)
    assert "token-bi-mat-123" not in out
    assert "mat-khau-bi-mat" not in out
    assert "***" in out
    assert "binh thuong" in out


def test_redact_for_test_no_secrets(monkeypatch):
    monkeypatch.delenv("DIAMONDX10_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("MT5_PASSWORD", raising=False)
    assert tr.redact_for_test("khong co gi nhay cam") == "khong co gi nhay cam"


def test_diag_logger_check_pass_fail_skip(tmp_path):
    log = tr.DiagLogger(tmp_path / "t.log")

    def _ok():
        return "mo ta pass"

    def _bad():
        raise ValueError("loi gia de test")

    assert log.check("buoc pass", _ok) is True
    assert log.check("buoc fail", _bad) is False
    log.skip("buoc skip", "ly do skip")
    log.close()
    states = [s for _, s, _ in log.results]
    assert states == ["PASS", "FAIL", "SKIP"]
    text = (tmp_path / "t.log").read_text(encoding="utf-8")
    assert "PASS: mo ta pass" in text
    assert "FAIL" in text and "loi gia de test" in text
    assert "SKIP: ly do skip" in text


def test_main_on_linux_writes_log_and_exits_nonzero(tmp_path, monkeypatch):
    # Khong co token that — buoc Telegram se FAIL truoc khi gui (khong
    # goi mang). Khong co MT5 tren Linux — cac buoc MT5 FAIL/SKIP.
    monkeypatch.delenv("DIAMONDX10_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("MT5_PASSWORD", raising=False)
    rc = tr.main(["--out", str(tmp_path)])
    assert rc == 1
    logs = list(tmp_path.glob("test-run-*.log"))
    assert len(logs) == 1
    text = logs[0].read_text(encoding="utf-8")
    assert "TONG KET" in text
    assert "FAIL" in text
    assert "MT5 terminal" in text
    assert "Khong co buoc nao LOI" not in text


def test_subprocess_env_includes_src(monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    env = tr._subprocess_env()
    assert str(tr.ROOT / "src") in env["PYTHONPATH"]
    monkeypatch.setenv("PYTHONPATH", "/mot/duong/dan")
    env = tr._subprocess_env()
    assert env["PYTHONPATH"].startswith(str(tr.ROOT / "src"))
    assert "/mot/duong/dan" in env["PYTHONPATH"]
