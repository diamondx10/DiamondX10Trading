"""Quan ly tien trinh con co bat log (manager console).

Moi tien trinh duoc quan ly (live, listener, diagnostics) co stdout +
stderr duoc doc theo dong (PIPE + reader thread) vao ring buffer trong
bo nho (toi da MAX_LINES dong / tien trinh, khong bao gio ghi ra file
o day). Reader thread la daemon, khong chan shutdown.

Diem tiem cho test: ProcessManager nhan popen_factory (mac dinh
subprocess.Popen) — giong _spawn_proc cua webapi.
"""
import subprocess
import threading
from collections import deque
from datetime import datetime, timezone

from .i18n import normalize_language, proc_display_name, t

MAX_LINES = 500

MANAGED_PROCESSES = ("live", "listener", "diagnostics")


class ManagedProcess:
    """1 tien trinh con + log dong da bat duoc."""

    def __init__(self, name, proc, started_utc=None):
        self.name = name
        self.proc = proc
        self.started_utc = (
            started_utc or datetime.now(timezone.utc).isoformat())
        self._lines = deque(maxlen=MAX_LINES)
        self._lock = threading.Lock()
        self._threads = []
        for stream in (getattr(proc, "stdout", None),
                       getattr(proc, "stderr", None)):
            if stream is None:
                continue
            thread = threading.Thread(
                target=self._reader, args=(stream,), daemon=True)
            thread.start()
            self._threads.append(thread)

    def _reader(self, stream):
        """Doc tung dong tu 1 stream vao ring buffer; khong bao gio raise."""
        try:
            for raw in stream:
                if isinstance(raw, bytes):
                    line = raw.decode("utf-8", "replace")
                else:
                    line = raw
                line = line.rstrip("\r\n")
                with self._lock:
                    self._lines.append(line)
        except Exception:  # noqa: BLE001 — doc log loi thi dung im
            pass
        finally:
            try:
                stream.close()
            except Exception:  # noqa: BLE001 — dong stream loi thi thoi
                pass

    @property
    def running(self):
        """True khi tien trinh con chay (poll() is None)."""
        try:
            return self.proc.poll() is None
        except Exception:  # noqa: BLE001 — poll loi thi coi nhu da dung
            return False

    @property
    def exit_code(self):
        """Ma thoat (None khi con chay)."""
        try:
            rc = self.proc.poll()
        except Exception:  # noqa: BLE001 — poll loi thi khong co ma
            return None
        if rc is not None:
            return rc
        return getattr(self.proc, "returncode", None)

    def lines(self, after=0):
        """Tra (total, lines) — lines la cac dong sau cursor `after`.

        `after` la so dong da doc (cursor cua frontend); after <= 0
        tra toan bo buffer, after >= total tra [].
        """
        try:
            after = int(after)
        except (TypeError, ValueError):
            after = 0
        if after < 0:
            after = 0
        with self._lock:
            buffered = list(self._lines)
        total = len(buffered)
        if after >= total:
            return total, []
        return total, buffered[after:]

    def stop(self, timeout=5):
        """Dung tien trinh: terminate -> doi -> kill neu can.

        Tra True (luon tra True nhu _stop_proc cua webapi: dung loi
        thi thoi, khong raise). Reader thread tu ket thuc khi pipe
        dong (EOF); thread la daemon nen khong chan shutdown.
        """
        try:
            if self.proc.poll() is not None:
                return True
        except Exception:  # noqa: BLE001 — poll loi thi van thu dung
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                self.proc.kill()
                self.proc.wait(timeout=timeout)
            except Exception:  # noqa: BLE001 — kill loi thi thoi
                pass
        except Exception:  # noqa: BLE001 — dung loi thi thoi
            pass
        return True


class ProcessManager:
    """Registry cac ManagedProcess, theo ten.

    popen_factory(argv, **kwargs) -> doi tuong giong Popen (co poll /
    terminate / wait / kill + stdout / stderr). Mac dinh
    subprocess.Popen.
    """

    def __init__(self, popen_factory=None):
        self._popen = popen_factory or subprocess.Popen
        self._procs = {}
        self._lock = threading.Lock()

    def start(self, name, argv, cwd=None, env=None, lang=None):
        """Khoi dong tien trinh `name` (neu chua chay).

        Tra (ok, reason, managed_or_None). Ly do (reason) duoc dich
        theo `lang` ("vi" | "en", mac dinh "vi" — tieng Viet co dau
        day du); ten tien trinh hien thi cung duoc dich qua
        i18n.proc_display_name. Chi tiet ky thuat (exception) giu
        nguyen dang goc. Khong kiem tra thoat som o day —
        webapi._start_proc giu buoc kiem tra do nhu cu.
        """
        lang = normalize_language(lang)
        display = proc_display_name(name, lang)
        with self._lock:
            existing = self._procs.get(name)
            if existing is not None and existing.running:
                return False, t("mgr.proc_running", lang,
                                proc=display), None
            try:
                proc = self._popen(
                    argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, bufsize=1)
            except Exception as exc:  # noqa: BLE001 — spawn loi thi bao ro
                return False, t("mgr.proc_start_failed", lang,
                                proc=display, detail=exc), None
            managed = ManagedProcess(name, proc)
            self._procs[name] = managed
            return True, t("mgr.proc_started", lang,
                           proc=display), managed

    def register(self, name, proc, started_utc=None):
        """Dang ky 1 Popen da spawn san (vd _spawn_proc cua webapi).

        Tra ManagedProcess moi; ghi de muc cu neu ten da co.
        """
        managed = ManagedProcess(name, proc, started_utc=started_utc)
        with self._lock:
            self._procs[name] = managed
        return managed

    def stop(self, name):
        """Dung tien trinh `name` (neu co). Tra True neu da dung /
        khong co / da dung truoc do."""
        with self._lock:
            managed = self._procs.get(name)
        if managed is None:
            return True
        return managed.stop()

    def get(self, name):
        """ManagedProcess theo ten, hoac None neu chua tung chay."""
        with self._lock:
            return self._procs.get(name)

    def status(self, name):
        """Trang thai: {"running","started_utc","exit_code"}.

        Chua tung chay -> running False, started_utc None,
        exit_code None.
        """
        managed = self.get(name)
        if managed is None:
            return {"running": False, "started_utc": None,
                    "exit_code": None}
        return {"running": managed.running,
                "started_utc": managed.started_utc,
                "exit_code": managed.exit_code}

    def lines(self, name, after=0):
        """(total, lines) cua tien trinh `name` sau cursor `after`.

        Chua tung chay -> (0, []).
        """
        managed = self.get(name)
        if managed is None:
            return 0, []
        return managed.lines(after=after)
