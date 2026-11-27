"""Mo hinh GRU hoc ket qua lenh offline cua dx10 (ai/model.py).

VAI TRO (user chot 2026-11-27): mo hinh nay KHONG phai bo tao tin
hieu doc lap — no la mo hinh CHINH THAM SO TA tu log. No hoc anh xa
(context thi truong + tham so TA) -> ket qua lenh, de tra loi "voi
tham so nay trong context nay, xac suat thang la bao nhieu".
Tham so duoc chinh di qua duong de xuat ta-review (kiem chung OOS,
KHONG BAO GIO tu ap); mo hinh khong thay the mo hinh TA quy tac
hay cac gate cung.

Kien truc (tu chon theo nghien cuu da verify 2026-11-27 — KHONG
vendor bat ky thu vien nao; chi tham chieu):
  - GRU (Cho et al. 2014): plain GRU 2 lop, hidden 64, dropout 0.2,
    Linear head -> 3 logits. Bat dau bang GRU don gian; LSTM-FCN
    (Karim et al. 2017, 2019) va InceptionTime (Fawaz et al. 2019)
    la duong nang cap da ghi nhan neu GRU underfit.
  - Dau vao: cua so 32 hang lien tiep (seq_len=32), moi hang =
    35 feature context thi truong (features.py, version 1) + 13
    feature tham so TA (ai/params.py, PARAM_FEATURE_NAMES) = 48 cot.
    Tham so vao mo hinh theo 2 duong: gian tiep qua cac cot chi bao
    (SMA/RSI/ATR/ADX tinh theo tham so ung vien) va truc tiep qua
    vector tham so chuan hoa — nho vay mo hinh moi hoc duoc anh
    huong rieng cua tham so len ket qua.
  - Dau ra: logits (batch, 3), 3 lop ket qua TP/SL-first
    (dataset.py, LABEL_NAMES_TP_SL): ["sl_first", "timeout",
    "tp_first"] (0 = SL cham truoc / thua, 1 = timeout, 2 = TP cham
    truoc / thang — dieu kien theo huong cua mau, meta["direction"]).
    Che do label "direction" (["down", "flat", "up"]) van ho tro
    qua ModelConfig.label_mode, nhung KHONG phai che do chinh.
  - KHONG co head du doan huong rieng: head tp_first theo huong
    mau da du de xep hang ung vien tham so (tune.py); them head
    huong chi trung lap viec cua quy tac TA.

Luu / tai (weights-only, KHONG BAO GIO pickle ca object model):
  - <SYMBOL>.pt: torch.save(state_dict) thuan.
  - <SYMBOL>.json (sidecar): {symbol, label_mode, classes,
    feature_version, feature_names, param_feature_names,
    param_feature_version, mean, std, seq_len, trained_at,
    bars_used, walkforward_metrics, torch_version}.
  - load() doc sidecar truoc, dung no de dung lai mo hinh
    (hyperparams + kiem tra feature version), roi moi
    load_state_dict(..., map_location="cpu", weights_only=True).

Torch la phu thuoc TUY CHON (khong co trong requirements.txt):
import module nay LUON an toan khi chua cai torch; chi khi dung
mo hinh (build / train / load / predict) moi bao loi sach ten
`ai-setup` (chay `python -m diamondx10 ai-setup` de cai).
"""
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODELS_DIR = REPO_ROOT / "data" / "ai-models"

# Lop mac dinh = nhan TP/SL-first cua dataset.py (che do mac dinh
# cua build_dataset). Che do "direction" dung ["down", "flat", "up"].
DEFAULT_CLASSES_TP_SL = ("sl_first", "timeout", "tp_first")
DEFAULT_CLASSES_DIRECTION = ("down", "flat", "up")
DEFAULT_SEQ_LEN = 32


class TorchNotAvailable(RuntimeError):
    """Torch chua cai — bao loi sach, huong ve `ai-setup`."""


class ModelLoadError(ValueError):
    """File weights / sidecar hong hoac khong khop — ghi ro ten file."""


