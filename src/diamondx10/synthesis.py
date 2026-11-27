"""Nhan dinh co ban (PTCB) theo desk + tong hop Yuling (PTKT + PTCB).

Yuling la nguoi tong hop cuoi: tin hieu ky thuat (PTKT) chi duoc
thanh lenh khi co nhan dinh co ban (PTCB) moi cua desk do dong
thuan hoac khong mau thuan manh. PTCB mot minh KHONG bao gio tao
lenh vao (TA HOLD thi CHO du PTCB co manh den dau).

Nhan dinh luu o decisions/fundamental-verdicts.json (goc repo, cung
quy uoc duong dan nhu decisions.py / killswitch.py: goc repo =
parents[2] cua file nay). File nay la file RUNTIME (nhan dinh moi
theo ngay) — khong commit.

Quy tac tong hop (xem docs/trading-principles.md, muc 37):
  PTKT BUY + PTCB buy tin cay cao -> MUA size 1.0
  PTKT BUY + PTCB buy tin cay thap / neutral -> MUA size 0.5
  PTKT BUY + PTCB sell tin cay cao -> KHONG MUA (chan), size 0
  PTKT BUY + PTCB sell tin cay thap -> MUA size 0.5 (canh bao)
  PTKT SELL doi xung. PTKT HOLD + PTCB bat ky -> CHO, size 0.
  PTCB thieu hoac qua han: size 0.5 theo PTKT; neu require_fa thi
  chan (KHONG MUA, size 0, blocked True).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

DESKS = ("forex", "xauusd", "crypto", "us_securities")
DIRECTIONS = ("buy", "sell", "neutral")
TA_ACTIONS = ("BUY", "SELL", "HOLD")

VERDICT_STORE = (Path(__file__).resolve().parents[2] / "decisions"
                 / "fundamental-verdicts.json")

DEFAULT_SYNTHESIS = {"verdict_max_age_hours": 24, "require_fa": False,
                     "fa_high_confidence": 0.6}


def _synthesis_cfg(cfg):
    """Muc `synthesis:` trong config, gop voi mac dinh."""
    merged = dict(DEFAULT_SYNTHESIS)
    merged.update((cfg or {}).get("synthesis") or {})
    return merged


def _parse_created_utc(value, field="created_utc"):
    """Parse ISO timestamp thanh datetime UTC; loi thi ValueError ro rang."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} khong phai chuoi ISO hop le: {value!r}")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"{field} khong doc duoc (can ISO, vd 2026-11-27T10:00:00Z): "
            f"{value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _now_utc_iso():
    return datetime.now(timezone.utc).isoformat()


def validate_verdict(data):
    """Kiem tra 1 nhan dinh PTCB, tra dict da chuan hoa.

    Schema: {desk, analyst, direction: buy|sell|neutral,
    confidence: float 0..1, drivers: [str], risks: [str], note: str,
    created_utc: ISO timestamp}. Thieu created_utc thi dien gio UTC
    hien tai. Bat ky loi nao cung raise ValueError voi thong bao ro
    rang (khong traceback o CLI — cmd_verdict bat va in sach).
    """
    if not isinstance(data, dict):
        raise ValueError("Nhan dinh phai la 1 object JSON (dict), "
                         f"nhan {type(data).__name__}.")
    desk = data.get("desk")
    if not isinstance(desk, str) or desk not in DESKS:
        raise ValueError(
            f"desk khong hop le: {desk!r} (chon trong {list(DESKS)})")
    analyst = data.get("analyst")
    if not isinstance(analyst, str) or not analyst.strip():
        raise ValueError("Thieu analyst (ten nguoi dua nhan dinh, vd "
                         "'Yuling Pan').")
    direction = data.get("direction")
    if not isinstance(direction, str) or direction not in DIRECTIONS:
        raise ValueError(
            f"direction khong hop le: {direction!r} "
            f"(chon buy | sell | neutral)")
    confidence = data.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError(
            f"confidence phai la so 0..1, nhan {confidence!r}")
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(
            f"confidence phai trong 0..1, nhan {confidence!r}")
    drivers = data.get("drivers", [])
    if not isinstance(drivers, list):
        raise ValueError(f"drivers phai la list, nhan {type(drivers).__name__}.")
    if not all(isinstance(d, str) for d in drivers):
        raise ValueError("drivers phai la list cac chuoi.")
    risks = data.get("risks", [])
    if not isinstance(risks, list):
        raise ValueError(f"risks phai la list, nhan {type(risks).__name__}.")
    if not all(isinstance(r, str) for r in risks):
        raise ValueError("risks phai la list cac chuoi.")
    note = data.get("note", "")
    if not isinstance(note, str):
        raise ValueError(f"note phai la chuoi, nhan {type(note).__name__}.")
    created = data.get("created_utc")
    if created is None:
        created_utc = _now_utc_iso()
    else:
        created_utc = _parse_created_utc(created).isoformat()
    return {"desk": desk, "analyst": analyst.strip(),
            "direction": direction, "confidence": confidence,
            "drivers": list(drivers), "risks": list(risks),
            "note": note, "created_utc": created_utc}


