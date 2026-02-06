import argparse
import csv
import sys
from bisect import bisect_left
from datetime import datetime, timedelta, time
from pathlib import Path


DATE_FORMATS = [
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
]


def parse_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    # Excel serial date
    try:
        serial = float(text)
        return datetime(1899, 12, 30) + timedelta(days=serial)
    except ValueError:
        return None


def normalize_column(name):
    return name.strip().lower().replace(" ", "").replace("_", "")


def map_columns(fieldnames, targets):
    normalized = {normalize_column(n): n for n in fieldnames}
    for target in targets:
        key = normalize_column(target)
        if key in normalized:
            return normalized[key]
    return None


def load_nifty_csv(path):
    path = Path(path)
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("Nifty CSV has no header.")
        date_col = map_columns(reader.fieldnames, ["date", "datetime", "timestamp", "time"])
        open_col = map_columns(reader.fieldnames, ["open"])
        high_col = map_columns(reader.fieldnames, ["high"])
        low_col = map_columns(reader.fieldnames, ["low"])
        close_col = map_columns(reader.fieldnames, ["close"])
        if not all([date_col, open_col, high_col, low_col, close_col]):
            raise ValueError("Nifty CSV must include date/open/high/low/close columns.")
        rows = []
        for row in reader:
            dt = parse_datetime(row.get(date_col))
            if not dt:
                continue
            try:
                high = float(row.get(high_col))
                low = float(row.get(low_col))
                close = float(row.get(close_col))
                open_ = float(row.get(open_col))
            except (TypeError, ValueError):
                continue
            rows.append({"dt": dt, "open": open_, "high": high, "low": low, "close": close})
        rows.sort(key=lambda r: r["dt"])
        if not rows:
            raise ValueError("No valid rows loaded from Nifty CSV.")
        return rows


def load_trades(path, sheet=None):
    path = Path(path)
    if path.suffix.lower() in [".xlsx", ".xls"]:
        try:
            import pandas as pd
        except ImportError as exc:
            raise SystemExit("Install pandas and openpyxl to read Excel: pip install pandas openpyxl") from exc
        df = pd.read_excel(path, sheet_name=sheet)  # type: ignore
        # When sheet_name is None and multiple sheets exist, pandas returns a dict.
        if isinstance(df, dict):
            if not df:
                raise ValueError("Excel file has no sheets.")
            # Pick the first sheet by name for default behavior.
            first_sheet_name = next(iter(df.keys()))
            df = df[first_sheet_name]
        df.columns = [str(c) for c in df.columns]
        fieldnames = list(df.columns)
        rows = df.to_dict(orient="records")

        # If columns look like a report header, attempt to locate the real header row.
        direction_col = map_columns(fieldnames, ["direction", "type", "side"])
        entry_time_col = map_columns(fieldnames, ["entrydatetime", "entrydate/time", "entrydate", "entrytime", "timestamp"])
        entry_price_col = map_columns(fieldnames, ["entryprice", "price"])
        qty_col = map_columns(fieldnames, ["qty", "quantity"])
        if not all([direction_col, entry_time_col, entry_price_col, qty_col]):
            df_raw = pd.read_excel(path, sheet_name=sheet, header=None)  # type: ignore
            if isinstance(df_raw, dict):
                if not df_raw:
                    raise ValueError("Excel file has no sheets.")
                first_sheet_name = next(iter(df_raw.keys()))
                df_raw = df_raw[first_sheet_name]
            header_row = None
            for i in range(min(200, len(df_raw))):
                row = df_raw.iloc[i].astype(str).str.strip().str.lower().tolist()
                if "direction" in row and "entry date/time" in row and "qty" in row:
                    header_row = i
                    break
            if header_row is not None:
                headers = [str(c) for c in df_raw.iloc[header_row].tolist()]
                df_data = df_raw.iloc[header_row + 1 :].copy()
                df_data.columns = headers
                df_data = df_data.dropna(how="all")
                fieldnames = list(df_data.columns)
                rows = df_data.to_dict(orient="records")
    else:
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            all_rows = list(reader)
        if not all_rows:
            raise ValueError("Trade log is empty.")
        header_row = None
        for i, row in enumerate(all_rows[:200]):
            normalized = [str(c).strip().lower() for c in row]
            if "direction" in normalized and "entry date/time" in normalized and "qty" in normalized:
                header_row = i
                break
        if header_row is None:
            raise ValueError("Trade log must include direction, entry time, entry price, qty columns.")
        fieldnames = all_rows[header_row]
        rows = []
        for row in all_rows[header_row + 1 :]:
            if not any(str(c).strip() for c in row):
                continue
            row_dict = {fieldnames[i]: row[i] if i < len(row) else "" for i in range(len(fieldnames))}
            rows.append(row_dict)

    direction_col = map_columns(fieldnames, ["direction", "type", "side"])
    entry_time_col = map_columns(fieldnames, ["entrydatetime", "entrydate/time", "entrydate", "entrytime", "timestamp"])
    entry_price_col = map_columns(fieldnames, ["entryprice", "price"])
    qty_col = map_columns(fieldnames, ["qty", "quantity"])

    if not all([direction_col, entry_time_col, entry_price_col, qty_col]):
        raise ValueError("Trade log must include direction, entry time, entry price, qty columns.")

    trades = []
    for row in rows:
        raw_dir = str(row.get(direction_col, "")).strip().upper()
        if raw_dir in ["BUY", "LONG"]:
            direction = "LONG"
        elif raw_dir in ["SELL", "SHORT"]:
            direction = "SHORT"
        else:
            continue

        dt = parse_datetime(row.get(entry_time_col))
        if not dt:
            continue
        try:
            entry_price = float(row.get(entry_price_col))
            qty = float(row.get(qty_col))
        except (TypeError, ValueError):
            continue
        trades.append(
            {
                "direction": direction,
                "entry_dt": dt,
                "entry_price": entry_price,
                "qty": qty,
            }
        )
    trades.sort(key=lambda r: r["entry_dt"])
    if not trades:
        raise ValueError("No valid trades loaded.")
    return trades