def _torch_import_error():
    """Thong bao loi chuan khi torch thieu (dung o moi cho)."""
    return ("torch chua cai — mo hinh AI can torch CPU. Chay: "
            "python -m diamondx10 ai-setup  (cai torch CPU + numpy + "
            "pandas, ~250MB, chi 1 lan, khong nam trong requirements.txt)")


def require_torch():
    """Import torch (lazy); raise TorchNotAvailable ten `ai-setup`
    neu chua cai. Dung o dau moi ham can torch, KHONG o top-level
    module — de phan con lai cua dx10 khong vo vi thieu torch."""
    try:
        import torch  # noqa: PLC0415 — lazy import co chu y
    except ImportError:
        raise TorchNotAvailable(_torch_import_error()) from None
    return torch


def is_torch_ready():
    """True neu goi `torch` import duoc (find_spec, khong import)."""
    return importlib.util.find_spec("torch") is not None


def install_torch(runner=None):
    """Cai torch CPU + numpy + pandas (lenh `ai-setup`).

    Giong install_playwright (muse_browser.py): runner la ham nhan
    argv, tra object co .returncode (mac dinh subprocess.run) —
    diem tiem cho test. In canh bao kich thuoc truoc khi cai
    (wheel torch CPU ~200MB + numpy/pandas). Khong bao gio raise
    (OSError -> False). Tra True neu pip xong (returncode 0).
    """
    run = runner if runner is not None else subprocess.run
    print("Cai torch CPU + numpy + pandas cho mo hinh AI ...")
    print("CANH BAO: goi torch CPU ~200MB (+ numpy/pandas), tai ve "
          "1 lan, chi dung CPU — khong can GPU, khong nam trong "
          "requirements.txt, khong tu cai khi chay quickstart.")
    try:
        pip = run([sys.executable, "-m", "pip", "install", "torch",
                   "--index-url",
                   "https://download.pytorch.org/whl/cpu",
                   "numpy", "pandas"])
    except OSError as exc:
        print(f"LOI: khong chay duoc pip: {exc}")
        print("Huong dan: cai Python 3.10+ roi chay lai "
              "python -m diamondx10 ai-setup")
        return False
    if pip.returncode != 0:
        print("LOI: pip install torch that bai (xem loi pip o tren).")
        print("Huong dan: kiem tra mang / dung luong trong, roi chay "
              "lai python -m diamondx10 ai-setup")
        return False
    print("OK: da cai torch CPU + numpy + pandas.")
    print("Buoc tiep theo: python -m diamondx10 ai-train --symbol "
          "EURUSD --days 90")
    return True


@dataclass
class ModelConfig:
    """Hyperparams nho cua DirectionGRU (ghi vao sidecar JSON)."""
    n_features: int = 35
    hidden: int = 64
    layers: int = 2
    dropout: float = 0.2
    seq_len: int = DEFAULT_SEQ_LEN
    classes: tuple = field(default_factory=lambda: DEFAULT_CLASSES_TP_SL)
    label_mode: str = "tp_sl"

    def to_dict(self):
        """Dict JSON-hoa duoc (classes ve list)."""
        return {"n_features": int(self.n_features),
                "hidden": int(self.hidden),
                "layers": int(self.layers),
                "dropout": float(self.dropout),
                "seq_len": int(self.seq_len),
                "classes": list(self.classes),
                "label_mode": self.label_mode}

    @classmethod
    def from_dict(cls, data):
        """Dung lai tu dict sidecar (thieu khoa thi dung mac dinh)."""
        data = dict(data or {})
        classes = tuple(data.get("classes") or DEFAULT_CLASSES_TP_SL)
        return cls(n_features=int(data.get("n_features", 35)),
                   hidden=int(data.get("hidden", 64)),
                   layers=int(data.get("layers", 2)),
                   dropout=float(data.get("dropout", 0.2)),
                   seq_len=int(data.get("seq_len", DEFAULT_SEQ_LEN)),
                   classes=classes,
                   label_mode=data.get("label_mode", "tp_sl"))


