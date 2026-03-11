"""Scraper for district heating price data from waermepreise.info."""

import re
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

URL = "https://www.waermepreise.info/"
TABLE_ID = "tablepress-27"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Canonical column names mapped from raw header text
COLUMN_MAP = {
    "Bundesland": "Bundesland",
    "Stadt": "Stadt",
    "Unternehmen": "Unternehmen",
    "Teilnetz": "Teilnetz",
    "EFH in ct/kWh (brutto)": "EFH_ct_kWh",
    "MFH in ct/kWh (brutto)": "MFH_ct_kWh",
    "Industrie in ct/kWh (brutto)": "Industrie_ct_kWh",
    "Anpassungszyklus": "Anpassungszyklus",
    "Preisstand": "Preisstand",
    "Lieferumfang des Anschlusses (nicht im Preis enthalten)": "Lieferumfang",
    "Netzgröße in MW": "Netzgroesse_MW",
    "Netzverluste in MWh/a": "Netzverluste_MWh",
    "Netzverluste": "Netzverluste_pct",
    "Energieträger": "Energietraeger",
    "Anteil EE & KE": "Anteil_EE_KE",
    "Anteil KWK": "Anteil_KWK",
    "PEF": "PEF",
    "Internetseite": "Internetseite",
}


def _extract_header_text(th) -> str:
    """Extract plain text from a <th>, stripping tooltip spans."""
    for span in th.find_all("span", class_="tooltip-text"):
        span.decompose()
    return th.get_text(separator=" ", strip=True)


def fetch_table() -> pd.DataFrame:
    """Fetch and parse the price table from waermepreise.info."""
    print(f"Fetching data from {URL} ...")
    response = requests.get(URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    table = soup.find("table", id=TABLE_ID)
    if table is None:
        raise RuntimeError(
            f"Table '{TABLE_ID}' not found on page. "
            "The website structure may have changed."
        )

    # Parse headers
    raw_headers = [_extract_header_text(th) for th in table.select("thead th")]

    # Normalize headers: try direct match, then partial match
    columns = []
    for raw in raw_headers:
        # Remove soft-hyphens, then normalize whitespace
        clean = re.sub(r"\u00ad", "", raw)
        clean = re.sub(r"\s+", " ", clean).strip()
        matched = None
        for key, canonical in COLUMN_MAP.items():
            if clean == key or clean.startswith(key):
                matched = canonical
                break
        columns.append(matched if matched else clean)

    # Parse rows
    rows = []
    for tr in table.select("tbody tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) == len(columns):
            rows.append(dict(zip(columns, cells)))

    df = pd.DataFrame(rows, columns=columns)
    print(f"  Scraped {len(df)} rows, {len(df.columns)} columns.")
    return df


def load_or_scrape(cache_path: str | Path, refresh: bool = False) -> pd.DataFrame:
    """Load data from CSV cache or scrape fresh if needed.

    Args:
        cache_path: Path to the CSV cache file.
        refresh: If True, always re-scrape even if cache exists.
    """
    cache_path = Path(cache_path)
    if not refresh and cache_path.exists():
        print(f"Loading cached data from {cache_path} ...")
        df = pd.read_csv(cache_path, dtype=str)
        print(f"  Loaded {len(df)} rows.")
        return df

    df = fetch_table()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)
    print(f"  Saved to {cache_path}")
    return df