def get_session_window(candles):
    first_day = candles[0]["dt"].date()
    day_times = [c["dt"].time() for c in candles if c["dt"].date() == first_day]
    if not day_times:
        return None
    return min(day_times), max(day_times)


def count_in_session(trades, session_start, session_end):
    count = 0
    for t in trades:
        tm = t["entry_dt"].time()
        if session_start <= tm <= session_end:
            count += 1
    return count


def apply_trade_offset(trades, minutes):
    if minutes == 0:
        return trades
    delta = timedelta(minutes=minutes)
    for t in trades:
        t["entry_dt"] = t["entry_dt"] + delta
    trades.sort(key=lambda r: r["entry_dt"])
    return trades


def maybe_adjust_trade_times(trades, candles, explicit_offset):
    if explicit_offset is not None:
        return apply_trade_offset(trades, explicit_offset), explicit_offset

    session_window = get_session_window(candles)
    if session_window is None:
        return trades, 0

    session_start, session_end = session_window
    base_count = count_in_session(trades, session_start, session_end)

    candidates = [0, -330, 330]
    best_offset = 0
    best_count = base_count
    for offset in candidates:
        if offset == 0:
            continue
        shifted = [{"entry_dt": t["entry_dt"] + timedelta(minutes=offset)} for t in trades]
        count = 0
        for t in shifted:
            tm = t["entry_dt"].time()
            if session_start <= tm <= session_end:
                count += 1
        if count > best_count:
            best_count = count
            best_offset = offset

    # Apply if it materially improves alignment with session hours.
    if best_offset != 0 and best_count >= max(3, int(base_count * 1.5)):
        return apply_trade_offset(trades, best_offset), best_offset

    return trades, 0


def evaluate_trade(trade, candles, candle_times, rr, risk):
    direction = trade["direction"]
    entry_dt = trade["entry_dt"]
    entry_price = trade["entry_price"]
    qty = trade["qty"]
    if qty <= 0:
        return None

    risk_per_unit = risk / qty
    if direction == "LONG":
        sl = entry_price - risk_per_unit
        target = entry_price + rr * risk_per_unit
    else:
        sl = entry_price + risk_per_unit
        target = entry_price - rr * risk_per_unit

    start_idx = bisect_left(candle_times, entry_dt)
    if start_idx >= len(candles):
        return None

    exit_dt = None
    exit_price = None
    outcome = "NO_HIT"
    entry_day = entry_dt.date()
    cutoff_dt = datetime.combine(entry_day, time(15, 20))
    last_candle = None

    for candle in candles[start_idx:]:
        if candle["dt"].date() != entry_day:
            break
        if candle["dt"] > cutoff_dt:
            break
        last_candle = candle
        high = candle["high"]
        low = candle["low"]

        sl_hit = False
        target_hit = False
        if direction == "LONG":
            sl_hit = low <= sl
            target_hit = high >= target
        else:
            sl_hit = high >= sl
            target_hit = low <= target

        if sl_hit and target_hit:
            outcome = "LOSS"
            exit_dt = candle["dt"]
            exit_price = sl
            break
        if sl_hit:
            outcome = "LOSS"
            exit_dt = candle["dt"]
            exit_price = sl
            break
        if target_hit:
            outcome = "WIN"
            exit_dt = candle["dt"]
            exit_price = target
            break

    if exit_dt is None:
        if last_candle is None:
            return None
        exit_dt = last_candle["dt"]
        exit_price = last_candle["close"]
        outcome = "NO_HIT"

    pnl = (exit_price - entry_price) * qty
    if direction == "SHORT":
        pnl = -pnl

    return {
        "outcome": outcome,
        "exit_dt": exit_dt,
        "exit_price": exit_price,
        "sl": sl,
        "target": target,
        "pnl": pnl,
    }


def compute_drawdown(pnls, initial_capital):
    peak = initial_capital
    equity = initial_capital
    max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
    return max_dd


def compute_drawdown_series(pnls, initial_capital):
    peak = initial_capital
    equity = initial_capital
    dd_abs = []
    dd_pct = []
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        dd = peak - equity
        dd_abs.append(dd)
        if peak > 0:
            dd_pct.append(dd / peak * 100.0)
        else:
            dd_pct.append(0.0)
    return dd_abs, dd_pct


