"""Analysis and visualization of district heating price data."""

import re

import matplotlib as mpl
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

# Register and apply Frutiger LT Com Light as the default font
_FONT_PATH = (
    r"C:\Users\hei24918\AppData\Local\Microsoft\Windows\Fonts\FrutigerLTCom-Light.ttf"
)
fm.fontManager.addfont(_FONT_PATH)
mpl.rcParams["font.family"] = "Frutiger LT Com"
mpl.rcParams["font.weight"] = "light"

PRICE_COLS = ["EFH_ct_kWh", "MFH_ct_kWh", "Industrie_ct_kWh"]
PRICE_LABELS = ["EFH", "MFH", "Industrie"]
COLORS = ["#2196F3", "#FF9800", "#4CAF50"]

# Vollbenutzungsstunden used to estimate Wärmeabsatz from Netzgröße
VOLLBENUTZUNGSSTUNDEN = 1700
# Netzverluste
DEFAULT_NETZVERLUSTE_PCT = 0.15
# Umsatzsteuer factor to convert brutto → netto
VAT_FACTOR = 1.19


# ---------------------------------------------------------------------------
# Netzgröße parsing
# ---------------------------------------------------------------------------

def _parse_netzgroesse(value: str) -> float | None:
    """Convert 'Netzgröße in MW' text to a numeric midpoint in MW."""
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip()

    # "größer als 200 MW" → use 250 as reasonable estimate
    m = re.match(r"gr[oöÖ]ßer als\s*([\d.,]+)", v, re.IGNORECASE)
    if m:
        lower = float(m.group(1).replace(",", "."))
        return lower * 1.25  # e.g. >200 MW → 250 MW

    # "kleiner als 5 MW" → use half as estimate
    m = re.match(r"kleiner als\s*([\d.,]+)", v, re.IGNORECASE)
    if m:
        upper = float(m.group(1).replace(",", "."))
        return upper * 0.5  # e.g. <5 MW → 2.5 MW

    # "5 - 20 MW" → midpoint = 12.5
    m = re.match(r"([\d.,]+)\s*[-–]\s*([\d.,]+)", v)
    if m:
        lo = float(m.group(1).replace(",", "."))
        hi = float(m.group(2).replace(",", "."))
        return (lo + hi) / 2

    # bare number
    m = re.match(r"([\d.,]+)", v)
    if m:
        return float(m.group(1).replace(",", "."))

    return None


# ---------------------------------------------------------------------------
# Percentage parsing
# ---------------------------------------------------------------------------

def _parse_pct(value: str) -> float | None:
    """Parse percentage strings like '15%', '<5%', '>90%' to a float (0–100)."""
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip()
    m = re.search(r"([\d.,]+)\s*%", v)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


