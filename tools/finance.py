# -*- coding: utf-8 -*-
"""Finance and business calculators."""

from __future__ import annotations

import math

from .common import ok, parse_float, split_pipe, to_ascii_digits
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


def _money(value: float) -> str:
    return f"{round(value):,}"


def _pct(value: float) -> str:
    return f"{value:,.2f}%"


# --------------------------------------------------------------------------
# Currency formatter
# --------------------------------------------------------------------------

_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "IRR": "ریال", "AED": "د.إ",
    "TRY": "₺", "JPY": "¥", "CNY": "¥", "RUB": "₽", "INR": "₹",
}
_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def _localize_digits(value: str, target: str) -> str:
    if target == "fa":
        return "".join(_FA_DIGITS[int(ch)] if ch.isdigit() else ch for ch in value)
    if target == "ar":
        return "".join(_AR_DIGITS[int(ch)] if ch.isdigit() else ch for ch in value)
    return value


def currency_formatter(item: Input) -> Output:
    value_text, currency, locale = split_pipe(item.require_text(), 3, from_right=False, strip=True)
    value = parse_float(value_text)
    currency = (currency or "IRR").upper()
    locale = locale or "fa-IR"
    symbol = _SYMBOLS.get(currency, currency)
    decimal = f"{value:,.2f}"
    if locale.startswith("fa"):
        formatted = _localize_digits(decimal, "fa").replace(",", "٬").replace(".", "٫") + " " + symbol
        plain = _localize_digits(f"{value:,.2f}", "fa").replace(",", "٬").replace(".", "٫")
    elif locale.startswith("ar"):
        formatted = _localize_digits(decimal, "ar").replace(",", "٬").replace(".", "٫") + " " + symbol
        plain = _localize_digits(f"{value:,.2f}", "ar").replace(",", "٬").replace(".", "٫")
    elif locale.startswith("de"):
        formatted = decimal.replace(",", "X").replace(".", ",").replace("X", ".") + " " + symbol
        plain = formatted
    else:
        formatted = symbol + decimal if currency in {"USD", "GBP", "JPY", "CNY", "INR"} else decimal + " " + symbol
        plain = decimal
    return ok(
        "\n".join(
            [
                f"Formatted: {formatted}",
                f"Decimal: {plain}",
                f"Toman (value / 10): {_localize_digits(_money(value / 10), 'fa') if locale.startswith('fa') else _money(value / 10)}",
                f"Rial (value × 10): {_localize_digits(_money(value * 10), 'fa') if locale.startswith('fa') else _money(value * 10)}",
            ]
        ),
        title="Currency Formatter",
    )


_register(make_tool("currency-formatter", currency_formatter, title="Currency Formatter", hint="value|currency|locale"))


# --------------------------------------------------------------------------
# Discount / margin / VAT
# --------------------------------------------------------------------------

def discount_calc(item: Input) -> Output:
    price, rate = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    price_value, rate_value = parse_float(price), parse_float(rate)
    saved = price_value * rate_value / 100
    return ok(f"Final: {_money(price_value - saved)}\nSaved: {_money(saved)}", title="Discount")


def margin_calc(item: Input) -> Output:
    price, cost = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    price_value, cost_value = parse_float(price), parse_float(cost)
    if price_value <= 0:
        raise ToolError("Selling price must be positive.")
    profit = price_value - cost_value
    margin = profit / price_value * 100
    markup = profit / cost_value * 100 if cost_value > 0 else float("nan")
    return ok(
        f"Profit: {_money(profit)}\nMargin: {_pct(margin)}\nMarkup: {_pct(markup) if math.isfinite(markup) else '-'}",
        title="Margin / Markup",
    )


def vat_add(item: Input) -> Output:
    net, rate = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    net_value, rate_value = parse_float(net), parse_float(rate)
    tax = net_value * rate_value / 100
    return ok(f"Net: {_money(net_value)}\nTax: {_money(tax)}\nGross: {_money(net_value + tax)}", title="VAT Add")


def vat_remove(item: Input) -> Output:
    gross, rate = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    gross_value, rate_value = parse_float(gross), parse_float(rate)
    net = gross_value / (1 + rate_value / 100)
    return ok(f"Net: {_money(net)}\nTax: {_money(gross_value - net)}\nGross: {_money(gross_value)}", title="VAT Remove")


