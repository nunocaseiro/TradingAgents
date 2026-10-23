from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yfinance as yf

from tradingagents.dataflows import date_window
from tradingagents.dataflows.date_window import (
    withhold_live_profile,
    withhold_undated_statements,
    withhold_undisclosed_trades,
)
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.net import vendor_reachable
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.common import (
    YAHOO_HOST,
    raise_for_empty,
    yf_retry,
)

# Quote currencies Yahoo gives in a minor unit, and the main unit of each.
_MAIN_UNIT = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str, "analysis date in YYYY-MM-DD format"] = None
):
    """Get company fundamentals overview from yfinance.

    ``Ticker.info`` is a present-day snapshot with no historical vintage, so a
    past ``as_of_date`` withholds it through the shared point-in-time guard
    (``date_window.withhold_live_profile``, #1300).
    """
    canonical = normalize_symbol(ticker)

    # Guard before the request: the response would only be discarded, and the
    # answer does not depend on it.
    withheld = withhold_live_profile(as_of_date, canonical)
    if withheld:
        return withheld

    info = yf_retry(lambda: yf.Ticker(canonical).info)
    if not info:
        raise_for_empty(ticker, canonical, "fundamentals")

    # Yahoo gives these two in percent (dividendYield 0.41 is 0.41%; debtToEquity
    # 78.4 is 78.4%, a ratio of 0.78) but the margins and returns as fractions,
    # so each carries its unit.
    dividend_yield, debt_to_equity = info.get("dividendYield"), info.get("debtToEquity")
    # Money figures come in three currencies (#1456): price levels in the quote
    # currency, which can be a minor unit (London in pence, GBp); market cap and
    # per-share figures in that currency's main unit (GBP), as Yahoo's own P/E
    # and P/B are computed against them; income figures in the currency the
    # company reports in (an ADR quotes in USD, reports in TWD), or bare when
    # Yahoo does not say which.
    quote = info.get("currency")
    main = _MAIN_UNIT.get(quote, quote)
    reported = info.get("financialCurrency")

    def money(key, currency):
        value = info.get(key)
        return None if value is None else f"{value} {currency}" if currency else value

    fields = [
        ("Name", info.get("longName")),
        ("Sector", info.get("sector")),
        ("Industry", info.get("industry")),
        ("Market Cap", money("marketCap", main)),
        ("PE Ratio (TTM)", info.get("trailingPE")),
        ("Forward PE", info.get("forwardPE")),
        ("PEG Ratio", info.get("pegRatio")),
        ("Price to Book", info.get("priceToBook")),
        ("EPS (TTM)", money("trailingEps", main)),
        ("Forward EPS", money("forwardEps", main)),
        ("Dividend Yield", None if dividend_yield is None else f"{dividend_yield}%"),
        ("Beta", info.get("beta")),
        ("52 Week High", money("fiftyTwoWeekHigh", quote)),
        ("52 Week Low", money("fiftyTwoWeekLow", quote)),
        ("50 Day Average", money("fiftyDayAverage", quote)),
        ("200 Day Average", money("twoHundredDayAverage", quote)),
        ("Revenue (TTM)", money("totalRevenue", reported)),
        ("Gross Profit", money("grossProfits", reported)),
        ("EBITDA", money("ebitda", reported)),
        ("Net Income", money("netIncomeToCommon", reported)),
        ("Profit Margin", info.get("profitMargins")),
        ("Operating Margin", info.get("operatingMargins")),
        ("Return on Equity", info.get("returnOnEquity")),
        ("Return on Assets", info.get("returnOnAssets")),
        ("Debt to Equity", None if debt_to_equity is None
         else f"{debt_to_equity}% ({debt_to_equity / 100:.2f}x)"),
        ("Current Ratio", info.get("currentRatio")),
        ("Book Value", money("bookValue", main)),
        ("Free Cash Flow", money("freeCashflow", reported)),
    ]

    lines = [f"{label}: {v}" for label, v in fields if v is not None]

    # yfinance returns a stub dict (e.g. {"trailingPegRatio": None}) for
    # unknown symbols, so `info` is truthy but every field is empty. Treat
    # "no usable fields" as no data rather than emitting a bare header the
    # agent might fabricate around.
    if not lines:
        raise_for_empty(ticker, canonical, "fundamental fields")

    report = f"# Company Fundamentals for {canonical}\n\n" + "\n".join(lines)
    # Asked only for a symbol that reports earnings: funds, indices and crypto
    # have no calendar, and the request would be wasted.
    calendar = _earnings_calendar(canonical) if info.get("earningsTimestamp") else {}
    outlook = _earnings_and_consensus(info, calendar, quote, main, reported)
    if outlook:
        report += "\n\n## Next Earnings and Analyst Consensus\n\n" + "\n".join(outlook)
    return report


def _earnings_calendar(canonical: str) -> dict:
    """Yahoo's earnings calendar for ``canonical``, or {} when it has none or cannot be reached.

    The calendar only adds the quarter's estimates to the overview, so a failed
    request leaves them out rather than costing the overview.
    """
    try:
        calendar = yf_retry(lambda: yf.Ticker(canonical).calendar)
    except VendorUnavailableError:
        return {}
    return calendar if isinstance(calendar, dict) else {}