def _store_path(path=None):
    return Path(path) if path is not None else VERDICT_STORE


def load_verdicts(store_path=None):
    """Doc kho nhan dinh -> {desk: verdict}. File chua co thi {}."""
    path = _store_path(store_path)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ValueError(f"Khong doc duoc kho nhan dinh {path}: {exc}")
    if isinstance(raw, dict) and isinstance(raw.get("verdicts"), list):
        items = raw["verdicts"]
    elif isinstance(raw, dict):
        items = list(raw.values())
    else:
        raise ValueError(f"Kho nhan dinh {path} sai dinh dang "
                         "(can object {desk: verdict} hoac "
                         "{'verdicts': [...]})")
    out = {}
    for item in items:
        verdict = validate_verdict(item)
        desk = verdict["desk"]
        if (desk not in out or _parse_created_utc(verdict["created_utc"])
                > _parse_created_utc(out[desk]["created_utc"])):
            out[desk] = verdict
    return out


def load_verdict(store_path, desk):
    """Nhan dinh moi nhat cua 1 desk, hoac None neu chua co."""
    return load_verdicts(store_path).get(desk)


def save_verdict(verdict, store_path=None):
    """Luu 1 nhan dinh, gop theo desk, giu ban moi nhat moi desk.

    Tra nhan dinh dang luu cho desk do (co the la ban cu neu ban moi
    cu hon ban da luu)."""
    cleaned = validate_verdict(verdict)
    path = _store_path(store_path)
    verdicts = load_verdicts(path)
    desk = cleaned["desk"]
    current = verdicts.get(desk)
    if current is None or (_parse_created_utc(cleaned["created_utc"])
                           > _parse_created_utc(current["created_utc"])):
        verdicts[desk] = cleaned
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(verdicts, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return verdicts[desk]


def synthesize(ta_action, fa_direction, fa_confidence, cfg, *,
               verdict_age_hours=None):
    """Tong hop Yuling: PTKT + PTCB -> khuyen nghi + he so size.

    ta_action: "BUY" | "SELL" | "HOLD". fa_direction: "buy" | "sell" |
    "neutral" | None (None = chua co PTCB). fa_confidence: float 0..1
    (None = 0.0). verdict_age_hours: tuoi cua nhan dinh PTCB (gio);
    None + co huong PTCB = tuoi khong ro, coi nhu PTCB co; None +
    khong co huong PTCB = chua co PTCB. Qua han verdict_max_age_hours
    thi coi nhu chua co PTCB. Tra dict {recommendation, size, blocked,
    rationale, fa_status}.
    """
    if not isinstance(ta_action, str):
        raise ValueError(f"ta_action khong hop le: {ta_action!r}")
    ta = ta_action.strip().upper()
    if ta not in TA_ACTIONS:
        raise ValueError(f"ta_action khong hop le: {ta_action!r} "
                         "(chon BUY | SELL | HOLD)")
    fa = None
    if fa_direction is not None:
        if not isinstance(fa_direction, str):
            raise ValueError(f"fa_direction khong hop le: {fa_direction!r}")
        fa = fa_direction.strip().lower()
        if fa not in DIRECTIONS:
            raise ValueError(f"fa_direction khong hop le: {fa_direction!r} "
                             "(chon buy | sell | neutral)")
    if fa_confidence is None:
        conf = 0.0
    else:
        if isinstance(fa_confidence, bool) or not isinstance(
                fa_confidence, (int, float)):
            raise ValueError(
                f"fa_confidence phai la so 0..1, nhan {fa_confidence!r}")
        conf = float(fa_confidence)
        if not 0.0 <= conf <= 1.0:
            raise ValueError(
                f"fa_confidence phai trong 0..1, nhan {conf!r}")
    syn = _synthesis_cfg(cfg)
    max_age = float(syn.get("verdict_max_age_hours", 24))
    require_fa = bool(syn.get("require_fa", False))
    high_conf = float(syn.get("fa_high_confidence", 0.6))

    fa_label = f"{fa} (tin cay {conf:g})" if fa is not None else "chua co"
    base = f"PTKT: {ta}; PTCB: {fa_label}"

    # PTCB thieu hoac qua han -> coi nhu chua co PTCB moi.
    missing = fa is None
    stale = False
    if (fa is not None and verdict_age_hours is not None
            and float(verdict_age_hours) > max_age):
        missing, stale = True, True
    if missing:
        fa_status = "stale" if stale else "missing"
        age_note = (f"nhan dinh cu hon {max_age:g} gio" if stale
                    else f"khong co nhan dinh moi trong {max_age:g} gio")
        rationale = (f"{base} — chua co PTCB moi ({age_note}); "
                     "chi dung PTKT, giam size mot nua." if ta != "HOLD"
                     else f"{base} — chua co PTCB moi ({age_note}); "
                     "PTKT HOLD nen cho.")
        if ta == "HOLD":
            return {"recommendation": "CHO", "size": 0.0, "blocked": False,
                    "rationale": rationale, "fa_status": fa_status}
        if require_fa:
            return {"recommendation": "KHONG MUA", "size": 0.0,
                    "blocked": True,
                    "rationale": rationale + " Yeu cau PTCB moi (require_fa) "
                    "nen chan khong vao lenh.",
                    "fa_status": fa_status}
        rec = "MUA" if ta == "BUY" else "BAN"
        return {"recommendation": rec, "size": 0.5, "blocked": False,
                "rationale": rationale, "fa_status": fa_status}

    # PTCB co va con moi.
    if ta == "HOLD":
        return {"recommendation": "CHO", "size": 0.0, "blocked": False,
                "rationale": base + " — PTKT HOLD nen cho; PTCB mot minh "
                "khong tao lenh vao.",
                "fa_status": "ok"}
    aligned = (ta == "BUY" and fa == "buy") or (ta == "SELL" and fa == "sell")
    opposed = (ta == "BUY" and fa == "sell") or (ta == "SELL" and fa == "buy")
    rec = "MUA" if ta == "BUY" else "BAN"
    if aligned:
        if conf >= high_conf:
            return {"recommendation": rec, "size": 1.0, "blocked": False,
                    "rationale": base + " — PTKT va PTCB dong thuan manh, "
                    "vao du size.",
                    "fa_status": "ok"}
        return {"recommendation": rec, "size": 0.5, "blocked": False,
                "rationale": base + " — PTKT va PTCB dong thuan nhung tin "
                "cay thap, giam size mot nua.",
                "fa_status": "ok"}
    if opposed:
        if conf >= high_conf:
            return {"recommendation": "KHONG MUA", "size": 0.0,
                    "blocked": True,
                    "rationale": base + " — PTCB mau thuan manh voi PTKT, "
                    "chan khong vao lenh.",
                    "fa_status": "ok"}
        return {"recommendation": rec, "size": 0.5, "blocked": False,
                "rationale": base + " — canh bao: PTCB nguoc chieu PTKT "
                "nhung tin cay thap, giam size mot nua.",
                "fa_status": "ok"}
    # FA neutral.
    return {"recommendation": rec, "size": 0.5, "blocked": False,
            "rationale": base + " — PTCB trung lap, PTKT dan dat, "
            "giam size mot nua.",
            "fa_status": "ok"}


def _verdict_age_hours(verdict, now=None):
    """Tuoi cua nhan dinh (gio) tinh tu created_utc; None neu khong co."""
    if verdict is None:
        return None
    now = now or datetime.now(timezone.utc)
    created = _parse_created_utc(verdict["created_utc"])
    return (now - created).total_seconds() / 3600.0


def cmd_verdict(cfg, file, *, store_path=None):
    """Luu nhan dinh PTCB tu file JSON. Tra 0 neu luu duoc, 1 neu loi.

    File chua 1 nhan dinh hoac {"verdicts": [...]}. Loi doc file hay
    nhan dinh khong hop le deu in thong bao tieng Viet ro rang (khong
    traceback) va tra 1; khong luu gi khi co loi.
    """
    path = Path(file)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"LOI: khong tim thay file {file}")
        return 1
    except (OSError, ValueError) as exc:
        print(f"LOI: khong doc duoc file {file}: {exc}")
        return 1
    if isinstance(raw, dict) and isinstance(raw.get("verdicts"), list):
        items = raw["verdicts"]
    elif isinstance(raw, dict):
        items = [raw]
    else:
        print("LOI: file phai chua 1 nhan dinh (object) hoac "
              '{"verdicts": [...]}.')
        return 1
    if not items:
        print("LOI: file khong co nhan dinh nao.")
        return 1
    try:
        verdicts = [validate_verdict(item) for item in items]
    except ValueError as exc:
        print(f"LOI: nhan dinh khong hop le — {exc}")
        return 1
    store = _store_path(store_path)
    for verdict in verdicts:
        save_verdict(verdict, store)
        print(f"Da luu nhan dinh: desk {verdict['desk']} — "
              f"analyst {verdict['analyst']} — "
              f"direction {verdict['direction']} "
              f"(tin cay {verdict['confidence']:g})")
    print(f"Kho nhan dinh: {store}")
    return 0


