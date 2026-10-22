# Onlinekalendrar

Kör den lokala kalendern med projektets virtuella Python-miljö:

    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python serve.py --port 8086

Öppna http://127.0.0.1:8086/. Lokala aktiviteter fungerar även direkt från dist/index.html.
Onlineanslutningar kräver servern. Inget installeras i HA automatiskt.

## Leverantörer

| Källa | Visa | Skapa | Ändra / ta bort |
| --- | --- | --- | --- |
| iCloud | Ja | Ja | Ja, ett valt tillfälle i återkommande serier |
| Google Calendar | Ja | Med skrivbehörighet | Med skrivbehörighet, ett tillfälle |
| CalDAV, exempelvis Nextcloud och Fastmail | Ja | Om servern tillåter | Om servern tillåter, ett tillfälle |
| Home Assistant | Ja | Om entiteten stöder det | Om entiteten stöder det och rapporterar händelsens UID |
| ICS / iCalendar-prenumeration | Ja | Nej | Nej |

Flera källor och kalendrar kan vara valda samtidigt. Varje aktivitet har en bestämd källa.
Att välja en annan kalender flyttar inte gamla aktiviteter. Välj målkalender under **Spara i** när en ny aktivitet skapas.
En ny onlineaktivitet som skapas i den lokala vyn växlar visningen till blandat läge så att den syns.

Under **Inställningar → Visa kalender** väljs lokalt, online eller båda.
Kryssa för önskade kalendrar under **Onlinekalendrar** och spara inställningarna.
Anslutning/bortkoppling gäller direkt för servern; kalenderurval sparas med inställningarna.
Det befintliga iCloud-kontot och dess valda kalender behålls. Apple-ID visas för anslutningen.
iCloud-panelen väljer en kalender per anslutet Apple-konto. Ytterligare CalDAV-källor kan läggas till separat.

## iCloud

Anslut med Apple-ID och ett appspecifikt Apple-lösenord. Det vanliga kontolösenordet används inte.
Välj iCloud-kalender i anslutningspanelen och spara inställningarna.
Hämtning använder kalenderns upptäckta iCloud-server, som kan ha en annan adress än inloggningsservern.

## Google

1. Aktivera **Google Calendar API** i ett Google Cloud-projekt.
2. Konfigurera OAuth consent screen och lägg till ditt Google-konto som testanvändare om appen är i testläge.
3. Skapa en OAuth-klient av typen **Desktop app** för lokal användning på samma dator.
4. I kalendern: **Inställningar → Onlinekalendrar → Lägg till kalenderkälla → Google Kalender**.
5. Ange Client ID och Client secret och välj **Anslut kalenderkälla**.
6. Klicka **Fortsätt till Google**, godkänn åtkomsten och återvänd till kalendern.
7. Välj kalendrar och spara inställningarna.

Google-inloggningen använder state, PKCE och en returadress till kalenderns egen server.
Den lokala returadressen visas i inställningarna. För inbäddning/åtkomst från en annan dator eller en publicerad HTTPS-tjänst används en **Web application**-klient med exakt registrerad returadress.
Ett generiskt Google-klient-ID levereras inte med projektet; användaren behöver skapa sitt eget.
Begärda behörigheter är calendar.calendarlist.readonly och calendar.events.
Refresh-token lagras på servern och förnyar åtkomsten. Avbrutet/flöde som gått ut kan startas om.
Bortkoppling tar bort den lokala anslutningen; återkalla vid behov även appens åtkomst i Google-kontot.

## Home Assistant

Ange HA:s basadress och en långlivad åtkomsttoken från din HA-profil.
Token används enbart av Python-servern. Ingen token skickas tillbaka till webbläsaren.
Välj kalenderentiteterna som ska visas. Kalenderns supported_features avgör tillgängliga åtgärder.

Läsning och skapande använder REST; ändring och borttagning använder calendar/event/update respektive calendar/event/delete över HA:s WebSocket-API.
Befintliga händelser behöver en UID. Utan UID visas de skrivskyddade.
Återkommande händelsers recurrence_id skickas vidare för att ändra endast det valda tillfället.
Beskrivning och plats bevaras vid ändring.
Händelsen hämtas på nytt och jämförs före ändring. HA saknar ett atomiskt If-Match-villkor för dessa kommandon, så en samtidig ändring precis efter kontrollen kan inte uteslutas.
Skapande i HA saknar serverstödd idempotens; bekräftade upprepningar skyddas under serverprocessens livstid.
Om en skapandebegäran avbryts eller får timeout: uppdatera kalendern innan du försöker igen.

