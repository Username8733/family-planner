# Kör familjekalendern i Home Assistant

Detta är förberett lokalt. Inget har installerats eller ändrats i HA.

## Enkel inbäddning utan HA-givare: webbsidesdashboard

1. Exportera din nuvarande kalender under Inställningar → Exportera JSON.
2. Kopiera innehållet i projektets dist/ till /config/www/familjekalender/ på HA-servern. Starta om HA om www skapades för första gången.
3. Öppna /local/familjekalender/index.html under din vanliga HA-adress och kontrollera sidan.
4. I HA: Inställningar → Dashboards → Lägg till dashboard → Webbsida. Namn: Familjekalender. Ikon: mdi:calendar-month. URL: /local/familjekalender/index.html.
5. Öppna kalenderns Inställningar i den nya adressen och importera JSON-filen. Import ersätter kalendern i denna webbläsare efter bekräftelse.
6. Använd samma URL vid framtida uppdateringar så att lokal lagring följer med.

Samma dist/index.html används fristående. Det behövs ingen HA-token, HACS eller extern JavaScript-resurs. Appen anpassar sig efter ramens tillgängliga höjd och använder HA:s vanliga inbäddning.

## Data och nästa integrationssteg

I lokalt läge sparas aktiviteter, kolumner, tema och inställningar i webbläsarens localStorage. Onlinehändelser läses från respektive ansluten källa, inklusive HA:s kalenderentiteter. Onlinefunktionen kräver den körande Python-servern enligt ../ONLINE-CALENDAR.md. Lokala aktiviteter och inställningar synkroniseras inte mellan enheter. Export/import flyttar en lokal kopia. Ny adress/protokoll/port ger separat lagring. Använd export före flytt eller rensning av webbdata.

Väder hämtas direkt från Open-Meteo, även när appen visas i HA. Vald stad och dess koordinater skickas till vädertjänsten. Inga aktivitetsuppgifter skickas dit. Prognosen gäller dagens datum i väderstadens tidszon, oberoende av vilken månad kalendern visar.

HA:s /local/ är statiska filer utan separat autentisering. Lägg inga säkerhetskopior, aktiviteter eller kontouppgifter i www; endast appens generiska dist-filer. Kalenderdata ligger i webbläsaren och exporterade JSON-filer förvaras privat.

Dokumentation:
- https://www.home-assistant.io/dashboards/dashboards/#webpage-dashboard
- https://www.home-assistant.io/dashboards/iframe/
- https://www.home-assistant.io/integrations/http/#hosting-files

## HA-givare: använd det medföljande kortet

En vanlig webbsidesdashboard visar appen men skickar inte HA:s givarvärden. För att kunna välja en utomhusgivare används därför projektets egna, lilla HA-kort:

1. Kopiera hela dist/ till /config/www/familjekalender/, inklusive hemma-calendar-card.js.
2. Under Inställningar → Dashboards → Resurser lägger du till /local/familjekalender/hemma-calendar-card.js som JavaScript-modul. Avancerat läge kan behöva aktiveras i profilen för att visa resurser.
3. Skapa en separat dashboard och använd konfigurationen i dashboard.yaml i dess råkonfigurationsredigerare.
4. Öppna familjekalenderns Inställningar → Källa för aktuell utetemperatur → Temperaturgivare i Home Assistant.
5. Välj den givare som faktiskt sitter utomhus och spara. Listan visar temperaturgivare med enheten °C eller °F; inga givare gissas automatiskt.
6. Begränsa vid behov listan med temperature_entities i kortkonfigurationen. Det är ett visningsfilter, inte en behörighetsgräns för HA-användaren.

Kortet får det inloggade HA-gränssnittets hass-objekt och skickar enbart temperaturgivarnas ID, namn, värde, enhet och uppdateringstid till kalendern. Inga tokens, lösenord eller andra entiteter skickas eller sparas. Adapter och app måste ligga på samma origin som HA. Appen kontrollerar både avsändarfönster och origin. Anslutningen får en heartbeat var 30:e sekund; om den upphör visas ingen anslutning efter 90 sekunder.

Värdet omvandlas till vald temperaturenhet. Unknown/unavailable, borttagen givare och bruten anslutning visas tydligt i kortet; de ersätts inte tyst med vädertjänstens temperatur. En givare kan uppdateras sällan utan att vara trasig: uppdateringstiden visas, och någon godtycklig åldersgräns för själva mätvärdet används inte.

Lokalt kan man fortfarande välja vädertjänsten, vars aktuella temperatur markeras som modellvärde. Att välja HA som källa fristående utan adapter visar ingen anslutning.

Bygger på HA:s kort-API: https://contributors.home-assistant.io/frontend/custom-ui/card/
Panelvy: https://www.home-assistant.io/dashboards/panel/


## Onlinekalendrar: iCloud, Google, HA, CalDAV och ICS
Onlinekalendern behöver serverdelen i serve.py och kan inte köras enbart som en statisk fil under /local/. Se ../ONLINE-CALENDAR.md för körning, autentisering och HA-inbäddning via tjänstens HTTPS-adress. Ingen automatisk HA-installation har gjorts.