# ---------------------------------------------------------------------------
# Data cleaning
# ---------------------------------------------------------------------------

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Parse raw string columns to numeric types and compute Wärmeabsatz weight."""
    df = df.copy()

    # Price columns: German decimal comma → float, then convert brutto → netto (÷ 1.19)
    for col in PRICE_COLS:
        if col in df.columns:
            df[col] = (
                df[col]
                .str.replace(",", ".", regex=False)
                .pipe(pd.to_numeric, errors="coerce")
                / VAT_FACTOR
            )

    # Netzverluste in MWh/a: strip thousand-separators (dots), then parse
    if "Netzverluste_MWh" in df.columns:
        df["Netzverluste_MWh"] = (
            df["Netzverluste_MWh"]
            .str.replace(".", "", regex=False)  # remove thousand dots
            .str.replace(",", ".", regex=False)  # decimal comma
            .pipe(pd.to_numeric, errors="coerce")
        )

    # Netzverluste % column
    if "Netzverluste_pct" in df.columns:
        df["Netzverluste_pct"] = df["Netzverluste_pct"].apply(_parse_pct)

    # Netzgröße in MW
    if "Netzgroesse_MW" in df.columns:
        df["Netzgroesse_MW_num"] = df["Netzgroesse_MW"].apply(_parse_netzgroesse)

    # Compute Wärmeabsatz (MWh) – used as weight
    df["Waermeabsatz_MWh"] = _compute_waermeabsatz(df)

    # Drop rows where all three prices are missing
    df = df.dropna(subset=PRICE_COLS, how="all")

    return df


def _compute_waermeabsatz(df: pd.DataFrame) -> pd.Series:
    """Compute Wärmeabsatz (MWh) for each row using the priority fallback logic."""
    result = pd.Series(index=df.index, dtype=float)

    for idx, row in df.iterrows():
        mwh = row.get("Netzverluste_MWh")
        pct = row.get("Netzverluste_pct")
        netz_mw = row.get("Netzgroesse_MW_num")

        has_mwh = pd.notna(mwh) and mwh > 0
        has_pct = pd.notna(pct) and pct > 0
        has_netz = pd.notna(netz_mw) and netz_mw > 0

        if has_mwh and has_pct:
            # Primary: derive from losses
            result[idx] = mwh / (pct / 100)
        elif has_mwh:
            # % missing → assume default
            result[idx] = mwh / DEFAULT_NETZVERLUSTE_PCT
        elif has_netz:
            # MWh missing → estimate from network size
            result[idx] = netz_mw * VOLLBENUTZUNGSSTUNDEN
        else:
            result[idx] = np.nan

    return result


# ---------------------------------------------------------------------------
# Weighted average calculation
# ---------------------------------------------------------------------------

def weighted_avg(df: pd.DataFrame, group_col: str | None = None) -> pd.DataFrame:
    """Compute weighted average prices, optionally grouped by a column.

    Rows without a valid Wärmeabsatz weight fall back to equal weighting (weight=1).
    Rows where a specific price is NaN are excluded from that price's average.

    Returns a DataFrame with columns: [group_col,] EFH_ct_kWh, MFH_ct_kWh, Industrie_ct_kWh
    """
    if group_col:
        groups = df.groupby(group_col, sort=False)
        records = []
        for name, grp in groups:
            record = {group_col: name}
            record.update(_weighted_avg_row(grp))
            records.append(record)
        return pd.DataFrame(records)
    else:
        record = _weighted_avg_row(df)
        return pd.DataFrame([record])


def _weighted_avg_row(df: pd.DataFrame) -> dict:
    result = {}
    weights_default = np.where(df["Waermeabsatz_MWh"].isna(), 1.0, df["Waermeabsatz_MWh"])
    for col in PRICE_COLS:
        mask = df[col].notna()
        if mask.sum() == 0:
            result[col] = np.nan
        else:
            prices = df.loc[mask, col].values
            w = np.where(
                df.loc[mask, "Waermeabsatz_MWh"].isna(),
                1.0,
                df.loc[mask, "Waermeabsatz_MWh"].values,
            )
            result[col] = np.average(prices, weights=w)
    return result


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_total(avg_total: pd.DataFrame) -> None:
    """Bar chart of overall weighted average prices for EFH, MFH, Industrie."""
    values = [avg_total.iloc[0][col] for col in PRICE_COLS]

    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(PRICE_LABELS, values, color=COLORS, width=0.5, edgecolor="white")

    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.15,
            f"{val:.2f}",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )

    ax.set_title(
        "Gewichtete Durchschnittspreise Fernwärme\n(Deutschland gesamt)",
        fontsize=13,
        pad=12,
    )
    ax.set_ylabel("ct/kWh (netto)", fontsize=11)
    ax.set_ylim(0, max(values) * 1.2)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    fig.tight_layout()


def plot_by_bundesland(avg_bl: pd.DataFrame, avg_total: pd.DataFrame) -> None:
    """Grouped bar chart of weighted average prices per Bundesland."""
    # Sort by EFH price ascending
    avg_bl = avg_bl.sort_values("EFH_ct_kWh", ascending=True).reset_index(drop=True)

    n = len(avg_bl)
    x = np.arange(n)
    width = 0.25

    fig, ax = plt.subplots(figsize=(max(14, n * 0.9), 6))

    for i, (col, label, color) in enumerate(zip(PRICE_COLS, PRICE_LABELS, COLORS)):
        offsets = x + (i - 1) * width
        bars = ax.bar(offsets, avg_bl[col], width=width, label=label, color=color, edgecolor="white")

    # Reference lines for national averages
    line_styles = ["--", "-.", ":"]
    for col, label, color, ls in zip(PRICE_COLS, PRICE_LABELS, COLORS, line_styles):
        nat_avg = avg_total.iloc[0][col]
        ax.axhline(nat_avg, color=color, linestyle=ls, linewidth=1.5, alpha=0.8,
                   label=f"Ø {label} (DE): {nat_avg:.2f} ct/kWh")

    ax.set_xticks(x)
    ax.set_xticklabels(avg_bl["Bundesland"], rotation=40, ha="right", fontsize=9)
    ax.set_title(
        "Gewichtete Durchschnittspreise Fernwärme nach Bundesland",
        fontsize=13,
        pad=12,
    )
    ax.set_ylabel("ct/kWh (netto)", fontsize=11)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.legend(fontsize=9, ncol=2, loc="upper left")
    fig.tight_layout()


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------

def run_analysis(df: pd.DataFrame) -> None:
    """Run the full analysis pipeline and display charts."""
    print("Cleaning data ...")
    df_clean = clean_data(df)
    print(f"  {len(df_clean)} rows after cleaning.")

    weight_ok = df_clean["Waermeabsatz_MWh"].notna().sum()
    weight_fallback = df_clean["Waermeabsatz_MWh"].isna().sum()
    print(f"  Wärmeabsatz: {weight_ok} rows with weight, {weight_fallback} rows using equal fallback.")

    print("Computing weighted averages ...")
    avg_total = weighted_avg(df_clean)
    avg_bl = weighted_avg(df_clean, group_col="Bundesland")

    print("\n--- Gewichtete Durchschnittspreise (Deutschland gesamt) ---")
    for col, label in zip(PRICE_COLS, PRICE_LABELS):
        print(f"  {label}: {avg_total.iloc[0][col]:.2f} ct/kWh")

    print("\n--- Gewichtete Durchschnittspreise nach Bundesland ---")
    print(avg_bl.set_index("Bundesland")[PRICE_COLS].round(2).to_string())

    print("\nGenerating charts ...")
    plot_total(avg_total)
    plot_by_bundesland(avg_bl, avg_total)
    plt.show()