def _exchange_zone(info: dict):
    """The listing exchange's time zone, so dates fall on the exchange's day; UTC when unknown."""
    try:
        return ZoneInfo(info.get("exchangeTimezoneName") or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return UTC


def _with_unit(value, currency):
    return f"{value} {currency}" if currency else f"{value}"


def _estimate(calendar: dict, name: str, currency) -> str | None:
    """'average CUR (low x, high y)' for one of the calendar's estimates, or None."""
    average = calendar.get(f"{name} Average")
    if average is None:
        return None
    low, high = calendar.get(f"{name} Low"), calendar.get(f"{name} High")
    spread = f" (low {low}, high {high})" if low is not None and high is not None else ""
    return _with_unit(average, currency) + spread


def _earnings_and_consensus(info: dict, calendar: dict, quote, main, reported) -> list[str]:
    """The next earnings date, the quarter's estimates and the analyst consensus.

    Price targets are in the quote currency like the other price levels; EPS
    estimates in its main unit like the EPS fields; revenue in the reporting
    currency like the income figures.
    """
    zone = _exchange_zone(info)
    lines = []

    timestamp = info.get("earningsTimestamp")
    if timestamp:
        day = datetime.fromtimestamp(timestamp, tz=UTC).astimezone(zone).strftime("%Y-%m-%d")
        if day < date_window.get_current_date():
            lines.append(f"Latest Earnings Date: {day} (already reported; Yahoo has no later date yet)")
        else:
            status = {False: " (confirmed by Yahoo)",
                      True: " (estimated by Yahoo, not confirmed)"}.get(info.get("isEarningsDateEstimate"), "")
            lines.append(f"Next Earnings Date: {day}{status}")
            call = info.get("earningsCallTimestampStart")
            if call:
                call_time = datetime.fromtimestamp(call, tz=UTC).astimezone(zone)
                if call_time.strftime("%Y-%m-%d") == day:
                    lines.append(f"Earnings Call: {call_time:%Y-%m-%d %H:%M %Z}")
            for label, name, currency in (("EPS", "Earnings", main), ("Revenue", "Revenue", reported)):
                estimate = _estimate(calendar, name, currency)
                if estimate:
                    lines.append(f"Next Quarter {label} Estimate: {estimate}")

    target = info.get("targetMeanPrice")
    if target is not None:
        lines.append(f"Analyst Target Mean: {_with_unit(target, quote)}")
    low, high, median = (info.get(k) for k in ("targetLowPrice", "targetHighPrice", "targetMedianPrice"))
    if low is not None and high is not None:
        lines.append(f"Analyst Target Range: {low} - {_with_unit(high, quote)}"
                     + (f" (median {median})" if median is not None else ""))
    rating = info.get("recommendationKey")
    if rating and rating != "none":
        mean = info.get("recommendationMean")
        scale = f" (mean {mean}, 1 strong buy - 5 strong sell)" if mean is not None else ""
        lines.append(f"Analyst Recommendation: {rating}{scale}")
    opinions = info.get("numberOfAnalystOpinions")
    if opinions:
        lines.append(f"Number of Analyst Opinions: {opinions}")
    return lines


def _statement(ticker, freq, as_of_date, title, quarterly_attr, annual_attr) -> str:
    """One financial statement as CSV, for a run dated today."""
    canonical = normalize_symbol(ticker)
    withheld = withhold_undated_statements(as_of_date, canonical, title)
    if withheld:
        return withheld
    what = title.lower()
    attr = quarterly_attr if freq.lower() == "quarterly" else annual_attr
    data = yf_retry(lambda: getattr(yf.Ticker(canonical), attr))
    if data is None or data.empty:
        raise_for_empty(ticker, canonical, f"{what} data")
    return f"# {title} data for {canonical} ({freq})\n" + data.to_csv()


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    as_of_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get balance sheet data from yfinance."""
    return _statement(ticker, freq, as_of_date, "Balance Sheet", "quarterly_balance_sheet", "balance_sheet")


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    as_of_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get cash flow data from yfinance."""
    return _statement(ticker, freq, as_of_date, "Cash Flow", "quarterly_cashflow", "cashflow")


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    as_of_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get income statement data from yfinance."""
    return _statement(ticker, freq, as_of_date, "Income Statement", "quarterly_income_stmt", "income_stmt")


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
    as_of_date: Annotated[str | None, "analysis date, yyyy-mm-dd"] = None,
):
    """Get insider transactions data from yfinance, for a run dated today."""
    canonical = normalize_symbol(ticker)
    withheld = withhold_undisclosed_trades(as_of_date, canonical)
    if withheld:
        return withheld
    data = yf_retry(lambda: yf.Ticker(canonical).insider_transactions)

    # Empty is normal here (many valid symbols have no insider filings),
    # so report it plainly rather than treating the symbol as invalid.
    if data is None or data.empty:
        if not vendor_reachable(YAHOO_HOST):
            raise VendorUnavailableError("Yahoo Finance is unreachable; insider filings were not retrieved")
        return f"No insider transactions reported for symbol '{canonical}'"

    return f"# Insider Transactions data for {canonical}\n" + data.to_csv()


def get_company_profile(ticker: str) -> dict:
    """Yahoo's current profile for ``ticker``: name, sector, industry and the like."""
    return yf_retry(lambda: yf.Ticker(normalize_symbol(ticker)).info) or {}
