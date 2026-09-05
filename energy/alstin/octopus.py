"""Octopus Energy REST client.

Public price endpoints need no auth; account/consumption endpoints use HTTP Basic
with the API key as the username and a blank password. Never hardcode the key.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable, Optional

import requests

BASE_URL = "https://api.octopus.energy/v1"
UTC = dt.timezone.utc


def _parse_iso(s: str) -> dt.datetime:
    """Parse an Octopus ISO timestamp into an aware UTC datetime.

    Python 3.9's fromisoformat does not accept a trailing 'Z', so normalise it.
    """
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return d.astimezone(UTC)


@dataclass(frozen=True)
class Rate:
    """A single half-hourly (or longer) unit rate, price in p/kWh inc VAT."""

    value_inc_vat: float
    valid_from: dt.datetime
    valid_to: Optional[dt.datetime]  # None means open-ended (flat/ongoing rate)

    def covers(self, when: dt.datetime) -> bool:
        """True if `when` falls within [valid_from, valid_to)."""
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        when = when.astimezone(UTC)
        if when < self.valid_from:
            return False
        if self.valid_to is None:
            return True
        return when < self.valid_to

    def duration_hours(self) -> float:
        if self.valid_to is None:
            return float("inf")
        return (self.valid_to - self.valid_from).total_seconds() / 3600.0


def parse_tariff_code(tariff_code: str) -> tuple[str, str]:
    """Split a tariff code into (product_code, region).

    e.g. 'E-1R-GO-VAR-22-10-14-H' -> ('GO-VAR-22-10-14', 'H').
    Format is <E|G>-<NR>-<PRODUCT>-<REGION>; region is the final single-letter part.
    """
    parts = tariff_code.split("-")
    if len(parts) < 4:
        raise ValueError(f"Unrecognised tariff code: {tariff_code!r}")
    region = parts[-1]
    product = "-".join(parts[2:-1])
    return product, region


@dataclass
class MeterPoint:
    mpan: str
    serial: str
    tariff_code: Optional[str]
    is_export: bool


class OctopusClient:
    def __init__(self, api_key: str, base_url: str = BASE_URL, timeout: int = 30):
        if not api_key:
            raise ValueError("Octopus API key is empty (set OCTOPUS_API_KEY)")
        self._session = requests.Session()
        self._session.auth = (api_key, "")  # key as username, blank password
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ---- low level -------------------------------------------------------
    def _get(self, path: str, params: Optional[dict] = None, auth: bool = True) -> dict:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        # Public endpoints work without auth; sending it anyway is harmless.
        resp = self._session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _paginate(self, path: str, params: Optional[dict] = None) -> Iterable[dict]:
        next_url: Optional[str] = None
        first = True
        while first or next_url:
            data = self._get(next_url or path, params=params if first else None)
            for row in data.get("results", []):
                yield row
            next_url = data.get("next")
            first = False

    # ---- account --------------------------------------------------------
    def get_account(self, account_number: str) -> dict:
        return self._get(f"/accounts/{account_number}/")

    def account_meter_points(self, account_number: str) -> list[MeterPoint]:
        """Return electricity meter points with current tariff codes.

        Import vs export is inferred from is_export on the meter point.
        """
        account = self.get_account(account_number)
        out: list[MeterPoint] = []
        for prop in account.get("properties", []):
            for emp in prop.get("electricity_meter_points", []):
                mpan = emp.get("mpan", "")
                is_export = bool(emp.get("is_export", False))
                tariff_code = self._current_tariff_code(emp)
                serials = [m.get("serial_number", "") for m in emp.get("meters", [])]
                serial = serials[0] if serials else ""
                out.append(MeterPoint(mpan, serial, tariff_code, is_export))
        return out

    @staticmethod
    def _current_tariff_code(emp: dict) -> Optional[str]:
        """Pick the agreement whose window contains now (or the latest one)."""
        now = dt.datetime.now(UTC)
        agreements = emp.get("agreements", [])
        best: Optional[str] = None
        best_from: Optional[dt.datetime] = None
        for ag in agreements:
            code = ag.get("tariff_code")
            if not code:
                continue
            vf = _parse_iso(ag["valid_from"]) if ag.get("valid_from") else None
            vt = _parse_iso(ag["valid_to"]) if ag.get("valid_to") else None
            active = (vf is None or vf <= now) and (vt is None or now < vt)
            if active:
                return code
            # fall back to the most recent agreement we have seen
            if best_from is None or (vf is not None and vf > best_from):
                best, best_from = code, vf
        return best

    def account_gas_meter_points(self, account_number: str) -> list[MeterPoint]:
        """Return gas meter points (MPRN + serial + current tariff) on the account.

        MeterPoint.mpan holds the MPRN here; is_export is always False for gas.
        """
        account = self.get_account(account_number)
        out: list[MeterPoint] = []
        for prop in account.get("properties", []):
            for gmp in prop.get("gas_meter_points", []):
                mprn = gmp.get("mprn", "")
                tariff_code = self._current_tariff_code(gmp)
                serials = [m.get("serial_number", "") for m in gmp.get("meters", [])]
                serial = serials[0] if serials else ""
                out.append(MeterPoint(mprn, serial, tariff_code, False))
        return out

    # ---- rates ----------------------------------------------------------
    def standard_unit_rates(
        self,
        product_code: str,
        tariff_code: str,
        period_from: dt.datetime,
        period_to: dt.datetime,
    ) -> list[Rate]:
        path = (
            f"/products/{product_code}/electricity-tariffs/"
            f"{tariff_code}/standard-unit-rates/"
        )
        params = {
            "period_from": period_from.astimezone(UTC).isoformat(),
            "period_to": period_to.astimezone(UTC).isoformat(),
        }
        rates: list[Rate] = []
        for row in self._paginate(path, params):
            rates.append(
                Rate(
                    value_inc_vat=float(row["value_inc_vat"]),
                    valid_from=_parse_iso(row["valid_from"]),
                    valid_to=_parse_iso(row["valid_to"]) if row.get("valid_to") else None,
                )
            )
        rates.sort(key=lambda r: r.valid_from)
        return rates

    def rates_for_tariff(
        self, tariff_code: str, period_from: dt.datetime, period_to: dt.datetime
    ) -> list[Rate]:
        product, _region = parse_tariff_code(tariff_code)
        return self.standard_unit_rates(product, tariff_code, period_from, period_to)

    # ---- consumption ----------------------------------------------------
    def consumption(
        self,
        mpan: str,
        serial: str,
        period_from: dt.datetime,
        period_to: dt.datetime,
        group_by: Optional[str] = None,
    ) -> list[dict]:
        path = f"/electricity-meter-points/{mpan}/meters/{serial}/consumption/"
        params = {
            "period_from": period_from.astimezone(UTC).isoformat(),
            "period_to": period_to.astimezone(UTC).isoformat(),
        }
        if group_by:
            params["group_by"] = group_by
        return list(self._paginate(path, params))

    def gas_consumption(
        self,
        mprn: str,
        serial: str,
        period_from: dt.datetime,
        period_to: dt.datetime,
        group_by: Optional[str] = None,
    ) -> list[dict]:
        """Raw gas consumption intervals.

        Octopus returns `consumption` in the meter's native unit: kWh for many
        SMETS2 gas meters, m^3 for SMETS1/older. The caller converts using the
        configured unit (see gas.py).
        """
        path = f"/gas-meter-points/{mprn}/meters/{serial}/consumption/"
        params = {
            "period_from": period_from.astimezone(UTC).isoformat(),
            "period_to": period_to.astimezone(UTC).isoformat(),
        }
        if group_by:
            params["group_by"] = group_by
        return list(self._paginate(path, params))
