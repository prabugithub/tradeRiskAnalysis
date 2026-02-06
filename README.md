# TradeRRCheck

Evaluate fixed risk-reward outcomes (1:2, 1:3, 1:4 by default) for NIFTY 5-minute data using your trade log.

## What It Does
- Reads NIFTY 5-minute candles from CSV
- Reads trades from CSV or Excel
- Computes SL/Target per trade based on fixed risk per trade (default `10000`)
- Evaluates each trade using candle `high/low`
- If SL and Target are hit in the same candle, SL is chosen (conservative)
- Outputs per-trade results and aggregated stats

## Requirements
- Python 3.8+
- If your trade log is Excel (`.xlsx`/`.xls`):
  - `pip install pandas openpyxl`

## Files
- Input:
  - `NIFTY 50_5minute.csv` (candles)
  - `active-analysis.xlsx` (trade log)
- Output:
  - `rr_results.csv` (per trade per RR)
  - `rr_results_stats.csv` (summary stats per RR)

## Run
From the project folder:

```bash
python rr_eval.py --trades "active-analysis.xlsx" --nifty "NIFTY 50_5minute.csv"
```

If the trades file is CSV:

```bash
python rr_eval.py --trades "active-analysis.csv" --nifty "NIFTY 50_5minute.csv"
```

Specify a sheet name (Excel) and custom params:

```bash
python rr_eval.py --trades "active-analysis.xlsx" --sheet "Sheet1" --nifty "NIFTY 50_5minute.csv" --rrs 2,3,4 --risk 10000 --out rr_results.csv
```

## CLI Options
- `--trades`: Trade log CSV/XLSX
- `--nifty`: NIFTY 5-minute candles CSV
- `--sheet`: Excel sheet name (optional)
- `--rrs`: Comma-separated RR list (default `2,3,4`)
- `--risk`: Risk per trade in currency (default `10000`)
- `--out`: Output CSV filename (default `rr_results.csv`)

## Expected Columns

### NIFTY 5-minute CSV
Required columns (case/space/underscore insensitive):
- `date` / `datetime` / `timestamp`
- `open`
- `high`
- `low`
- `close`

### Trade Log CSV/XLSX
Required columns (case/space/underscore insensitive):
- `Direction` or `Type` (`LONG/SHORT` or `BUY/SELL`)
- `Entry Date/Time` (or `Timestamp`)
- `Entry Price` (or `Price`)
- `Qty` (or `Quantity`)

The Excel export is supported even if the actual header row starts later in the sheet.

## Output Fields

### rr_results.csv
- `rr`
- `direction`
- `entry_dt`
- `entry_price`
- `qty`
- `sl`
- `target`
- `exit_dt`
- `exit_price`
- `outcome` (`WIN`, `LOSS`, `NO_HIT`)
- `pnl`

### rr_results_stats.csv
- `rr`
- `trades`
- `wins`
- `losses`
- `win_rate`
- `avg_win`
- `avg_loss`
- `expectancy`
- `total_pnl`
- `max_drawdown`

## Notes
- Trades with no SL/Target hit are marked `NO_HIT` and excluded from stats.
- Drawdown is computed from the sequence of trade P&L (per RR).
