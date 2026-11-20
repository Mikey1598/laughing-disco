# ICC strategy for gold (XAUUSD) on TradingView

`icc_gold.pine` is a Pine Script v5 indicator. It marks the three phases of the ICC setup on the chart and can send alerts for each one.

| Phase | What the script looks for | Mark on the chart |
|---|---|---|
| **Indication** | A candle closes through the last confirmed swing high (bullish) or swing low (bearish). This break of structure gives the direction. | `I` plus a dashed line at the broken level |
| **Correction** | Price pulls back at least 38.2% into the impulse leg and does not break the origin of the move. | `C` plus a shaded 38.2–78.6% zone |
| **Continuation** | Price closes back through the high (long) or low (short) of the candle that made the correction extreme. This is the entry. | `CONT ▲/▼` plus entry, stop-loss and take-profit lines |

A setup is cancelled (`✕`) when price closes beyond the origin of the impulse. It is also cancelled when structure breaks the other way.

## Install
1. In TradingView, open **Pine Editor** at the bottom of the chart.
2. Paste in the contents of `icc_gold.pine` and click **Add to chart**.
3. Open an `XAUUSD` chart. The script works on any timeframe, but 15m or 1H entries with the 4H filter are a good place to start.
4. To get alerts, click **Alert**, choose **ICC**, then pick an event such as "ICC LONG continuation".

## Settings worth tuning
- **Swing pivot length**: use a lower value to catch more, smaller structure, or a higher value for fewer, bigger swings.
- **Break confirmed by**: `Close` is stricter and gives fewer false breaks than `Wick`.
- **HTF filter**: takes longs only above the 4H 50 EMA and shorts only below it.
- **Stop buffer and R multiple**: these set where the stop-loss and take-profit lines are drawn.

## Chart reviews
You can send a screenshot of your gold chart to Claude. Ask it to identify the current ICC phase, the key levels and whether a continuation entry is valid.

*This is an educational tool and not financial advice. Backtest it before trading real money.*

## Full rules
`ICC_STRATEGY.md` sets out the complete strategy: the timeframe stack, structure, each phase, risk, when not to trade, and grading.

## Instant alerts with levels
In TradingView, create an alert, choose **ICC**, then **Any alert() function call**. Each alert message contains the levels for that phase: the indication with its invalidation level and correction zone, the correction with its trigger price, and the continuation with entry, SL and TP.

## Automatic scanner
`python3 icc_scanner.py` downloads live gold data and reports the current ICC phase for three setups: the **daily** setup (4H entry trigger), and the **major** and **internal** 4H setups (15m entry trigger). Add `--json` for machine-readable output, or `--state-file PATH` to see whether the phase has changed since the last run.
