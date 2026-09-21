"""
DVSPortal-logica voor gemeente Nijmegen.

Bouwt op de dvsportal-client, met aanpassingen voor deze portaalversie:
- de API staat onder /DVSPortal/api/ in plaats van /DVSWebAPI/api/
- de login verwacht loginMethod als getal en een vaste permitMediaTypeID
- er komt geen token terug; de sessie loopt via een cookie, en het login-
  antwoord bevat de Permits al, dus login/getbase is niet nodig
- reservation/create verwacht LicensePlate als object, een permitMediaCode
  en datums met tijdzone-offset

Volgorde is bewust: eerst kijken of het kenteken al actief is, pas daarna
aanmelden. Daardoor is /run idempotent en kost een dubbele aanroep nooit saldo.
"""

import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

import dvsportal.dvsportal as _dvs
from dvsportal import DVSPortal
from dvsportal.exceptions import DVSPortalError

TZ = ZoneInfo("Europe/Amsterdam")

API_HOST = os.environ.get("DVS_HOST", "parkeerproducten.nijmegen.nl")

# Het basispad is niet instelbaar via de constructor, dus we overschrijven
# de module-constante die _request() gebruikt.
API_PATH = os.environ.get("DVS_API_PATH", "/DVSPortal/api/")
_dvs.API_BASE_URI = API_PATH if API_PATH.endswith("/") else API_PATH + "/"

IDENTIFIER = os.environ["DVS_IDENTIFIER"]
PASSWORD = os.environ["DVS_PASSWORD"]
LOGIN_METHOD = int(os.environ.get("DVS_LOGIN_METHOD", "2"))
MEDIA_TYPE_ID = int(os.environ.get("DVS_MEDIA_TYPE_ID", "7"))
MEDIA_CODE = os.environ.get("DVS_MEDIA_CODE")  # leeg = uit het login-antwoord halen
CAR_NAME = os.environ.get("CAR_NAME", "")
UNTIL_TIME = os.environ.get("UNTIL_TIME", "21:00")
DRY_RUN = os.environ.get("DRY_RUN", "1") == "1"


def _iso(dt: datetime) -> str:
    """2026-09-21T13:12:00.000+02:00 — zoals het portaal het zelf stuurt."""
    return dt.astimezone(TZ).isoformat(timespec="milliseconds")


class NijmegenPortal(DVSPortal):
    async def token(self):
        """Geen token: de aiohttp-sessie houdt het cookie vast."""
        if self._token is None:
            await self.update()
        return self._token

    async def authorization_header(self):
        await self.token()
        return {}

    async def update(self):
        """Logt in en leest saldo en reserveringen uit het login-antwoord."""
        response = await self._request(
            "login",
            json={
                "identifier": self._identifier,
                "loginMethod": LOGIN_METHOD,
                "password": self._password,
                "permitMediaTypeID": MEDIA_TYPE_ID,
                "asIdentifier": None,
                "otp": None,
                "resetCode": None,
                "zipCode": None,
            },
        )
        self._token = "cookie"

        permits = response.get("Permits") or []
        if not permits:
            raise DVSPortalError(f"Geen vergunning gevonden. Velden: {sorted(response)}")

        permit = permits[0]
        media = permit["PermitMedias"][0]

        self._default_type_id = media.get("TypeID", MEDIA_TYPE_ID)
        self._default_code = MEDIA_CODE or media.get("Code")
        self._balance = media.get("Balance")
        self._unit_price = permit.get("UnitPrice")

        self._active_reservations = {
            r["LicensePlate"]["Value"]: {
                "reservation_id": r.get("ReservationID"),
                "valid_from": r.get("ValidFrom"),
                "valid_until": r.get("ValidUntil"),
                "license_plate": r["LicensePlate"]["Value"],
                "units": r.get("Units"),
                "cost": None,
            }
            for r in media.get("ActiveReservations", [])
        }

    async def create_reservation(
        self, license_plate_value, date_from, date_until, license_plate_name=None
    ):
        """Zelfde payload als het portaal zelf stuurt."""
        await self.token()

        payload = {
            "LicensePlate": {
                "Value": license_plate_value,
                "Name": license_plate_name or CAR_NAME or license_plate_value,
            },
            "permitMediaTypeID": MEDIA_TYPE_ID,
            "permitMediaCode": self._default_code,
            "DateFrom": _iso(date_from),
        }
        if date_until is not None:
            payload["DateUntil"] = _iso(date_until)

        return await self._request("reservation/create", json=payload)


def _norm(plate: str) -> str:
    return plate.replace("-", "").replace(" ", "").upper()


def _fmt_balance(balance) -> str:
    """Saldo staat in units (minuten)."""
    if balance is None:
        return "onbekend"
    minutes = int(balance)
    return f"{minutes // 60} uur {minutes % 60} min"


def _hhmm(value) -> str:
    try:
        return datetime.fromisoformat(str(value)).strftime("%H:%M")
    except ValueError:
        return str(value)


async def check_and_register(plate: str) -> str:
    target = _norm(plate)

    async with NijmegenPortal(
        api_host=API_HOST, identifier=IDENTIFIER, password=PASSWORD
    ) as portal:
        await portal.update()

        existing = next(
            (r for p, r in portal.active_reservations.items() if _norm(p) == target),
            None,
        )
        balance = _fmt_balance(portal.balance)

        if existing:
            return (
                f"🅿️ {plate} staat al aangemeld tot {_hhmm(existing['valid_until'])}. "
                f"Saldo: {balance}."
            )

        now = datetime.now(TZ)
        until = None
        if UNTIL_TIME:
            until = datetime.combine(now.date(), time.fromisoformat(UNTIL_TIME), TZ)
            if until <= now:
                return (
                    f"🌙 {plate} is niet aangemeld, maar het venster tot {UNTIL_TIME} "
                    f"is al voorbij. Niets gedaan. Saldo: {balance}."
                )

        if DRY_RUN:
            return (
                f"🧪 [test] {plate} is niet aangemeld; zou nu aangemeld worden "
                f"tot {UNTIL_TIME or 'handmatig afmelden'}. Saldo: {balance}."
            )

        await portal.create_reservation(
            license_plate_value=target,
            date_from=now,
            date_until=until,
        )

        await portal.update()
        return (
            f"✅ {plate} aangemeld tot {UNTIL_TIME or 'handmatig afmelden'}. "
            f"Saldo nu: {_fmt_balance(portal.balance)}."
        )