def _define_model_class(torch):
    """Lop DirectionGRU that — chi dinh nghia khi torch co san."""
    class DirectionGRU(torch.nn.Module):
        """GRU 2 lop + Linear head -> 3 logits.

        forward(x) voi x (batch, seq_len, n_features) tra logits
        (batch, 3). Lay hidden state o buoc thoi gian CUOI (khong
        lay trung binh ca chuoi) roi qua head.
        """
        def __init__(self, config=None, **overrides):
            super().__init__()
            cfg = config or ModelConfig(**overrides)
            self.config = cfg
            # Dropout cua nn.GRU chi co tac dung khi layers > 1;
            # truyen 0 khi 1 lop de tranh warning cua PyTorch.
            gru_dropout = cfg.dropout if cfg.layers > 1 else 0.0
            self.gru = torch.nn.GRU(
                cfg.n_features, cfg.hidden, num_layers=cfg.layers,
                batch_first=True, dropout=gru_dropout)
            self.head = torch.nn.Linear(cfg.hidden, len(cfg.classes))

        def forward(self, x):
            _out, hidden = self.gru(x)
            last = hidden[-1]
            return self.head(last)

    return DirectionGRU


if importlib.util.find_spec("torch") is not None:
    import torch as _torch_mod  # noqa: F401 — chi de dinh nghia lop
    DirectionGRU = _define_model_class(_torch_mod)
else:
    class DirectionGRU:  # type: ignore[no-redef]
        """Cho giu khi chua cai torch: khoi tao bao loi sach.

        Import module van duoc (de dx10 khong vo); chi khi that su
        dung mo hinh moi raise TorchNotAvailable ten `ai-setup`.
        """
        def __init__(self, *args, **kwargs):
            raise TorchNotAvailable(_torch_import_error())


def build_model(config=None, **overrides):
    """Dung DirectionGRU tu ModelConfig (raise TorchNotAvailable
    neu chua cai torch)."""
    require_torch()
    cfg = config or ModelConfig(**overrides)
    return DirectionGRU(cfg)


def _sidecar_defaults():
    """Khoa sidecar luon co (de load cu khong vo vi thieu khoa)."""
    return {"symbol": None, "label_mode": "tp_sl",
            "classes": list(DEFAULT_CLASSES_TP_SL),
            "feature_version": None, "feature_names": None,
            "param_feature_names": None, "param_feature_version": None,
            "mean": None, "std": None, "seq_len": DEFAULT_SEQ_LEN,
            "trained_at": None,
            "bars_used": None, "walkforward_metrics": None,
            "torch_version": None}


def save_model(model, config, sidecar, pt_path, json_path=None):
    """Luu weights + sidecar JSON.

    model: DirectionGRU da train (co .state_dict()). config:
    ModelConfig. sidecar: dict thong tin them (symbol, mean/std,
    metrics... — se gop voi khoa mac dinh + config + torch_version).
    pt_path: duong dan file .pt; json_path: file .json (mac dinh
    cung ten, doi duoi .json). Chi luu state_dict (weights-only),
    KHONG pickle ca object model. Tra (pt_path, json_path) dang
    Path. Raise TorchNotAvailable neu chua cai torch.
    """
    torch = require_torch()
    pt_path = Path(pt_path)
    json_path = (Path(json_path) if json_path is not None
                 else pt_path.with_suffix(".json"))
    pt_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    full = dict(_sidecar_defaults())
    full.update(dict(sidecar or {}))
    full.update(config.to_dict())
    full["trained_at"] = (full.get("trained_at")
                          or datetime.now(timezone.utc).isoformat())
    full["torch_version"] = torch.__version__
    torch.save(model.state_dict(), pt_path)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(full, f, ensure_ascii=False, indent=2)
    return pt_path, json_path


