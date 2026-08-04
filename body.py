"""Combined Smash Guys daily report.

Usage: python3 body.py 2026-07-28

Credentials are read from .env in this folder or, after moving this folder to
Desktop, from the existing SmashGuysAutomationV1/.env file. Originals are not
modified.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://tpb.restroworks.biz"
LOGIN_URL = f"{BASE_URL}/auth/local/newLogin"
DAILY_URL = f"{BASE_URL}/api/bills/getDataRangeBillsForInvoice"
MENU_URL = f"{BASE_URL}/api/bills/getDataForMenuMix"
REMOVED_URL = f"{BASE_URL}/api/bills/getRemovedTaxes"

TENANT_ID = "5a2e7abaff77e3ec6fcb1f2d"
DEPLOYMENT_ID = "6a339e787cccc549cd511487"
BRAND_ID = "680c73fcf78d6a5425eaf954"
SBRAND_ID = "680c784ecdabd84d1b9643fb"
CLUSTER_ID = "6a3397c3fd92c1125f96d173"
BRAND_LABEL = "SG WF"

CUTOFF_REFERENCE = "2026-06-17T23:30:00.000Z"
CUTOFF_TIME = datetime.strptime(CUTOFF_REFERENCE, "%Y-%m-%dT%H:%M:%S.000Z").time()
APC_DEDUCTION = Decimal("0.05")  # Gross Sale minus 5%, then divided by covers.

COLLECTIONS = (
    "Cash", "Credit Card", "Debit Card", "Coupon", "BTC", "TTR",
    "Smart Card", "Swiggy DineOut", "Eazy Diner",
)
CARD_TYPES = {
    "creditcard": "Credit Card", "debitcard": "Debit Card", "coupon": "Coupon",
    "btc": "BTC", "smartcard": "Smart Card", "online": "TTR",
}
OTHER_TYPES = {"swiggydineout": "Swiggy DineOut", "eazydiner": "Eazy Diner"}


def load_env() -> None:
    here = Path(__file__).resolve().parent
    files = (here / ".env", here.parent / "SmashGuysAutomationV1" / ".env")
    for file in files:
        if not file.exists():
            continue
        for line in file.read_text().splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def credentials() -> tuple[str, str]:
    load_env()
    username, password = os.getenv("RW_USERNAME"), os.getenv("RW_PASSWORD")
    if not username or not password:
        raise RuntimeError("Set RW_USERNAME and RW_PASSWORD in .env before running.")
    return username, password


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def norm(value: Any) -> str:
    return "".join(char for char in str(value).lower() if char.isalnum())


def query_date(business_date: date) -> str:
    value = business_date - timedelta(days=1)
    return f"{value.isoformat()}T{CUTOFF_TIME.isoformat(timespec='milliseconds')}Z"


def headers(token: str, page: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{BASE_URL}{page}",
        "lsbrand_id": BRAND_ID, "lssbrand_id": SBRAND_ID,
        "lscluster_id": CLUSTER_ID, "lsdeployment_id": DEPLOYMENT_ID,
        "lstenant_id": TENANT_ID,
    }


def login() -> tuple[requests.Session, str]:
    username, password = credentials()
    session = requests.Session()
    response = session.post(
        LOGIN_URL,
        json={"username": username, "password": password, "subdomain": "tpb", "extras": {}},
        timeout=30,
    )
    response.raise_for_status()
    token = response.json()["token"]
    session.cookies.set("token", token)
    return session, token


def request_json(session: requests.Session, url: str, hdrs: dict[str, str], params: dict[str, Any]) -> Any:
    response = session.get(url, headers=hdrs, params=params, timeout=120)
    if not response.ok:
        raise RuntimeError(f"{response.status_code} from {url}: {response.text[:500]}")
    return response.json()


def fetch_daily(session: requests.Session, token: str, day: date) -> list[dict[str, Any]]:
    stamp = query_date(day)
    raw = request_json(session, DAILY_URL, headers(token, "/reports/dailySalesSummary"), {
        "API": "getDataRangeBillsForInvoice", "backend": "false",
        "cutOffTimeSetting": CUTOFF_REFERENCE, "deploymentSetting": "false",
        "deployment_id": DEPLOYMENT_ID, "endCutOffTime": CUTOFF_REFERENCE,
        "fromDate": stamp, "multiTab": "", "reportName": "Daily_Sales_Summary",
        "startCutOffTime": CUTOFF_REFERENCE, "tenant_id": TENANT_ID, "toDate": stamp,
    })
    return raw[0] if isinstance(raw, list) and raw and isinstance(raw[0], list) else []


def fetch_menu_mix(session: requests.Session, token: str, day: date) -> list[dict[str, Any]]:
    stamp = query_date(day)
    raw = request_json(session, MENU_URL, headers(token, "/reports/menuMixReport"), {
        "API": "getDataForMenuMix", "backend": "false", "brand_id": BRAND_ID,
        "cutOffTimeSetting": CUTOFF_REFERENCE, "deploymentSetting": "false",
        "deployment_id": DEPLOYMENT_ID, "endCutOffTime": CUTOFF_REFERENCE,
        "fromDate": stamp, "inclusive_tax_on": "false", "menuMixType": "SCategory",
        "reportName": "Menu_Mix", "round_off_tax_on": "false",
        "startCutOffTime": CUTOFF_REFERENCE, "tab": "all", "tabType": "all",
        "tabWiseOption": "Consolidated", "tenant_id": TENANT_ID, "toDate": stamp,
    })
    return raw if isinstance(raw, list) else []


def fetch_removed_charges(session: requests.Session, token: str, day: date) -> list[dict[str, Any]]:
    stamp = query_date(day)
    prefix = {"label": "Bill Print Prefix", "name": "bill_print_prefix", "value": "", "selected": True,
              "fieldType": "text", "group": "Bill Settings", "isEditable": True}
    raw = request_json(session, REMOVED_URL, headers(token, "/reports/RemovedTaxesReport"), {
        "API": "getRemovedTaxes", "backend": "false", "billPrintPrefix": json.dumps(prefix, separators=(",", ":")),
        "cutOffTimeSetting": CUTOFF_REFERENCE, "deploymentSetting": "false", "deployment_id": DEPLOYMENT_ID,
        "endCutOffTime": CUTOFF_REFERENCE, "formatOption": "true", "fromDate": stamp,
        "reportName": "Removed_Charges", "reportOption": "Charges", "startCutOffTime": CUTOFF_REFERENCE,
        "tenant_id": TENANT_ID, "toDate": stamp,
    })
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return raw[0]
    return raw if isinstance(raw, list) else []


def cash_amount(entries: Any) -> Decimal:
    result = Decimal("0")
    for entry in entries or []:
        if isinstance(entry, dict):
            result += money(next((entry[key] for key in ("totalAmount", "amount", "value") if key in entry), 0))
        else:
            result += money(entry)
    return result


def bill_collections(bill: dict[str, Any]) -> dict[str, Decimal]:
    result: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    payments = bill.get("payments") or {}
    result["Cash"] += cash_amount(payments.get("cash"))
    for card in payments.get("cards") or []:
        if not isinstance(card, dict):
            continue
        kind = norm(card.get("cardType"))
        if kind == "other":
            details = card.get("detail") or []
            if details:
                for detail in details:
                    bucket = OTHER_TYPES.get(norm(detail.get("otherName")), "Other")
                    result[bucket] += money(detail.get("amount"))
            else:
                result["Other"] += money(card.get("totalAmount"))
        else:
            result[CARD_TYPES.get(kind, "Unmapped")] += money(card.get("totalAmount"))
    return result


def bill_total(bill: dict[str, Any]) -> Decimal:
    return sum(bill_collections(bill).values(), Decimal("0"))


def bill_round_off(bill: dict[str, Any]) -> Decimal:
    nested = bill.get("bill") if isinstance(bill.get("bill"), dict) else {}
    for source in (nested, bill):
        for key in ("roundOff", "roundOffAmount", "roundoff", "round_off"):
            if key in source:
                return money(source[key])
    return Decimal("0")


def tab_name(bill: dict[str, Any]) -> str:
    data = bill.get("billData") if isinstance(bill.get("billData"), dict) else {}
    return " ".join(str(item) for item in (bill.get("tab"), bill.get("_tab"), data.get("tab")) if item).lower()


def takeaway_bill(bill: dict[str, Any]) -> bool:
    tab = tab_name(bill)
    return bool(bill.get("_isTakeOut") or bill.get("_isDelivery") or "take" in tab or "delivery" in tab)


def staff_bill(bill: dict[str, Any]) -> bool:
    return any(bill.get(key) for key in ("_isStaff", "isStaff", "staffBill", "_isStaffBill")) or "staff" in tab_name(bill)


def daily_metrics(bills: list[dict[str, Any]]) -> dict[str, Any]:
    collections = {key: Decimal("0") for key in COLLECTIONS}
    for bill in bills:
        for key, amount in bill_collections(bill).items():
            if key in collections:
                collections[key] += amount
    gross = sum(collections.values(), Decimal("0")) + sum((bill_round_off(bill) for bill in bills), Decimal("0"))
    covers = sum(int(str(bill.get("_covers", 0) or 0)) for bill in bills)
    ta = [bill for bill in bills if takeaway_bill(bill)]
    staff = [bill for bill in bills if staff_bill(bill)]
    # Operations rule:
    # 1. Deduct 5% from Gross Sales.
    # 2. Deduct the Takeaway amount.
    # 3. Divide the resulting real Dine-in amount by Covers for APC.
    takeaway_amount = sum((bill_total(bill) for bill in ta), Decimal("0"))
    real_dine_in_amount = (gross * (Decimal("1") - APC_DEDUCTION)) - takeaway_amount
    apc = (real_dine_in_amount / covers) if covers else Decimal("0")
    return {
        "bills": len(bills), "covers": covers, "gross": gross, "apc": apc, "collections": collections,
        "apc_principal": real_dine_in_amount,
        "takeaway": (takeaway_amount, len(ta)),
        "staff": (sum((bill_total(bill) for bill in staff), Decimal("0")), len(staff)),
    }


def menu_metrics(rows: list[dict[str, Any]]) -> dict[str, int]:
    beverage = coffee = dessert = burrata = 0
    for row in rows:
        quantity = int(money(row.get("quantity")))
        category, name = str(row.get("superCategoryName") or "").lower(), str(row.get("name") or "").lower()
        beverage += quantity if category == "beverages" else 0
        coffee += quantity if category == "coffee" else 0
        dessert += quantity if category == "desserts" else 0
        burrata += quantity if name == "smashed burrata" else 0
    return {"desserts": dessert, "beverages": beverage + coffee, "burrata": burrata}


def removed_metrics(bills: list[dict[str, Any]]) -> tuple[int, Decimal]:
    total, affected = Decimal("0"), set()
    for bill in bills:
        hit = False
        for kot in bill.get("_kots") or []:
            for item in kot.get("items") or []:
                for tax in item.get("removedTaxes") or []:
                    if tax.get("name") == "S.C.@10%":
                        total += money(tax.get("tax_amount"))
                        hit = True
        if hit:
            affected.add(str(bill.get("_id") or bill.get("billNumber")))
    return len(affected), total


def display_money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('1'), rounding=ROUND_HALF_UP):,.0f}"


def build_ops_message(day: date, daily: dict[str, Any]) -> str:
    """Message for the Ops group. The Dine In line visibly shows APC math."""
    ta_amount, ta_bills = daily["takeaway"]
    staff_amount, staff_bills = daily["staff"]
    return f"""DSR Date : {day:%d/%m/%Y}
