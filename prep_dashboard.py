"""
Reads the ForgeAlpha pipeline's Excel outputs (+ the Indian Fama-French style
factor CSV) and exports a compact JSON payload for the dashboard: full
monthly return series (raw NIFTY factors, orthogonalized/market-neutral
NIFTY factors, Fama-French style factors, sectors, market) plus crowding
percentiles and correlation matrices. The dashboard does all regression
(rolling betas, R², Adj. R², VIF) live in the browser for both factor
sources, so this step only hands over clean, aligned monthly series — no
rolling-window computation happens here.
"""

import json
import os

import numpy as np
import pandas as pd

DASH_FILE = r"D:\PMS\Sectors Post\forgealpha_dashboard_data.xlsx"
RAW_FILE = r"D:\PMS\Data\NIFTY Indices\All_NIFTY_Indices.xlsx"
FF_FILE = r"D:\PMS\Indian FF Factor Data.csv"
OUT_FILE = os.path.join(os.path.dirname(__file__), "dashboard_data.json")

FACTOR_ORDER = ["Quality", "Momentum", "Value", "LowVol"]
SECTOR_ORDER = ["IT", "Bank", "Auto", "FMCG", "Pharma", "Metal", "Energy", "Financial Services"]
FF_FACTOR_ORDER = ["SMB", "HML", "WML", "RMW", "CMA"]

WINDOWS = {"1M": 1, "3M": 3, "6M": 6, "12M": 12}
CROWDING_LOOKBACK_MONTHS = 12


def pivot_series(df, id_col):
    return df.pivot(index="Date", columns=id_col, values="Return").sort_index()


def ols_resid(y, x):
    X = np.column_stack([np.ones(len(x)), x.values])
    beta, *_ = np.linalg.lstsq(X, y.values, rcond=None)
    fitted = X @ beta
    return pd.Series(y.values - fitted, index=y.index)


def trailing_cum_return(monthly_pct_series, months):
    tail = monthly_pct_series.tail(months).dropna()
    if len(tail) == 0:
        return None
    growth = (1 + tail / 100).prod()
    return round((growth - 1) * 100, 2)


def trailing_table(wide_df):
    return {col: {w: trailing_cum_return(wide_df[col], m) for w, m in WINDOWS.items()} for col in wide_df.columns}


def crowding_from_series(wide_df, lookback_months, history_months=36):
    """Trailing-N-month-sum percentile rank vs. the factor's own full history.
    Used directly for FF factors (already long-short/self-financing — no
    market subtraction needed, unlike the NIFTY smart-beta indices)."""
    pct = wide_df.rolling(lookback_months).sum().rank(pct=True) * 100
    out = {}
    for col in wide_df.columns:
        s = pct[col].dropna().tail(history_months)
        out[col] = {
            "latest": round(float(s.iloc[-1]), 1) if len(s) else None,
            "history": [round(float(v), 1) for v in s.values],
        }
    return out


def corr_matrix(wide_df):
    c = wide_df.corr()
    return {a: {b: round(float(c.loc[a, b]), 3) for b in c.columns} for a in c.index}


