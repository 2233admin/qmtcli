"""Daily trend screen over the loopback bridge: momentum, volume, distance to the 20-day high.

The TDX/TQ plugin on this host stops updating its calendar, so this reads the bridge instead.
Rules match .git/pstack/scan-20261110.md except the 20-day high, which uses the bar high, and ST
names, which the bridge does not expose.

The report also names its own data date from the tick timetag, so a stale feed is visible instead of
silently repeating yesterday.
"""

import argparse
import json
import statistics
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CONNECTION = Path.home() / "AppData/Local/QmtCli/daqmt/connection.json"
CHUNK = 300
BARS = 26


def get(config, path):
    request = urllib.request.Request(
        config["endpoint"] + path, headers={"X-Bridge-Secret": config["secret"]}
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - loopback
        return json.loads(response.read())


def rows_of(frame, fields):
    columns = frame.get("columns") or []
    index = {name: position for position, name in enumerate(columns)}
    if any(name not in index for name in fields):
        return None
    return [[row[index[name]] for name in fields] for row in frame.get("data") or []]


def metrics(rows, last_close):
    if rows is None or len(rows) < BARS:
        return None
    closes = [row[0] for row in rows]
    highs = [row[1] for row in rows]
    volumes = [row[2] for row in rows]
    if any(value is None for value in closes[-21:]) or closes[-1] in (None, 0):
        return None
    if any(value is None for value in highs[-20:]) or not max(highs[-20:] or [0]):
        return None
    if any(value is None for value in volumes[-20:]) or volumes[-1] in (None, 0):
        return None
    previous = closes[-21]
    if not previous or not last_close:
        return None
    recent = closes[-20:]
    mean_volume_5 = statistics.fmean(volumes[-5:])
    mean_volume_20 = statistics.fmean(volumes[-20:])
    if not mean_volume_20:
        return None
    return {
        "close": closes[-1],
        "chg1": (closes[-1] / last_close - 1) * 100,
        "mom5": (closes[-1] / closes[-6] - 1) * 100,
        "mom20": (closes[-1] / previous - 1) * 100,
        "above20": (closes[-1] / statistics.fmean(recent) - 1) * 100,
        "vr": mean_volume_5 / mean_volume_20,
        "dh": (closes[-1] / max(highs[-20:]) - 1) * 100,
    }


def percentile(values):
    ordered = sorted(values)
    size = len(ordered)
    return {value: position / max(size - 1, 1) for position, value in enumerate(ordered)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None,
                        help="directory to write scan-YYYYMMDD.md into")
    args = parser.parse_args()

    config = json.loads(CONNECTION.read_text(encoding="utf-8"))
    try:
        ticks = get(config, "/api/market/tick?symbols=SH,SZ")["ticks"]
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ConnectionRefusedError):
            # The QMT-side strategy serves the bridge only while it runs; outside
            # a session it is intentionally down, which is not a scan failure.
            print(f"skipped: bridge not listening at {config['endpoint']} "
                  f"(QMT strategy not running)")
            return 0
        raise
    stamp = max((tick.get("timetag", "") for tick in ticks.values()), default="")

    lines = []

    def emit(text=""):
        lines.append(text)

    universe = {}
    for symbol, tick in ticks.items():
        if symbol[0] not in "036" or symbol.startswith("88"):
            continue
        close = tick.get("lastClose") or 0
        price = tick.get("lastPrice") or 0
        if close <= 0 or price <= 0:
            continue
        universe[symbol] = tick

    up = sum(1 for t in universe.values() if t["lastPrice"] > t["lastClose"])
    down = sum(1 for t in universe.values() if t["lastPrice"] < t["lastClose"])

    found = {}
    symbols = sorted(universe)
    for start in range(0, len(symbols), CHUNK):
        chunk = symbols[start:start + CHUNK]
        query = urllib.parse.urlencode({
            "symbols": ",".join(chunk),
            "period": "1d",
            "count": str(BARS),
            "fields": "close,high,volume",
            "dividend_type": "front",
        })
        try:
            payload = get(config, "/api/market/bars?" + query)["bars"]
        except OSError as exc:
            print(f"chunk {start} failed: {exc}", file=sys.stderr)
            return 1
        for symbol, frame in payload.items():
            result = metrics(rows_of(frame, ["close", "high", "volume"]),
                             universe[symbol]["lastClose"])
            if result:
                found[symbol] = result

    limit = {symbol: (19.8 if symbol[:3] in ("300", "301", "688", "689") else 9.8)
             for symbol in found}

    passed = {
        symbol: value for symbol, value in found.items()
        if value["close"] >= 3
        and value["mom20"] > 0 and value["mom5"] > 0 and value["above20"] > 0
        and value["vr"] >= 1.2
        and value["chg1"] < limit[symbol] - 0.2
    }

    emit(f"# 全市场趋势筛选 {stamp[:8]}")
    emit()
    emit(f"行情时点 `{stamp}`；有效股票 {len(universe)} 只，涨 {up} 跌 {down}，"
         f"拿到 {BARS} 根日线的 {len(found)} 只，通过 {len(passed)} 只。")
    emit()

    if not passed:
        emit("No symbol passed.")
        report = "\n".join(lines) + "\n"
        print(report, end="")
        return 0

    ranks = {name: percentile([v[name] for v in passed.values()])
             for name in ("mom20", "mom5", "vr", "dh")}
    for value in passed.values():
        value["score"] = 100 * (
            0.4 * ranks["mom20"][value["mom20"]]
            + 0.2 * ranks["mom5"][value["mom5"]]
            + 0.2 * ranks["vr"][value["vr"]]
            + 0.2 * ranks["dh"][value["dh"]]
        )

    steady = {s: v for s, v in passed.items()
              if 10 <= v["mom20"] <= 50 and v["mom5"] <= 20 and v["dh"] >= -3
              and v["vr"] >= 1.3 and v["chg1"] < 7}

    emit("## 全市场前 20")
    emit()
    emit("| 代码 | 收盘 | 当日 | 5日 | 20日 | 距20日高 | 量比 | 评分 |")
    emit("|---|---|---|---|---|---|---|---|")
    for symbol, value in sorted(passed.items(), key=lambda kv: -kv[1]["score"])[:20]:
        emit(f"| {symbol} | {value['close']:.3f} | {value['chg1']:+.2f}% "
             f"| {value['mom5']:+.2f}% | {value['mom20']:+.2f}% "
             f"| {value['dh']:+.2f}% | {value['vr']:.2f} | {value['score']:.1f} |")
    emit()
    emit(f"## 稳健切分 {len(steady)} 只")
    emit()
    if steady:
        emit("| 代码 | 收盘 | 当日 | 5日 | 20日 | 距20日高 | 量比 |")
        emit("|---|---|---|---|---|---|---|")
        for symbol, value in sorted(steady.items(), key=lambda kv: -kv[1]["score"]):
            emit(f"| {symbol} | {value['close']:.3f} | {value['chg1']:+.2f}% "
                 f"| {value['mom5']:+.2f}% | {value['mom20']:+.2f}% "
                 f"| {value['dh']:+.2f}% | {value['vr']:.2f} |")

    report = "\n".join(lines) + "\n"
    print(report, end="")
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        target = args.out / f"scan-{stamp[:8]}.md"
        target.write_text(report, encoding="utf-8")
        print(f"\nwritten: {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
