# Bezoekersvergunning automatisch aanmelden (Nijmegen / DVSPortal)

Kortcommando op je iPhone checkt om 11:00 of je thuis bent en roept dan deze
service aan. De service meldt je kenteken aan als dat nog niet actief is en
stuurt een regel tekst terug die het kortcommando als melding toont.

## Railway Variables

| Variabele | Waarde |
| --- | --- |
| `RUN_TOKEN` | zelf verzinnen, lang en willekeurig |
| `PLATE` | je kenteken, bv. `12-ABC-3` |
| `DVS_IDENTIFIER` | het pas-/kaartnummer waarmee je inlogt op het portaal |
| `DVS_PASSWORD` | je wachtwoord |
| `UNTIL_TIME` | eindtijd reservering, bv. `21:00` (leeg = open tot je afmeldt) |
| `DRY_RUN` | `1` om te testen, `0` om echt aan te melden |
| `TZ` | `Europe/Amsterdam` |

`DVS_HOST` staat standaard op `parkeerproducten.nijmegen.nl`.

## Testen

1. Deploy met `DRY_RUN=1`.
2. `curl -X POST -H "X-Token: <token>" https://<app>.up.railway.app/run`
   Je krijgt het echte saldo terug, maar er wordt niets aangemeld.
3. Klopt het? Zet `DRY_RUN=0`.

## Kortcommando

Kortcommando's > Automatisering > Tijdstip 11:00, "Direct uitvoeren" aan:

1. Huidige locatie ophalen
2. Afstand ophalen tot je thuisadres
3. Als afstand < 0,15 km
4. Inhoud van URL ophalen: POST naar `/run` met header `X-Token`
5. Toon melding met het resultaat

## Let op

- **`UNTIL_TIME`**: check de venstertijden van betaald parkeren in jouw straat.
  Zet je dit leeg, dan loopt de reservering door tot je handmatig afmeldt en
  kan dat flink saldo kosten.
- **Saldo** komt uit het portaal in units (minuten). Ziet het getal er raar uit,
  pas dan `_fmt_balance()` in `parking.py` aan.
- **Afmelden** kan met `portal.end_reservation(reservation_id=...)`. Handig als
  tweede kortcommando dat afgaat zodra je het thuisgebied verlaat.
