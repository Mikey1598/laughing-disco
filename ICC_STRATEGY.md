# The ICC strategy: Indication, Correction, Continuation

These are the rules I use to read gold charts. The same rules drive `icc_gold.pine` (the TradingView indicator) and `icc_scanner.py` (the automatic scanner).

ICC is a **market-structure** strategy. Price moves in impulses and pullbacks. ICC waits for the market to show its direction (Indication), lets it pull back (Correction), and enters only when it resumes in that direction (Continuation). **You never enter on the Indication, and you never enter in the middle of a pullback.**

---

## 0. Timeframe stack
| Role | Timeframe | Purpose |
|---|---|---|
| Bias | **Daily** | Direction of the last daily break of structure. Trade only in this direction for A-grade setups. |
| Setup | **4H** | Indication, impulse leg and correction zone |
| Entry | **15m** (1H for wider stops) | Continuation trigger |

Setups that go against the daily bias are **B-grade**. Trade them at half size, or skip them.

## 1. Market structure basics
- A **swing high** is a candle whose high is above the highs of the candles on both sides. The defaults are 3 candles each side for major swings on the 4H, and 2 for internal swings. A **swing low** is the mirror image.
- **Bullish structure:** higher highs and higher lows. **Bearish structure:** lower highs and lower lows.
- A **break of structure (BOS)** is a candle that **closes** beyond the last swing high or low. A wick through doesn't count.

## 2. INDICATION: the market shows its hand
**Rule:** a 4H candle **closes** beyond the most recent swing point.
- A close below a swing low means a **short** indication. A close above a swing high means a **long** indication.

Each Indication defines three levels:
- **Broken level:** the swing point that was broken. It usually turns into resistance (for shorts) or support (for longs).
- **Origin:** where the impulse started. For a short, it's the highest high between that swing low and the breakout candle. **This is the invalidation level.**
- **Impulse extreme:** the furthest point the move reaches before it pulls back.

If price keeps breaking structure **without** pulling back, the Indication **refreshes**. Re-measure from the newest lower high (shorts) or higher low (longs).

✅ Do: mark the levels and set alerts.
❌ Don't: enter. Price is stretched at this point, and you'd be chasing.

## 3. CORRECTION: the pullback
**Rule:** the correction has started once price retraces **at least 38.2%** of the impulse leg.

| Zone | Retracement | Notes |
|---|---|---|
| Shallow | 38.2–50% | Common in strong trends. Trade half size. |
| **Prime** | **50–78.6%** | Highest probability, especially where it overlaps the broken level |
| Too deep | above 78.6% | The setup is weakening |
| Invalid | price **closes** beyond the origin | The setup is dead. Wait for a new BOS. |

**Confluence makes a zone stronger.** Look for these inside it:
- the broken structure level, retested from the other side
- a round number (3,700, 3,750 and so on)
- the open of the breakout candle
- a zone from a higher timeframe

**A healthy correction** is slow and overlapping, with small candles moving against the trend. That shows weak counter-pressure. **Warning signs** are big, fast candles that slice through the zone.

## 4. CONTINUATION: the entry
**Rule:** inside the zone, wait for the **15m** chart to break back in the direction of the trend.
- **Short:** a 15m candle **closes below the last higher low** of the pullback.
- **Long:** a 15m candle **closes above the last lower high** of the pullback.

Entry checklist:
- [ ] The setup agrees with the daily bias (A-grade)
- [ ] Price reached the correction zone (at least 38.2%)
- [ ] Momentum is fading: wicks against the pullback, smaller candles, or an engulfing candle
- [ ] The 15m trigger candle has closed
- [ ] No high-impact USD news within 30 minutes (CPI, NFP, FOMC, Fed speakers)
- [ ] It's during the London (3–5 AM ET) or New York (8:30–11 AM ET) session

## 5. Risk and trade management
| Item | Rule |
|---|---|
| Stop | Beyond the correction extreme, plus $3–5 for gold |
| Size | Risk 1% of the account. Gold: 1 lot × $1 = $100, so lots = (account × 1%) ÷ (stop distance in $ × 100). |
| TP1 | 2R. Close half and move the stop to your entry price. |
| TP2 | The impulse extreme (the old low or high) |
| TP3 | A measured move (the previous leg's size projected from the origin), or the next round number |
| Early exit | Price closes back beyond the high or low of the trigger candle before TP1 |

## 6. When NOT to trade
- No correction has happened yet. Never chase the impulse.
- The correction has closed beyond the origin.
- Within 30 minutes of high-impact news, or on holiday or thin sessions (Thanksgiving, Christmas week).
- Late Friday. Don't open new trades into the weekend.
- After two losses in a row in one day. Stop trading for the day.

## 7. Grading summary
| Grade | Conditions |
|---|---|
| **A+** | With the daily bias, prime zone plus broken-level confluence, London or New York trigger |
| **A** | With the daily bias, correction at least 38.2%, clean 15m trigger |
| **B** | Against the daily bias, or shallow zone only: half size |
| **No trade** | Any rule in section 6 applies |

*This is an educational framework, not financial advice.*
