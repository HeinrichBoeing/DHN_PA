# DHN_PA – District Heating Price Analysis

A Python tool that scrapes district heating (Fernwärme) price data from [waermepreise.info](https://www.waermepreise.info/) and computes weighted average prices by customer type and Bundesland.

## Features

- Scrapes all ~700 network entries from the public price transparency table
- Caches data locally as CSV to avoid repeated scraping
- Computes **Wärmeabsatz-weighted** average prices for EFH, MFH, and Industrie
- Outputs two charts:
  - National weighted average prices (bar chart)
  - Weighted average prices per Bundesland (grouped bar chart, sorted by EFH price, with national reference lines)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Scrape data (or load from cache) and show charts
python main.py

# Force re-scrape even if cached CSV exists
python main.py --refresh

# Use a custom directory for the cached CSV
python main.py --data-dir /path/to/dir
```

## Data & Methodology

### Source

Data is sourced from [waermepreise.info](https://www.waermepreise.info/), a German price transparency platform covering more than half of national district heating sales. Prices are reported as mixed prices (Mischpreise) per customer type:

| Type | Profile |
|------|---------|
| **EFH** | Einfamilienhaus – 15 kW / 27,000 kWh/a |
| **MFH** | Mehrfamilienhaus – 160 kW / 288,000 kWh/a |
| **Industrie** | Gewerbe/Industrie – 600 kW / 1,080,000 kWh/a |

Prices are displayed as **netto** (excl. 19% VAT).

### Weighting

The weighted average uses each network's estimated **Wärmeabsatz** (heat sales volume in MWh) as the weight. This is derived from the dataset in priority order:

1. **Netzverluste in MWh/a** and **Netzverluste %** both available:
   `Wärmeabsatz = Netzverluste_MWh / (Netzverluste_% / 100)`
2. **Netzverluste %** missing → assume **15 %**:
   `Wärmeabsatz = Netzverluste_MWh / 0.15`
3. **Netzverluste in MWh/a** missing → estimate from network capacity:
   `Wärmeabsatz = Netzgröße_MW × 1,700 Vollbenutzungsstunden`
4. **Both missing** → equal weighting (weight = 1)

## Project Structure

```
DHN_PA/
├── main.py           # CLI entry point
├── scraper.py        # Fetches and parses HTML table → CSV cache
├── analysis.py       # Weighted averages + matplotlib charts
├── requirements.txt  # Dependencies
└── data/
    └── waermepreise.csv  # Cached data (auto-generated)
```

## Adding Further Analyses

Add new analysis functions in `analysis.py` and call them from `run_analysis()`. The cleaned DataFrame passed to `run_analysis()` contains all 18 original columns plus the computed `Waermeabsatz_MWh` weight column.

## License

GNU General Public License v3 – see [LICENSE](LICENSE).
