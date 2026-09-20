"""
DVSPortal-logica voor gemeente Nijmegen.

Gebruikt de dvsportal-client (https://github.com/ChessSpider/py-dvsportal),
dezelfde die onder de Home Assistant-integratie zit.

Volgorde is bewust: eerst kijken of het kenteken al actief is, pas daarna
aanmelden. Daardoor is /run idempotent en kost een dubbele aanroep nooit saldo.
"""

import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

import dvsportal.dvsportal as _dvs
from dvsportal import DVSPortal

TZ = ZoneInfo("Europe/Amsterdam")

API_HOST = os.environ.get("DVS_HOST", "parkeerproducten.nijmegen.nl")

# De library gaat uit van /api/ als basispad; Nijmegen hangt de API onder
# /DVSPortal/api/. Het pad is niet instelbaar via de constructor, dus we
# overschrijven de module-constante die _request() gebruikt.
API_PATH = os.environ.get("DVS_API_PATH", "/DVSPortal/api/")
_dvs.API_BASE_URI = API_PATH if API_PATH.endswith("/") else API_PATH + "/"
IDENTIFIER = os.environ["DVS_IDENTIFIER"]  # je pas-/kaartnummer waarmee je inlogt
PASSWORD = os.environ["DVS_PASSWORD"]
UNTIL_TIME = os.environ.get("UNTIL_TIME", "21:00")  # einde venster, zie README
DRY_RUN = os.environ.get("DRY_RUN", "1") == "1"


def _norm(plate: str) -> str:
    """Kentekens vergelijken zonder streepjes/spaties en hoofdletterongevoelig."""
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

    async with DVSPortal(
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

        now = datetime.now(TZ).replace(tzinfo=None)  # portaal verwacht lokale tijd
        until = None
        if UNTIL_TIME:
            until = datetime.combine(now.date(), time.fromisoformat(UNTIL_TIME))
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