_register(make_tool("discount-vat-calculator", discount_calc, title="Discount Calculator", hint="price|percent"))
_register(make_tool("discount-vat-calculator", margin_calc, id="margin-calculator", title="Margin / Markup", hint="price|cost"))
_register(make_tool("discount-vat-calculator", vat_add, id="vat-add", title="VAT Add", hint="net|percent"))
_register(make_tool("discount-vat-calculator", vat_remove, id="vat-remove", title="VAT Remove", hint="gross|percent"))


# --------------------------------------------------------------------------
# Interest / CAGR / ROI
# --------------------------------------------------------------------------

def compound_interest(item: Input) -> Output:
    principal, rate, years, compounds = split_pipe(item.require_text(), 4, from_right=False, strip=True)
    p = parse_float(principal)
    r = parse_float(rate) / 100
    t = parse_float(years)
    n = parse_float(compounds or "12")
    if p <= 0 or t <= 0 or n <= 0:
        raise ToolError("Principal, years and compounding must be positive.")
    amount = p * (1 + r / n) ** (n * t)
    return ok(f"Final amount: {_money(amount)}\nInterest: {_money(amount - p)}", title="Compound Interest")


def cagr(item: Input) -> Output:
    begin, end, years = split_pipe(item.require_text(), 3, from_right=False, strip=True)
    b, e, t = parse_float(begin), parse_float(end), parse_float(years)
    if b <= 0 or e <= 0 or t <= 0:
        raise ToolError("All values must be positive.")
    value = ((e / b) ** (1 / t) - 1) * 100
    return ok(_pct(value), title="CAGR")


def roi(item: Input) -> Output:
    gain, cost = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    gain_value, cost_value = parse_float(gain), parse_float(cost)
    if cost_value <= 0:
        raise ToolError("Cost must be positive.")
    return ok(_pct(gain_value / cost_value * 100), title="ROI")


_register(make_tool("interest-calculator", compound_interest, title="Compound Interest", hint="principal|rate|years|compounds"))
_register(make_tool("interest-calculator", cagr, id="cagr", title="CAGR", hint="begin|end|years"))
_register(make_tool("interest-calculator", roi, id="roi", title="ROI", hint="gain|cost"))


# --------------------------------------------------------------------------
# Loan
# --------------------------------------------------------------------------

def loan_calculator(item: Input) -> Output:
    principal, rate, months = split_pipe(item.require_text(), 3, from_right=False, strip=True)
    p = parse_float(principal)
    annual = parse_float(rate)
    n = int(parse_float(months))
    if p <= 0 or n <= 0:
        raise ToolError("Principal and months must be positive.")
    monthly_rate = annual / 100 / 12
    if monthly_rate == 0:
        payment = p / n
    else:
        payment = p * monthly_rate / (1 - (1 + monthly_rate) ** -n)
    total = payment * n
    lines = [
        f"Monthly payment: {_money(payment)}",
        f"Total paid: {_money(total)}",
        f"Total interest: {_money(total - p)}",
        "",
        "Month | Payment | Principal | Interest | Balance",
    ]
    balance = p
    for month in range(1, min(n, 6) + 1):
        interest = balance * monthly_rate
        principal_part = payment - interest
        balance -= principal_part
        lines.append(
            f"{month} | {_money(payment)} | {_money(principal_part)} | {_money(interest)} | {_money(max(0, balance))}"
        )
    return ok("\n".join(lines), title="Loan Calculator")


_register(make_tool("loan-calculator", loan_calculator, title="Loan Calculator", hint="principal|annual_rate|months"))


# --------------------------------------------------------------------------
# Salary
# --------------------------------------------------------------------------

def salary_converter(item: Input) -> Output:
    amount, basis, hours_week, weeks_year = split_pipe(item.require_text(), 4, from_right=False, strip=True)
    value = parse_float(amount)
    basis = (basis or "monthly").lower()
    hours = parse_float(hours_week or "40")
    weeks = parse_float(weeks_year or "52")
    if hours <= 0 or weeks <= 0:
        raise ToolError("Hours/week and weeks/year must be positive.")
    hours_year = hours * weeks
    if basis.startswith("hour"):
        annual = value * hours_year
    elif basis.startswith("month"):
        annual = value * 12
    else:
        annual = value
    return ok(
        "\n".join(
            [
                f"Hourly: {_money(annual / hours_year)}",
                f"Monthly: {_money(annual / 12)}",
                f"Annual: {_money(annual)}",
            ]
        ),
        title="Salary Converter",
    )


_register(make_tool("salary-converter", salary_converter, title="Salary Converter", hint="amount|hourly/monthly/annual|hours_week|weeks_year"))