Brand : {BRAND_LABEL}
Gross Sale :- {display_money(daily['gross'])}
Dine in APC : {display_money(daily['apc'])}

Dine in : {display_money(daily['apc_principal'])}/{daily['covers']}
TA : {display_money(ta_amount)}/{ta_bills}
Staff : {display_money(staff_amount)}/{staff_bills}"""


def build_general_message(day: date, daily: dict[str, Any], menu: dict[str, int], removed: tuple[int, Decimal]) -> str:
    """Message for the General group; it deliberately contains no Ops-only lines."""
    removed_bills, removed_amount = removed
    return f"""Outlet - {BRAND_LABEL}
Date- {day.day}/{day.month}/{day.year}

Daily Report :-

SG:
Total bill - {daily['bills']}
APC - {display_money(daily['apc'])}
Cover - {daily['covers']}

Dessert sold - {menu['desserts']}
Beverages sold - {menu['beverages']}
Burrata sold - {menu['burrata']}

Sc Removal -
Total bills - {removed_bills}
Amount - {display_money(removed_amount)}

Review- google -
Thank you"""


def render(day: date, daily: dict[str, Any], menu: dict[str, int], removed: tuple[int, Decimal]) -> str:
    """Terminal view: two independently copyable messages, ready for two groups."""
    ops = build_ops_message(day, daily)
    general = build_general_message(day, daily, menu, removed)
    return f"""┌─[ THE SYSTEM : OPS STATUS ]──┐
│      SHADOW MONARCH          │
└──────────────────────────────┘
{ops}

────────────────────────────────

┌─[ THE SYSTEM : DAILY INTEL ]─┐
│      SHADOW MONARCH          │
└──────────────────────────────┘
{general}"""


def parse_day(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use YYYY-MM-DD, for example 2026-07-28.") from error


def main() -> None:
    parser = argparse.ArgumentParser(description="Smash Guys combined daily report")
    parser.add_argument("date", nargs="?", default=date.today(), type=parse_day)
    day = parser.parse_args().date
    try:
        session, token = login()
        daily = daily_metrics(fetch_daily(session, token, day))
        menu = menu_metrics(fetch_menu_mix(session, token, day))
        removed = removed_metrics(fetch_removed_charges(session, token, day))
    except (RuntimeError, requests.RequestException, ValueError, KeyError) as error:
        print(f"Report could not be generated: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(render(day, daily, menu, removed))


if __name__ == "__main__":
    main()