def build_payload():
    xl = pd.ExcelFile(DASH_FILE)
    crowding = xl.parse("Crowding")
    factor_returns = xl.parse("FactorReturns")
    sector_returns = xl.parse("SectorReturns")

    prices = pd.read_excel(RAW_FILE, sheet_name="All_Indices", index_col=0, parse_dates=True)
    market_monthly = prices["NIFTY 500"].resample("ME").last().pct_change().dropna() * 100

    factor_wide_raw = pivot_series(factor_returns, "Factor")[FACTOR_ORDER]
    sector_wide = pivot_series(sector_returns, "Sector")[SECTOR_ORDER]

    joint = pd.concat([market_monthly.rename("Market"), factor_wide_raw, sector_wide], axis=1).dropna(how="any")
    dates = joint.index
    market_series = joint["Market"]
    factor_raw_series = joint[FACTOR_ORDER]
    sector_series = joint[SECTOR_ORDER]

    factor_ortho_series = pd.DataFrame(
        {f: ols_resid(factor_raw_series[f], market_series) for f in FACTOR_ORDER}
    )

    # ---- Fama-French style factors (long-short, already market-relative by
    # construction — no orthogonalization step). MKT in the source file is the
    # raw market return (verified against our own NIFTY 500 series), so the
    # proper regressor is Mkt-RF = MKT - Rf, and the dependent variable for
    # any FF regression should be excess sector return (sector - Rf).
    ff_raw = pd.read_csv(FF_FILE)
    ff_raw["Month"] = pd.to_datetime(ff_raw["Month"])
    ff_raw = ff_raw.set_index("Month")
    ff_raw.index = ff_raw.index + pd.offsets.MonthEnd(0)  # align to month-end, matching sector/factor/market dates
    ff_raw["MktRF"] = (ff_raw["MKT"] - ff_raw["Rf"]) * 100
    for c in FF_FACTOR_ORDER + ["Rf"]:
        ff_raw[c] = ff_raw[c] * 100

    ff_joint = pd.concat([sector_wide, ff_raw[FF_FACTOR_ORDER + ["MktRF", "Rf"]]], axis=1).dropna(how="any")
    ff_dates = ff_joint.index
    ff_sectors_excess = ff_joint[SECTOR_ORDER].sub(ff_joint["Rf"], axis=0)
    ff_factors = ff_joint[FF_FACTOR_ORDER]
    ff_mktrf = ff_joint["MktRF"]

    ff_crowding_out = crowding_from_series(ff_factors, CROWDING_LOOKBACK_MONTHS)

    ff_corr_regressors = pd.concat([ff_factors, ff_mktrf.rename("MktRF")], axis=1)
    nifty_corr_regressors_raw = factor_raw_series.copy()
    nifty_corr_regressors_ortho = pd.concat([factor_ortho_series, market_series.rename("Market")], axis=1)

    # ---- overlap sample for a fair NIFTY-model vs. FF-model comparison ----
    overlap_idx = dates.intersection(ff_dates)
    compare = {
        "dates": [d.strftime("%Y-%m") for d in overlap_idx],
        "sectorsExcess": {
            s: [round(float(v), 3) for v in (sector_series.loc[overlap_idx, s] - ff_joint.loc[overlap_idx, "Rf"]).values]
            for s in SECTOR_ORDER
        },
        "niftyFactorsOrtho": {f: [round(float(v), 3) for v in factor_ortho_series.loc[overlap_idx, f].values] for f in FACTOR_ORDER},
        "niftyMarket": [round(float(v), 3) for v in market_series.loc[overlap_idx].values],
        "ffFactors": {f: [round(float(v), 3) for v in ff_factors.loc[overlap_idx, f].values] for f in FF_FACTOR_ORDER},
        "ffMktrf": [round(float(v), 3) for v in ff_mktrf.loc[overlap_idx].values],
    }

    trailing = {
        "factorsRaw": trailing_table(factor_raw_series),
        "factorsOrtho": trailing_table(factor_ortho_series),
        "sectors": trailing_table(sector_series),
        "market": {w: trailing_cum_return(market_series, m) for w, m in WINDOWS.items()},
        "ffFactors": trailing_table(ff_factors),
    }

    crowding_wide = crowding.pivot(index="Date", columns="Factor", values="PctPositive").sort_index()
    crowding_latest_date = crowding_wide.index.max()
    crowding_out = {}
    for f in FACTOR_ORDER:
        s = crowding_wide[f].dropna().tail(36)
        crowding_out[f] = {
            "latest": round(float(s.iloc[-1]), 1) if len(s) else None,
            "history": [round(float(v), 1) for v in s.values],
        }

    # Daily price levels for the sector/factor/market indices (not the FF factors, which are
    # only published monthly by the source CSV). Lets the dashboard compute "trailing N month"
    # performance from the exact calendar day N months ago against the live index, instead of
    # snapping to month-end buckets -- the two can disagree by several points when the window
    # straddles a sharp single-day move.
    daily_prices = {
        "dates": [d.strftime("%Y-%m-%d") for d in prices.index],
        "market": [None if pd.isna(v) else round(float(v), 3) for v in prices["NIFTY 500"]],
        "factors": {f: [None if pd.isna(v) else round(float(v), 3) for v in prices[f]] for f in FACTOR_ORDER},
        "sectors": {s: [None if pd.isna(v) else round(float(v), 3) for v in prices[s]] for s in SECTOR_ORDER},
    }

    payload = {
        "meta": {
            "asOfPrice": prices.index.max().strftime("%Y-%m-%d"),
            "crowdingAsOf": crowding_latest_date.strftime("%Y-%m-%d"),
            "sampleStart": dates.min().strftime("%Y-%m"),
            "sampleEnd": dates.max().strftime("%Y-%m"),
            "factorOrder": FACTOR_ORDER,
            "sectorOrder": SECTOR_ORDER,
            "ffFactorOrder": FF_FACTOR_ORDER,
        },
        "dates": [d.strftime("%Y-%m") for d in dates],
        "series": {
            "market": [round(float(v), 3) for v in market_series.values],
            "factorsRaw": {f: [round(float(v), 3) for v in factor_raw_series[f].values] for f in FACTOR_ORDER},
            "factorsOrtho": {f: [round(float(v), 3) for v in factor_ortho_series[f].values] for f in FACTOR_ORDER},
            "sectors": {s: [round(float(v), 3) for v in sector_series[s].values] for s in SECTOR_ORDER},
        },
        "trailing": trailing,
        "crowding": crowding_out,
        "correlations": {
            "niftyRaw": corr_matrix(nifty_corr_regressors_raw),
            "niftyOrtho": corr_matrix(nifty_corr_regressors_ortho),
            "ff": corr_matrix(ff_corr_regressors),
        },
        "ff": {
            "meta": {
                "sampleStart": ff_dates.min().strftime("%Y-%m"),
                "sampleEnd": ff_dates.max().strftime("%Y-%m"),
            },
            "dates": [d.strftime("%Y-%m") for d in ff_dates],
            "series": {
                "sectorsExcess": {s: [round(float(v), 3) for v in ff_sectors_excess[s].values] for s in SECTOR_ORDER},
                "factors": {f: [round(float(v), 3) for v in ff_factors[f].values] for f in FF_FACTOR_ORDER},
                "mktrf": [round(float(v), 3) for v in ff_mktrf.values],
                "rf": [round(float(v), 3) for v in ff_joint["Rf"].values],
            },
            "crowding": ff_crowding_out,
        },
        "compare": compare,
        "dailyPrices": daily_prices,
    }
    return payload


def main():
    payload = build_payload()
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"Wrote {OUT_FILE}")
    print(f"Sample: {payload['meta']['sampleStart']} -> {payload['meta']['sampleEnd']} "
          f"({len(payload['dates'])} months)")


if __name__ == "__main__":
    main()
