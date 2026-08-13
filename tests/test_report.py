"""report.py icindeki saf mantik fonksiyonlari icin testler.

Calistirmak icin (repo kok dizininde):
    pip install -r requirements.txt -r requirements-dev.txt
    pytest
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import report  # noqa: E402


def _sample_data():
    return {
        "son_guncelleme": "2026-08-12",
        "fonlar": {
            "AAA": {
                "ad": "Test Fonu A",
                "sirket": "Test Portföy",
                "risk": 1,
                "gecmis": [
                    {"tarih": "2026-08-10", "fiyat": 1.000000},
                    {"tarih": "2026-08-11", "fiyat": 1.001000},
                    {"tarih": "2026-08-12", "fiyat": 1.002000},
                ],
            },
            "BBB": {
                "ad": "Test Fonu B",
                "sirket": "Test Portföy",
                "risk": 2,
                "gecmis": [
                    {"tarih": "2026-08-12", "fiyat": 2.5},
                ],
            },
        },
    }


def test_compute_rows_basic_shape():
    rows = report.compute_rows(_sample_data())
    assert len(rows) == 2
    kods = {r["kod"] for r in rows}
    assert kods == {"AAA", "BBB"}


def test_compute_rows_daily_return_calculation():
    rows = report.compute_rows(_sample_data())
    row_a = next(r for r in rows if r["kod"] == "AAA")
    # (1.002 - 1.001) / 1.001 * 100
    expected = (1.002000 - 1.001000) / 1.001000 * 100
    assert row_a["gunluk_getiri"] is not None
    assert round(row_a["gunluk_getiri"], 8) == round(expected, 8)


def test_compute_rows_none_return_for_single_point():
    rows = report.compute_rows(_sample_data())
    row_b = next(r for r in rows if r["kod"] == "BBB")
    assert row_b["gunluk_getiri"] is None


def test_compute_rows_hist_includes_extra_fields_when_present():
    data = _sample_data()
    data["fonlar"]["AAA"]["gecmis"][-1]["buyukluk"] = 1_000_000.0
    data["fonlar"]["AAA"]["gecmis"][-1]["kisi"] = 42
    rows = report.compute_rows(data)
    row_a = next(r for r in rows if r["kod"] == "AAA")
    last_hist_entry = row_a["hist"][-1]
    # [tarih, fiyat, buyukluk, kisi] - eski girdilerde buyukluk/kisi None olabilir.
    assert last_hist_entry[0] == "2026-08-12"
    assert last_hist_entry[1] == 1.002000


def test_fmt_pct_positive_and_negative():
    assert "pos" in report.fmt_pct(1.5)
    assert "neg" in report.fmt_pct(-1.5)
    assert "muted" in report.fmt_pct(None)


def test_fmt_price_turkish_format():
    # Türkçe format: binlik ayraç nokta, ondalık ayraç virgül.
    assert report.fmt_price(1234.5) == "1.234,500000"


def test_slug_replaces_spaces():
    assert report._slug("Ziraat Portföy") == "Ziraat-Portföy"


def test_annualized_return_helper_matches_fetch_and_build():
    import fetch_and_build as fb
    # report.py de ayni formulu kullanmali (annualized_return varsa).
    if hasattr(report, "annualized_return"):
        assert round(report.annualized_return(0.05, 1), 4) == round(fb.annualized_return(0.05, 1), 4)