def cmd_synthesize(cfg, desk="forex", symbol=None, *, store_path=None,
                   out_path=None, feed_factory=None):
    """Tong hop Yuling cho 1 desk: PTKT tu feed + PTCB da luu.

    In khuyen nghi moi symbol (recommendation, he so size, rationale
    ghi ca PTKT + PTCB) va luu JSON ra
    decisions/synthesis-<YYYYMMDD>.json (hoac out_path neu truyen).
    Tren may khong co MT5 (provider mt5) thi bao loi sach, tra 1,
    khong traceback. Tra 0 neu xong.
    """
    cfg = cfg or {}
    if desk not in DESKS:
        print(f"LOI: desk khong hop le: {desk!r} "
              f"(chon trong {list(DESKS)})")
        return 1
    if symbol:
        symbols = [symbol]
    else:
        symbols = list((cfg.get("data", {}).get("symbols", {}) or {})
                       .get(desk) or [])
    if not symbols:
        print(f"LOI: chua cau hinh symbol cho desk {desk!r} trong "
              "config.yaml")
        return 1
    try:
        verdicts = load_verdicts(store_path)
    except ValueError as exc:
        print(f"LOI: {exc}")
        return 1
    verdict = verdicts.get(desk)
    age = _verdict_age_hours(verdict)
    fa_direction = verdict["direction"] if verdict else None
    fa_confidence = verdict["confidence"] if verdict else None

    from .data.providers import build_feed
    from .signals import generate_signals

    results, errors = [], []
    for sym in symbols:
        feed = None
        try:
            if feed_factory is not None:
                feed = feed_factory(sym)
            else:
                feed = build_feed(cfg, desk, symbol=sym)
            bars = feed.bars(60)
            sig = generate_signals(desk, bars, symbol=sym, cfg=cfg)
            ta_action = sig["action"]
        except (ImportError, ConnectionError, ValueError) as exc:
            print(f"LOI ({sym}): {exc}")
            errors.append({"symbol": sym, "error": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001 — 1 symbol loi khong crash
            print(f"LOI ({sym}): {exc}")
            errors.append({"symbol": sym, "error": str(exc)})
            continue
        finally:
            close = getattr(feed, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 — dong feed loi thi thoi
                    pass
        try:
            syn = synthesize(ta_action, fa_direction, fa_confidence, cfg,
                             verdict_age_hours=age)
        except ValueError as exc:
            print(f"LOI ({sym}): {exc}")
            errors.append({"symbol": sym, "error": str(exc)})
            continue
        entry = {"symbol": sym, "desk": desk, "ta_action": ta_action,
                 "fa_direction": fa_direction,
                 "fa_confidence": fa_confidence,
                 "fa_status": syn["fa_status"],
                 "recommendation": syn["recommendation"],
                 "size": syn["size"], "blocked": syn["blocked"],
                 "rationale": syn["rationale"]}
        results.append(entry)
        print(f"{sym}: PTKT {ta_action} -> {syn['recommendation']} "
              f"(size {syn['size']:g}) — {syn['rationale']}")
    out = {
        "date": datetime.now(timezone.utc).strftime("%Y%m%d"),
        "desk": desk,
        "verdict": verdict,
        "results": results,
        "errors": errors,
    }
    out_file = (Path(out_path) if out_path is not None
                else Path(__file__).resolve().parents[2] / "decisions"
                / f"synthesis-{out['date']}.json")
    try:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    except OSError as exc:
        print(f"LOI: khong ghi duoc ket qua ra {out_file}: {exc}")
        return 1
    print(f"Da luu tong hop: {out_file}")
    if errors:
        print(f"Co {len(errors)}/{len(symbols)} symbol loi.")
        return 1
    return 0
