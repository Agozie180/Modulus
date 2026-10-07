"""The Monday Oracle - Modulus seals its forecast of Monday's open BEFORE Wall Street wakes up,
and lets reality grade it on-chain.

  forecast  : for every bStock, P(real stock opens Monday above Friday's close) and the expected gap,
              from the dark-weekend token move, shrunk by the measured betas (market 1x-ish, idio ~0.5x)
  commit    : Merkle root of all forecasts + secret salt -> sha256 commitment -> WeekendOracle.commit()
              on BSC (contracts/WeekendOracle.sol). Nobody, including us, can edit it after the fact.
  reveal    : Monday after 13:30 UTC publish root + salt (+ any single forecast with its Merkle proof)
  grade     : real Monday open vs Friday close -> hit rate, Brier score, MAE vs the 'no change' forecast.
              Appended to oracle/scoreboard.json and fed back into the calibration curve.

Seed data: research/data24/oracle_rows.json (858 stock-weekends, 17 weekends).
"""
from __future__ import annotations
import hashlib, json, math, os, secrets, statistics as st, urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..")
ROWS = os.path.join(ROOT, "research", "data24", "oracle_rows.json")
OUT = os.path.join(ROOT, "oracle")


def _load(path):
    """Read a JSON seed file, falling back to its .gz twin (the repo ships the compressed copy)."""
    import gzip
    if os.path.exists(path):
        return json.load(open(path))
    with gzip.open(path + ".gz", "rt") as f:
        return json.load(f)


def _rows():
    try:
        return [r for r in _load(ROWS) if r.get("w_sun21") is not None]
    except FileNotFoundError:
        return []


def fit(rows=None):
    """Betas (market, idio) and a bucketed sign-probability table, all from history."""
    rows = rows if rows is not None else _rows()
    if not rows:
        return {"b_mkt": 0.9, "b_idio": 0.52, "table": [(0.0, 0.5)]}
    wk = {}
    for r in rows:
        wk.setdefault(r["fri"], []).append(r)
    mk = {w: (st.mean(x["w_sun21"] for x in v), st.mean(x["g"] for x in v)) for w, v in wk.items()}
    xs, ys = [m[0] for m in mk.values()], [m[1] for m in mk.values()]
    b_m = sum(a * b for a, b in zip(xs, ys)) / max(1e-12, sum(a * a for a in xs))
    ii = [(r["w_sun21"] - mk[r["fri"]][0], r["g"] - mk[r["fri"]][1]) for r in rows]
    b_i = sum(a * b for a, b in ii) / max(1e-12, sum(a * a for a, _ in ii))
    fc = [(b_m * mk[r["fri"]][0] + b_i * (r["w_sun21"] - mk[r["fri"]][0]), r["g"]) for r in rows]
    table = [(0.0, 0.5)]                   # below 50 bps the Oracle abstains (coin-flip territory)
    for lo in (0.005, 0.01, 0.02):
        c = [(f, g) for f, g in fc if abs(f) >= lo and g != 0]
        if len(c) >= 30:
            hit = sum((f > 0) == (g > 0) for f, g in c) / len(c)
            table.append((lo, round(min(0.8, 0.5 + (hit - 0.5) * len(c) / (len(c) + 20)), 4)))
    return {"b_mkt": round(b_m, 4), "b_idio": round(b_i, 4), "table": table}


def p_up(gap_hat: float, model) -> float:
    conf = [p for lo, p in model["table"] if abs(gap_hat) >= lo][-1]
    return conf if gap_hat > 0 else 1 - conf


def forecast(token_moves: dict[str, float], model=None) -> dict:
    """token_moves: {ticker: token price now / token price at Friday's US close - 1}."""
    model = model or fit()
    m = st.mean(token_moves.values()) if token_moves else 0.0
    out = {}
    for t, w in sorted(token_moves.items()):
        g = model["b_mkt"] * m + model["b_idio"] * (w - m)
        out[t] = {"token_move_bps": round(w * 1e4, 1), "gap_hat_bps": round(g * 1e4, 1), "p_up": round(p_up(g, model), 4)}
    return out


