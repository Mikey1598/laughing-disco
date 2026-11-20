#!/usr/bin/env python3
"""ICC (Indication, Correction, Continuation) scanner for gold.

Fetches COMEX gold futures (GC=F) from Yahoo Finance and converts the prices to
approximate spot XAUUSD using a live spot quote. It then works out where the
current ICC setup stands:

    Daily   -> bias (direction of the last daily break of structure)
    4H      -> Indication (break of structure), impulse leg, correction zone
    15m     -> Continuation trigger (break of the pullback's last higher low / lower high)

Usage:
    python3 icc_scanner.py            # human-readable report
    python3 icc_scanner.py --json     # machine-readable report
    python3 icc_scanner.py --state-file PATH   # also says whether the phase changed

The rules are written out in ICC_STRATEGY.md.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

UA = {"User-Agent": "Mozilla/5.0 (icc-scanner)"}
NY = "America/New_York"

# ---- strategy parameters (keep in sync with ICC_STRATEGY.md / icc_gold.pine) ----
PIV_4H = 3          # 4H major swing = bar with 3 lower highs / higher lows each side
PIV_4H_INT = 2      # 4H internal swing (nearer, smaller structure)
PIV_D = 3           # daily swing
PIV_15 = 2          # 15m swing (continuation trigger for 4H setups)
PIV_W = 2           # weekly swing (bias for the daily setup)
PIV_4H_TRIG = 2     # 4H swing (continuation trigger for daily setups)
FIB_MIN = 0.382     # correction has started once price retraces this far
FIB_ZONE = (0.5, 0.786)  # prime correction zone
STOP_BUF = 5.0      # $ beyond correction extreme
RR = 2.0            # TP1 in R


def fetch(symbol: str, interval: str, rng: str) -> pd.DataFrame:
    data, err = None, None
    for attempt in range(6):  # Yahoo rate-limits bursts: rotate hosts and back off
        host = ("query1", "query2")[attempt % 2]
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={rng}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                data = json.load(r)
            break
        except Exception as e:
            err = e
            time.sleep(2 * (attempt + 1))
    if data is None:
        raise RuntimeError(f"could not fetch {symbol} {interval}: {err}")
    res = data["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame(
        {"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"]},
        index=pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(NY),
    ).dropna()
    return df


def spot_price() -> float | None:
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.gold-api.com/price/XAU", headers=UA), timeout=15) as r:
            return float(json.load(r)["price"])
    except Exception:
        return None


def to_4h(h1: pd.DataFrame) -> pd.DataFrame:
    # FX-style 4H candles that open at 17:00 New York time (17, 21, 01, 05, 09, 13).
    # Bin on New York wall-clock time so DST changes don't shift the candles.
    wall = h1.index.tz_localize(None)
    key = (wall - pd.Timedelta(hours=17)).floor("4h") + pd.Timedelta(hours=17)
    out = h1.groupby(key).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    return out


def pivots(df: pd.DataFrame, n: int):
    """Return lists of (confirm_idx, pivot_idx, price) for swing highs and lows."""
    hs, ls = [], []
    H, L = df["high"].values, df["low"].values
    for i in range(n, len(df) - n):
        if H[i] == max(H[i - n:i + n + 1]) and H[i] > max(H[i - n:i]):
            hs.append((i + n, i, H[i]))
        if L[i] == min(L[i - n:i + n + 1]) and L[i] < min(L[i - n:i]):
            ls.append((i + n, i, L[i]))
    return hs, ls


@dataclass
class Setup:
    direction: str = "none"          # "short" / "long" / "none"
    phase: str = "WAITING"           # WAITING, INDICATION, CORRECTION, CONTINUATION, INVALIDATED
    indication_time: str = ""
    broken_level: float = 0.0
    origin: float = 0.0              # invalidation level
    impulse: float = 0.0             # extreme of the impulse leg
    shallow_zone: tuple = ()
    zone: tuple = ()
    correction_extreme: float = 0.0
    trigger: float = 0.0
    entry: float = 0.0
    stop: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    notes: list = field(default_factory=list)


def structure_bias(df: pd.DataFrame, n: int) -> str:
    """Direction of the most recent close-based break of structure."""
    hs, ls = pivots(df, n)
    C = df["close"].values
    bias = "none"
    last_h = last_l = None
    hi = li = 0
    for i in range(len(df)):
        while hi < len(hs) and hs[hi][0] <= i:
            last_h = hs[hi][2]; hi += 1
        while li < len(ls) and ls[li][0] <= i:
            last_l = ls[li][2]; li += 1
        if last_h is not None and C[i] > last_h:
            bias, last_h = "bullish", None
        if last_l is not None and C[i] < last_l:
            bias, last_l = "bearish", None
    return bias


def analyse_4h(df: pd.DataFrame, piv: int = PIV_4H) -> Setup:
    hs, ls = pivots(df, piv)
    H, L, C = df["high"].values, df["low"].values, df["close"].values
    s = Setup()
    last_h = last_l = None  # (pivot_idx, price)
    hi = li = 0
    corr_bar = None
    for i in range(len(df)):
        while hi < len(hs) and hs[hi][0] <= i:
            last_h = (hs[hi][1], hs[hi][2]); hi += 1
        while li < len(ls) and ls[li][0] <= i:
            last_l = (ls[li][1], ls[li][2]); li += 1

        bear_bos = last_l is not None and C[i] < last_l[1]
        bull_bos = last_h is not None and C[i] > last_h[1]

        if bear_bos and (s.direction != "short" or s.phase != "CORRECTION"):
            # new bearish BOS: fresh setup, or the indication refreshes to the newest leg
            origin = max(H[last_l[0]:i + 1])
            s = Setup(direction="short", phase="INDICATION", indication_time=str(df.index[i]),
                      broken_level=last_l[1], origin=origin, impulse=L[i])
            last_l = None
            corr_bar = None
            continue
        if bull_bos and (s.direction != "long" or s.phase != "CORRECTION"):
            origin = min(L[last_h[0]:i + 1])
            s = Setup(direction="long", phase="INDICATION", indication_time=str(df.index[i]),
                      broken_level=last_h[1], origin=origin, impulse=H[i])
            last_h = None
            corr_bar = None
            continue
        if bear_bos:
            last_l = None
        if bull_bos:
            last_h = None

        if s.direction == "short" and s.phase in ("INDICATION", "CORRECTION"):
            if C[i] > s.origin:
                s.phase = "INVALIDATED"; continue
            rng = s.origin - s.impulse
            if s.phase == "INDICATION":
                if L[i] < s.impulse:
                    s.impulse = L[i]
                elif rng > 0 and (H[i] - s.impulse) / rng >= FIB_MIN:
                    s.phase, s.correction_extreme, s.trigger, corr_bar = "CORRECTION", H[i], L[i], i
            elif s.phase == "CORRECTION":
                if H[i] > s.correction_extreme:
                    s.correction_extreme, s.trigger = H[i], L[i]
                elif C[i] < s.trigger:
                    s.phase = "CONTINUATION"
                    s.entry, s.stop = C[i], s.correction_extreme + STOP_BUF
        elif s.direction == "long" and s.phase in ("INDICATION", "CORRECTION"):
            if C[i] < s.origin:
                s.phase = "INVALIDATED"; continue
            rng = s.impulse - s.origin
            if s.phase == "INDICATION":
                if H[i] > s.impulse:
                    s.impulse = H[i]
                elif rng > 0 and (s.impulse - L[i]) / rng >= FIB_MIN:
                    s.phase, s.correction_extreme, s.trigger, corr_bar = "CORRECTION", L[i], H[i], i
            elif s.phase == "CORRECTION":
                if L[i] < s.correction_extreme:
                    s.correction_extreme, s.trigger = L[i], H[i]
                elif C[i] > s.trigger:
                    s.phase = "CONTINUATION"
                    s.entry, s.stop = C[i], s.correction_extreme - STOP_BUF

    # projected zones from the (current) impulse leg
    if s.direction == "short":
        rng = s.origin - s.impulse
        s.shallow_zone = (s.impulse + 0.382 * rng, s.impulse + 0.5 * rng)
        s.zone = (s.impulse + FIB_ZONE[0] * rng, s.impulse + FIB_ZONE[1] * rng)
        s.tp2 = s.impulse
    elif s.direction == "long":
        rng = s.impulse - s.origin
        s.shallow_zone = (s.impulse - 0.5 * rng, s.impulse - 0.382 * rng)
        s.zone = (s.impulse - FIB_ZONE[1] * rng, s.impulse - FIB_ZONE[0] * rng)
        s.tp2 = s.impulse
    if s.phase == "CONTINUATION":
        risk = abs(s.entry - s.stop)
        s.tp1 = s.entry - RR * risk if s.direction == "short" else s.entry + RR * risk
    s._corr_time = df.index[corr_bar] if corr_bar is not None else None  # type: ignore[attr-defined]
    return s


def ltf_trigger(ltf: pd.DataFrame, s: Setup, piv: int = PIV_15):
    """While correcting, the continuation trigger = last lower-timeframe swing low (short) /
    swing high (long) formed since the correction began. Returns (level, fired)."""
    start = getattr(s, "_corr_time", None)
    if s.phase != "CORRECTION" or start is None:
        return None, False
    sub = ltf[ltf.index >= start]
    if len(sub) < 2 * piv + 1:
        return None, False
    hs, ls = pivots(sub, piv)
    if s.direction == "short":
        ext_i = int(sub["high"].values.argmax())
        cands = [p for p in ls if p[1] < ext_i]  # higher low before the correction high
        if not cands:
            return None, False
        lvl = cands[-1][2]
        fired = bool((sub["close"].values[ext_i + 1:] < lvl).any())
    else:
        ext_i = int(sub["low"].values.argmin())
        cands = [p for p in hs if p[1] < ext_i]
        if not cands:
            return None, False
        lvl = cands[-1][2]
        fired = bool((sub["close"].values[ext_i + 1:] > lvl).any())
    return lvl, fired


def run() -> dict:
    h1 = fetch("GC=F", "60m", "60d")
    m15 = fetch("GC=F", "15m", "5d")
    d1 = fetch("GC=F", "1d", "1y")
    spot = spot_price()
    last_fut = float(m15["close"].iloc[-1])
    offset = (spot - last_fut) if spot else 0.0
    for df in (h1, m15, d1):
        df[["open", "high", "low", "close"]] += offset
    h4 = to_4h(h1)

    bias = structure_bias(d1, PIV_D)
    wk = d1.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    wbias = structure_bias(wk, PIV_W)
    price = float(m15["close"].iloc[-1])
    return {
        "daily": build(analyse_4h(d1, PIV_D), h4, wbias, price, offset, spot,
                       tf="Daily", ltf="4H", bias_tf="Weekly", ltf_piv=PIV_4H_TRIG),
        "major": build(analyse_4h(h4, PIV_4H), m15, bias, price, offset, spot),
        "internal": build(analyse_4h(h4, PIV_4H_INT), m15, bias, price, offset, spot),
    }


def build(s: Setup, ltf_df: pd.DataFrame, bias: str, price: float, offset: float, spot,
          tf: str = "4H", ltf: str = "15m", bias_tf: str = "Daily", ltf_piv: int = PIV_15) -> dict:
    trig, fired = ltf_trigger(ltf_df, s, ltf_piv)
    if trig is not None:
        s.trigger = trig
        if fired:
            s.phase = "CONTINUATION"
            s.entry = float(ltf_df["close"].iloc[-1])
            s.stop = s.correction_extreme + STOP_BUF if s.direction == "short" else s.correction_extreme - STOP_BUF
            risk = abs(s.entry - s.stop)
            s.tp1 = s.entry - RR * risk if s.direction == "short" else s.entry + RR * risk

    aligned = (s.direction == "short" and bias == "bearish") or (s.direction == "long" and bias == "bullish")
    grade = f"A (with {bias_tf.lower()} trend)" if aligned else "B (counter-trend: half size)"
    if s.direction == "short" and s.phase == "INDICATION" and s.zone and price >= s.shallow_zone[0]:
        s.notes.append(f"Price is already in the shallow correction area: watch the {ltf} chart.")
    if s.direction == "long" and s.phase == "INDICATION" and s.zone and price <= s.shallow_zone[1]:
        s.notes.append(f"Price is already in the shallow correction area: watch the {ltf} chart.")

    out = asdict(s)
    out.update({
        "as_of": datetime.now(timezone.utc).astimezone(pd.Timestamp.now(tz=NY).tzinfo).strftime("%Y-%m-%d %H:%M ET"),
        "price": round(price, 2),
        "spot_quote": spot,
        "futures_to_spot_offset": round(offset, 2),
        "daily_bias": bias,
        "bias_tf": bias_tf,
        "tf": tf,
        "entry_tf": ltf,
        "grade": grade,
        "state_key": f"{s.direction}|{s.phase}|{s.indication_time}",
    })
    for k in ("broken_level", "origin", "impulse", "correction_extreme", "trigger", "entry", "stop", "tp1", "tp2"):
        out[k] = round(out[k], 2)
    out["shallow_zone"] = [round(x, 2) for x in s.shallow_zone]
    out["zone"] = [round(x, 2) for x in s.zone]
    return out


def report(r: dict) -> str:
    d, p = r["direction"], r["phase"]
    side = "SHORT" if d == "short" else "LONG" if d == "long" else "-"
    lines = [
        f"ICC scan · XAUUSD ≈ {r['price']}  ({r['as_of']})",
        f"{r['bias_tf']} bias: {r['daily_bias']}   Setup: {side}   Grade: {r['grade']}",
        f"Phase: {p}",
        "",
        f"1) INDICATION  : {r['tf']} close through {r['broken_level']} at {r['indication_time']}",
        f"   Origin / invalidation: {r['origin']}   Impulse extreme: {r['impulse']}",
        f"2) CORRECTION  : shallow {r['shallow_zone'][0] if r['shallow_zone'] else '-'}–{r['shallow_zone'][1] if r['shallow_zone'] else '-'}"
        f" | prime {r['zone'][0] if r['zone'] else '-'}–{r['zone'][1] if r['zone'] else '-'}",
    ]
    if p in ("CORRECTION", "CONTINUATION"):
        lines.append(f"   Correction extreme so far: {r['correction_extreme']}")
    trig = r["trigger"] if r["trigger"] else "forms once the correction starts"
    lines.append(f"3) CONTINUATION: {r['entry_tf']} close {'below' if d == 'short' else 'above'} {trig}")
    if p == "CONTINUATION":
        lines.append(f"   ENTRY {r['entry']}  STOP {r['stop']}  TP1 {r['tp1']}  TP2 {r['tp2']}")
    if p == "INVALIDATED":
        lines.append(f"   Setup invalidated: wait for a new {r['tf']} break of structure.")
    lines += [f"Note: {n}" for n in r["notes"]]
    lines.append(f"(Prices = COMEX futures shifted by {r['futures_to_spot_offset']:+} to match spot.)")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--state-file")
    a = ap.parse_args()
    try:
        r = run()
    except Exception as e:  # network / data problems
        print(f"ICC scan failed: {e}", file=sys.stderr)
        sys.exit(2)
    key = " || ".join(f"{k}:{r[k]['state_key']}" for k in ("daily", "major", "internal"))
    if a.state_file:
        sf = Path(a.state_file)
        prev = sf.read_text().strip() if sf.exists() else ""
        r["changed"] = prev != key
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(key)
    if a.json:
        print(json.dumps(r, indent=2, default=str))
    else:
        print("=== DAILY setup (daily swings, 4H entry trigger) ===")
        print(report(r["daily"]))
        print()
        print("=== INTERNAL setup (nearer, smaller 4H swings) ===")
        print(report(r["internal"]))
        print()
        print("=== MAJOR setup (bigger 4H swings) ===")
        print(report(r["major"]))
        if a.state_file:
            print()
            print("PHASE CHANGED" if r["changed"] else "no phase change")


if __name__ == "__main__":
    main()