Detta fungerar även fristående från HA. En ren kopia under HA:s /local/ är statisk och har inget Python-API.
För onlinefunktionerna används den körande tjänstens HTTPS-adress i en webbsidesdashboard, med samma-origin-proxy om även det medföljande temperaturkortet används.

## Andra tjänster

**CalDAV:** ange leverantörens CalDAV-basadress, användarnamn och lösenord/applösenord. Kalendrar upptäcks automatiskt.
**ICS:** ange en direkt http/https- eller webcal-länk till ett iCalendar-flöde. Privata ICS-länkar behandlas som inloggningsuppgifter.
ICS är en prenumeration med enbart läsning, exempelvis för en publicerad Outlook-kalender.
Native Microsoft Graph/Exchange OAuth ingår inte; använd en ICS-prenumeration eller en befintlig HA-integration.
HTTP-omdirigeringar för tokenbaserade API:er och ICS följs inte; använd slutadressen så att hemligheter inte skickas vidare till en annan värd.

## Namn, datum och uppdatering

- Person 1 - Dans hamnar hos Person 1.
- Person 1, Person 2 - Bio är en aktivitet som visas i båda personkolumnerna.
- Kolumnnamn matchas utan hänsyn till stora/små bokstäver. Tidigare namn bevaras som alias vid namnbyte.
- Om alla angivna namn inte kan matchas används vald reservkolumn och hela originaltiteln behålls.
- Heldagarsaktiviteters slutdatum är inkluderande i gränssnittet och exklusivt i leverantörernas API:er.
- Tider hanteras i källans tidszon. Sommartidsbyten kontrolleras.
- Onlinehändelser hämtas var tredje minut, vid månadsbyte, när fliken åter blir aktiv och efter ändring.
- Vid fel i en källa behålls dess tidigare händelser för samma månad, skrivskyddade och markerade med synkfel. Andra källor fortsätter fungera.
- Om samma underliggande kalender ansluts både direkt och via HA kan samma händelser visas två gånger. Välj en av anslutningarna.

## Språk

Välj **Inställningar → Språk / Language → Svenska / English** och spara.
Valet gäller den aktuella webbläsaren och följer med i JSON-exporten.
Gränssnitt, månad, veckodagar, vädertexter och svenska helgdagsnamn översätts.
Personnamn, kalendernamn och aktivitetstitlar översätts inte.
Datum förblir YYYY-MM-DD; tidsformat och temperaturenhet väljs separat.
Helgdagarna förblir svenska även när gränssnittet är engelskt.

## Privata uppgifter och nätverksdrift

Privata filer ligger som standard i ~/.local/share/hemma-calendar/:
- icloud.json: Apple-anslutningen.
- sources.json: övriga anslutningar, valda kalendrar, Google OAuth-token och signeringsnyckel.

Filer skrivs med behörighet 0600 och ligger utanför dist/. Inga lösenord, åtkomsttoken, privata kalenderlänkar eller hämtade onlineaktiviteter ingår i localStorage eller JSON-exporten.
Apple-ID exponeras avsiktligt för den inloggade/localhost-anslutna kalendern för att visa vilket konto som är anslutet.
Lägg inte privata konfigurationsfiler i HA:s www, i dist eller i Git.

Standardservern lyssnar endast på localhost. Nätverksåtkomst kräver HEMMA_HTTP_USERNAME och HEMMA_HTTP_PASSWORD samt TLS eller --behind-https-proxy och --public-host. Origin/Host och CSRF kontrolleras. Google OAuth-returkoder loggas inte.
Kalenderns inloggning ger åtkomst till de anslutna källornas rättigheter.

## Kontroller

- test_online_backend.py: verklig lokal CalDAV-server, CRUD, återkommande aktiviteter, konflikter och tidszoner.
- test_calendar_sources.py: isolerade Google/HA/ICS-protokoll, OAuth/PKCE, tokenförnyelse, paginering, CRUD, sekretess och fel.
- test_ha_websocket.py: verklig lokal HTTP/WebSocket-server med HA-protokoll.
- qa-multiple-calendars.py: verklig webbläsare och CalDAV-server, källor, delade aktiviteter, språk och skrivskydd vid fel.
- qa-settings-layout.py: scrollning, hörn, knapprad och ortsval på dator/iPad.

Google har testats med isolerade API-svar; ett riktigt Google-konto behöver anslutas för att verifiera OAuth-konfigurationen hos Google.

Källor: https://developers.google.com/identity/protocols/oauth2/native-app
https://developers.google.com/workspace/calendar/api/v3/reference/events/list
https://developers.google.com/workspace/calendar/api/v3/reference/events/patch
https://developers.home-assistant.io/docs/api/rest/
https://github.com/home-assistant/core/blob/dev/homeassistant/components/calendar/__init__.py