# ---------- commit / reveal (Merkle) ----------
def _h(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def leaf(week: str, ticker: str, f: dict) -> bytes:
    return _h(f"{week}|{ticker}|{f['gap_hat_bps']}|{f['p_up']}".encode())


def merkle(leaves: list[bytes]) -> tuple[bytes, list[list[bytes]]]:
    levels = [leaves[:] or [_h(b"")]]
    while len(levels[-1]) > 1:
        cur = levels[-1] + ([levels[-1][-1]] if len(levels[-1]) % 2 else [])
        levels.append([_h(min(a, b) + max(a, b)) for a, b in zip(cur[::2], cur[1::2])])
    return levels[-1][0], levels


def proof(levels, i: int) -> list[str]:
    out = []
    for lvl in levels[:-1]:
        lvl = lvl + ([lvl[-1]] if len(lvl) % 2 else [])
        out.append(lvl[i ^ 1].hex())
        i //= 2
    return out


def verify(leaf_b: bytes, prf: list[str], root: bytes) -> bool:
    h = leaf_b
    for s in prf:
        o = bytes.fromhex(s)
        h = _h(min(h, o) + max(h, o))
    return h == root


def week_id(now: datetime) -> str:
    d = now.astimezone(timezone.utc)
    fri = d - timedelta(days=(d.weekday() - 4) % 7)
    return fri.date().isoformat()


def commit(fc: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    wk = week_id(now)
    tick = sorted(fc)
    root, levels = merkle([leaf(wk, t, fc[t]) for t in tick])
    salt = secrets.token_bytes(32)
    rec = {"week": wk, "committed_at": now.isoformat(), "root": root.hex(), "salt": salt.hex(),
           "commitment": _h(root + salt).hex(), "forecasts": fc,
           "proofs": {t: proof(levels, i) for i, t in enumerate(tick)}}
    os.makedirs(OUT, exist_ok=True)
    json.dump(rec, open(os.path.join(OUT, f"{wk}.json"), "w"), indent=1)
    return rec


# ---------- grade ----------
def real_gap(ticker: str, week: str) -> float | None:
    """Real next-session open / Friday regular close - 1 (Yahoo daily)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.replace('.', '-')}?interval=1d&range=1mo"
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20))
        r = r["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        days = [(datetime.fromtimestamp(ts, timezone.utc).date().isoformat(), q["open"][i], q["close"][i])
                for i, ts in enumerate(r["timestamp"]) if q["close"][i]]
        i = next(i for i, d in enumerate(days) if d[0] == week)
        return days[i + 1][1] / days[i][2] - 1
    except Exception:
        return None


def score(pairs: list[tuple[dict, float]]) -> dict:
    """pairs: (forecast, real_gap)."""
    if not pairs:
        return {}
    br = st.mean((f["p_up"] - (g > 0)) ** 2 for f, g in pairs)
    hit = st.mean(((f["gap_hat_bps"] > 0) == (g > 0)) for f, g in pairs if f["gap_hat_bps"] != 0)
    mae0 = st.mean(abs(g) for _, g in pairs) * 1e4
    mae = st.mean(abs(g - f["gap_hat_bps"] / 1e4) for f, g in pairs) * 1e4
    return {"n": len(pairs), "hit": round(hit, 4), "brier": round(br, 4), "brier_coinflip": 0.25,
            "mae_bps": round(mae, 1), "mae_no_change_bps": round(mae0, 1), "error_cut": round(1 - mae / mae0, 4)}


def grade(week: str) -> dict:
    rec = json.load(open(os.path.join(OUT, f"{week}.json")))
    pairs = [(f, g) for t, f in rec["forecasts"].items() if (g := real_gap(t, week)) is not None]
    s = score(pairs) | {"week": week, "commitment": rec["commitment"]}
    path = os.path.join(OUT, "scoreboard.json")
    board = json.load(open(path)) if os.path.exists(path) else []
    board = [b for b in board if b.get("week") != week] + [s]
    json.dump(board, open(path, "w"), indent=1)
    return s


def backtest() -> dict:
    """Leave-one-weekend-out: the Oracle never sees the weekend it forecasts."""
    rows = _rows()
    weeks = sorted({r["fri"] for r in rows})
    pairs = []
    for w in weeks:
        model = fit([r for r in rows if r["fri"] != w])
        te = [r for r in rows if r["fri"] == w]
        fc = forecast({r["sym"]: r["w_sun21"] for r in te}, model)
        pairs += [(fc[r["sym"]], r["g"]) for r in te]
    res = score(pairs) | {"weekends": len(weeks), "method": "leave-one-weekend-out"}
    res["by_conviction"] = {f">={lo*1e4:.0f}bps": score([(f, g) for f, g in pairs if abs(f["gap_hat_bps"]) >= lo * 1e4])
                            for lo in (0.0025, 0.005, 0.01)}
    return res