def main():
    parser = argparse.ArgumentParser(description="Evaluate RR outcomes using Nifty 5-min candles.")
    parser.add_argument("--trades", required=True, help="Trade log CSV/XLSX file.")
    parser.add_argument("--nifty", required=True, help="Nifty 5-minute candles CSV file.")
    parser.add_argument("--out", default="rr_results.csv", help="Output CSV path.")
    parser.add_argument("--sheet", default=None, help="Excel sheet name (if trades is XLSX).")
    parser.add_argument("--rrs", default="2,3,4,10", help="Comma-separated RR list, e.g. 2,3,4,10")
    parser.add_argument("--risk", type=float, default=10000.0, help="Risk per trade in currency.")
    parser.add_argument("--initial-capital", type=float, default=1000000.0, help="Starting capital for drawdown calc.")
    parser.add_argument("--trade-offset-minutes", type=int, default=None, help="Shift trade times by minutes (e.g., -330).")
    args = parser.parse_args()

    candles = load_nifty_csv(args.nifty)
    candle_times = [c["dt"] for c in candles]
    trades = load_trades(args.trades, sheet=args.sheet)
    trades, applied_offset = maybe_adjust_trade_times(trades, candles, args.trade_offset_minutes)
    rrs = [float(x.strip()) for x in args.rrs.split(",") if x.strip()]

    results = []
    for rr in rrs:
        last_exit_dt = None
        blocked_day = None
        for trade in trades:
            entry_dt = trade["entry_dt"]
            entry_day = entry_dt.date()
            if blocked_day == entry_day:
                continue
            if last_exit_dt is not None and entry_dt < last_exit_dt:
                continue

            eval_result = evaluate_trade(trade, candles, candle_times, rr=rr, risk=args.risk)
            if eval_result is None:
                continue

            exit_dt = eval_result["exit_dt"]
            outcome = eval_result["outcome"]
            if exit_dt is None:
                blocked_day = entry_day
            else:
                last_exit_dt = exit_dt
                if outcome == "NO_HIT":
                    blocked_day = entry_day

            row = {
                "rr": rr,
                "direction": trade["direction"],
                "entry_dt": trade["entry_dt"],
                "entry_price": trade["entry_price"],
                "qty": trade["qty"],
                "sl": eval_result["sl"],
                "target": eval_result["target"],
                "exit_dt": eval_result["exit_dt"],
                "exit_price": eval_result["exit_price"],
                "outcome": eval_result["outcome"],
                "pnl": eval_result.get("pnl"),
            }
            results.append(row)

    if not results:
        raise SystemExit("No results produced.")

    # Per-RR stats
    stats = []
    for rr in rrs:
        rr_rows = [r for r in results if r["rr"] == rr]
        rr_rows_sorted = sorted(rr_rows, key=lambda r: r["entry_dt"])
        pnls = [r["pnl"] for r in rr_rows if r["pnl"] is not None]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        total = len(pnls)
        win_rate = (len(wins) / total * 100) if total else 0.0
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        expectancy = (win_rate / 100) * avg_win + (1 - win_rate / 100) * avg_loss
        total_pnl = sum(pnls) if pnls else 0.0
        max_dd = compute_drawdown(pnls, initial_capital=args.initial_capital)
        stats.append(
            {
                "rr": rr,
                "trades": total,
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": win_rate,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "expectancy": expectancy,
                "total_pnl": total_pnl,
                "max_drawdown": max_dd,
            }
        )

        pnls_for_dd = [r["pnl"] if r["pnl"] is not None else 0.0 for r in rr_rows_sorted]
        dd_abs, dd_pct = compute_drawdown_series(pnls_for_dd, initial_capital=args.initial_capital)
        for row, dd_a, dd_p in zip(rr_rows_sorted, dd_abs, dd_pct):
            row["drawdown_abs"] = dd_a
            row["drawdown_pct"] = dd_p

    # Write results
    out_path = Path(args.out)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "rr",
            "direction",
            "entry_dt",
            "entry_price",
            "qty",
            "sl",
            "target",
            "exit_dt",
            "exit_price",
            "outcome",
            "pnl",
            "drawdown_abs",
            "drawdown_pct",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            row = dict(row)
            if isinstance(row["entry_dt"], datetime):
                row["entry_dt"] = row["entry_dt"].strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(row["exit_dt"], datetime):
                row["exit_dt"] = row["exit_dt"].strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow(row)

    stats_path = out_path.with_name(out_path.stem + "_stats.csv")
    with stats_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "rr",
            "trades",
            "wins",
            "losses",
            "win_rate",
            "avg_win",
            "avg_loss",
            "expectancy",
            "total_pnl",
            "max_drawdown",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in stats:
            writer.writerow(row)

    print(f"Wrote {out_path}")
    print(f"Wrote {stats_path}")
    if applied_offset:
        print(f"Applied trade time offset: {applied_offset} minutes")


if __name__ == "__main__":
    main()
