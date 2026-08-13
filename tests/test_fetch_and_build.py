"""fetch_and_build.py icindeki saf mantik fonksiyonlari icin testler.
Ag cagrisi yapan fonksiyonlar (fetch_range, send_telegram) kapsanmaz.

Calistirmak icin (repo kok dizininde):
    pip install -r requirements.txt -r requirements-dev.txt
    pytest
"""
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import fetch_and_build as fb  # noqa: E402


def test_previous_business_day_from_weekday():
    # 2026-08-13 Persembe -> onceki is gunu 2026-08-12 Carsamba
    d = datetime(2026, 8, 13)
    assert fb.previous_business_day(d).date() == date(2026, 8, 12)


def test_previous_business_day_skips_weekend():
    # 2026-08-10 Pazartesi -> onceki is gunu 2026-08-07 Cuma
    d = datetime(2026, 8, 10)
    assert fb.previous_business_day(d).date() == date(2026, 8, 7)


def test_current_or_previous_business_day_weekday_returns_same_day():
    d = date(2026, 8, 13)  # Persembe
    assert fb.current_or_previous_business_day(d) == d


def test_current_or_previous_business_day_weekend_returns_friday():
    d = date(2026, 8, 15)  # Cumartesi
    assert fb.current_or_previous_business_day(d) == date(2026, 8, 14)
    d2 = date(2026, 8, 16)  # Pazar
    assert fb.current_or_previous_business_day(d2) == date(2026, 8, 14)


def test_business_days_between_excludes_weekend():
    start = date(2026, 8, 7)  # Cuma (haric)
    end = date(2026, 8, 12)  # Carsamba (dahil)
    days = fb.business_days_between(start, end)
    assert [d.strftime("%Y-%m-%d") for d in days] == [
        "2026-08-10", "2026-08-11", "2026-08-12",
    ]


def test_business_days_between_empty_when_no_gap():
    start = date(2026, 8, 12)
    end = date(2026, 8, 12)
    assert fb.business_days_between(start, end) == []


def test_annualized_return_positive():
    # Gunluk %0.05 getiri, yillik yaklasik %19.8 civarinda olmali (bilesik).
    result = fb.annualized_return(0.05, 1)
    assert result is not None
    assert 15 < result < 25


def test_annualized_return_none_when_pct_none():
    assert fb.annualized_return(None, 30) is None


def test_annualized_return_matches_yearly_period():
    # 365 gunluk donem icin yillik getiri, donem getirisinin kendisine esit olmali.
    result = fb.annualized_return(12.3, 365)
    assert round(result, 6) == round(12.3, 6)


def test_send_telegram_noop_without_env(monkeypatch, capsys):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    # Secret tanimli degilse hicbir istek atilmamali ve hata firlatilmamali.
    fb.send_telegram("test mesaji")
    captured = capsys.readouterr()
    assert captured.out == ""
