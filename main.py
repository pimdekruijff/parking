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