def load_sidecar(json_path):
    """Doc sidecar JSON; loi doc / JSON hong -> ModelLoadError
    ghi ro ten file (khong can torch — doc duoc ca khi torch
    thieu, de lenh CLI bao loi som)."""
    json_path = Path(json_path)
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ModelLoadError(
            f"Khong tim thay file sidecar mo hinh: {json_path} — "
            "train truoc (ai-train) roi tai lai.") from None
    except (OSError, ValueError) as exc:
        raise ModelLoadError(
            f"File sidecar mo hinh hong / khong doc duoc: {json_path} "
            f"({exc}) — xoa file va train lai (ai-train).") from None
    if not isinstance(data, dict):
        raise ModelLoadError(
            f"File sidecar mo hinh khong phai JSON object: {json_path} "
            "— xoa file va train lai (ai-train).")
    return data


def load_model(pt_path, json_path=None):
    """Tai mo hinh: doc sidecar -> dung lai model tu hyperparams
    trong do -> load_state_dict(weights_only=True, CPU).

    Kiem tra feature version / ten cot khop voi features.py hien
    tai (assert_feature_version) TRUOC khi dung weights. Loi file
    (thieu / hong / khong khop state_dict) -> ModelLoadError ghi
    ro ten file. Tra (model, sidecar_dict); model o che do eval().
    """
    pt_path = Path(pt_path)
    json_path = (Path(json_path) if json_path is not None
                 else pt_path.with_suffix(".json"))
    sidecar = load_sidecar(json_path)
    # Kiem tra feature version truoc khi dong den torch/weights.
    try:
        from .features import assert_feature_version
        assert_feature_version(sidecar.get("feature_version"),
                               sidecar.get("feature_names"))
    except ValueError as exc:
        raise ModelLoadError(
            f"Mo hinh {pt_path} khong dung duoc nua: {exc}") from None
    torch = require_torch()
    config = ModelConfig.from_dict(sidecar)
    model = DirectionGRU(config)
    try:
        state = torch.load(pt_path, map_location="cpu",
                           weights_only=True)
    except FileNotFoundError:
        raise ModelLoadError(
            f"Khong tim thay file weights mo hinh: {pt_path} — train "
            "truoc (ai-train) roi tai lai.") from None
    except Exception as exc:  # noqa: BLE001 — torch.load hong nhieu kieu
        raise ModelLoadError(
            f"File weights mo hinh hong / khong tai duoc: {pt_path} "
            f"({type(exc).__name__}: {exc}) — xoa file va train lai "
            "(ai-train).") from None
    try:
        model.load_state_dict(state)
    except Exception as exc:  # noqa: BLE001 — sai shape / thieu khoa
        raise ModelLoadError(
            f"Weights {pt_path} khong khop kien truc trong sidecar "
            f"{json_path} ({type(exc).__name__}: {exc}) — train lai "
            "(ai-train).") from None
    model.eval()
    return model, sidecar


def predict_logits(model, X):
    """Logits (n, 3) cho X dang list (n, seq_len, n_features).

    Khong doi grad (inference). Raise TorchNotAvailable neu chua
    cai torch. X co the la list thuan — khong can numpy.
    """
    torch = require_torch()
    tensor = torch.tensor(X, dtype=torch.float32)
    with torch.no_grad():
        return model(tensor)


def predict_proba(model, X):
    """Xac suat lop (n, 3) — softmax tren logits (tra list thuan,
    khong can numpy)."""
    torch = require_torch()
    logits = predict_logits(model, X)
    probs = torch.softmax(logits, dim=1)
    return probs.tolist()


def model_paths(symbol, models_dir=None):
    """(pt_path, json_path) cho 1 symbol trong thu muc model."""
    base = Path(models_dir) if models_dir is not None \
        else DEFAULT_MODELS_DIR
    return (base / f"{symbol}.pt", base / f"{symbol}.json")


def resolve_models_dir(cfg=None, models_dir=None):
    """Thu muc model: tham so truyen vao > config ai.models_dir >
    mac dinh data/ai-models (theo REPO_ROOT). Duong dan tuong doi
    hieu theo goc repo."""
    if models_dir is not None:
        return Path(models_dir)
    ai_cfg = (cfg or {}).get("ai") or {}
    configured = ai_cfg.get("models_dir")
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else REPO_ROOT / path
    return DEFAULT_MODELS_DIR
