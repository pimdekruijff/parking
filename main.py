import os
import secrets

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse

from parking import check_and_register

RUN_TOKEN = os.environ["RUN_TOKEN"]          # zelf verzinnen, zet 'm in Railway Variables
PLATE = os.environ.get("PLATE", "XX-123-X")  # je kenteken

app = FastAPI()


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/debug", response_class=PlainTextResponse)
def debug(x_token: str = Header(default="")):
    """Laat zien welke URL's de client opbouwt, om te zien of de patch werkt."""
    if not secrets.compare_digest(x_token, RUN_TOKEN):
        raise HTTPException(status_code=401, detail="nope")

    import dvsportal.dvsportal as dvs
    from yarl import URL

    import parking

    deployed = getattr(parking, "API_PATH", "ONTBREEKT — oude parking.py draait")

    base = URL.build(
        scheme="https",
        host=os.environ.get("DVS_HOST", "parkeerproducten.nijmegen.nl"),
        port=443,
        path=dvs.API_BASE_URI,
    )
    return "\n".join([
        f"parking.py   : {deployed}",
        f"API_BASE_URI : {dvs.API_BASE_URI}",
        f"login        : {base.join(URL('login'))}",
        f"getbase      : {base.join(URL('login/getbase'))}",
        f"create       : {base.join(URL('reservation/create'))}",
    ])


@app.post("/run", response_class=PlainTextResponse)
async def run(x_token: str = Header(default="")):
    if not secrets.compare_digest(x_token, RUN_TOKEN):
        raise HTTPException(status_code=401, detail="nope")

    # Fouten geven bewust een 200 terug met de fouttekst erin: dan toont het
    # kortcommando altijd een melding en denk je nooit ten onrechte dat het goed ging.
    try:
        return await check_and_register(PLATE)
    except Exception as exc:
        return f"⚠️ Aanmelden mislukt: {exc}"
