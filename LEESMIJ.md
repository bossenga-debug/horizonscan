# Horizonscan geneesmiddelen — alle domeinen in één overzicht

Statische HTML-pagina op basis van de CSV-export van de
[Horizonscan Geneesmiddelen](https://www.horizonscangeneesmiddelen.nl) van het
Zorginstituut. De site zelf laat je alleen per domein kijken; deze pagina zet de
acht domeinen naast elkaar in één doorzoekbare tabel, zet de verwachte
registraties op een tijdlijn, brengt de kosten van de sluismiddelen in beeld en
houdt bij wat er van maand tot maand verandert.

## Bestanden

| Bestand | Wat |
|---|---|
| `horizonscan.html` | de pagina — één bestand, geen internet nodig, dubbelklikken volstaat |
| `template.html` | opmaak, tabel- en grafiekcode; hier pas je de pagina aan |
| `ophalen.py` | haalt de CSV-exports, de detaillinks en de ATC-bronnen op naar `bron/` |
| `bouw_site.py` | bouwt `horizonscan.html` uit `bron/`, `historie/` en `template.html` |
| `atc.py` | koppelt werkzame stoffen aan een ATC-code |
| `mutaties.py` | vergelijkt met de vorige run en houdt het logboek bij |
| `bijwerken.py` | ophalen en bij wijziging herbouwen, in één opdracht |
| `deploy_ftp.py` | zet de pagina op medicatieadvies.nl/horizonscan |
| `htaccess` | cache- en compressie-instelling, wordt eenmalig als `.htaccess` geplaatst |
| `atc_correcties.json` | handmatige ATC-koppelingen (optioneel, zie hieronder) |
| `bron/` | opgehaalde brondata — **niet in de repo**, wordt elke run vers gehaald |
| `historie/` | momentopname en mutatielogboek — **wel in de repo**, zie hieronder |

## Bijwerken

```
python3 bijwerken.py            # ophalen en bij wijziging herbouwen
python3 bijwerken.py --altijd   # ook herbouwen als er niets veranderd is
python3 ophalen.py --check      # alleen kijken of er iets veranderd is
python3 bouw_site.py            # alleen opnieuw bouwen uit wat er al staat
```

Automatisch draait het maandelijks op de 5e via
`.github/workflows/horizonscan.yml`, met `--ci`: dan stopt het bij de kleinste
twijfel (een bron die van indeling verandert, een pagina die te klein uitvalt)
in plaats van een halve pagina te publiceren. De 8e is bewust vermeden, want dan
draait het add-on dashboard.

Vervangen bronbestanden krijgen de extensie `.vorige` en blijven staan, zodat je
kunt zien wat er veranderd is.

## Hoe de data binnenkomt

Per domein worden twee dingen opgehaald:

1. **De CSV-export**, via `/geneesmiddelen/export?publicatiedatum=&domein=<slug>`.
   Die URL zit achter een sessiecookie. Zonder cookie antwoordt de server met
   HTTP 200 en een leeg bestand — geen foutmelding, gewoon nul bytes. Daarom
   haalt `ophalen.py` eerst de domeinpagina op (die zet het cookie) en stuurt die
   pagina daarna als referer mee.

2. **De overzichtspagina zelf**, voor de links naar de detailpagina's. De export
   bevat wel een `id` per middel, maar dat id werkt niet als URL: het redirect
   naar `/pagenotfound`. De bruikbare slugs staan alleen in de HTML.

De acht domeinslugs staan in `DOMEINEN` in `ophalen.py`.

## De koppeling met de detailpagina's

Een middel met vijf indicaties heeft vijf detailpagina's: `pembrolizumab-4`,
`pembrolizumab-10`, enzovoort. Welke pagina bij welke CSV-regel hoort, is
nergens expliciet vastgelegd. `koppel_slugs()` leidt het af uit de linktekst op
de overzichtspagina — die is per pagina óf de stofnaam óf de indicatietekst —
en wijst elke slug maar één keer toe, hoogste gelijkenis eerst.

Dat lukt voor **1.899 van de 1.924 middelen (99%)**. De overige 25 krijgen geen
link; in het detailpaneel staat dan "geen directe link gevonden". Steekproef op
`pembrolizumab-10/-12/-28` bevestigde dat de toegewezen pagina's inhoudelijk
kloppen.

## Kolomvolgorde

De export heeft drie kolommen die `Additional remarks` heten en vier die
`References` heten. Op naam lezen levert dan de verkeerde kolom op, dus
`bouw_site.py` werkt op kolomnummer. `controleer_koppen()` stopt met een
duidelijke melding zodra de site die volgorde wijzigt — dan moeten `KOLOM` en
`VERWACHTE_KOPPEN` mee.

## Vertaling

De export is Engelstalig. Alleen velden met een vaste, gesloten woordenlijst
worden vertaald: domein, registratiefase, sluisstatus, vergoeding, kader, reden
van opname, therapeutische waarde, bijzonderheid, registratieroute, traject,
toedieningsweg en de 85 hoofdindicaties. Vrije tekst — de volledige indicatie,
de onderbouwing, het werkingsmechanisme — blijft staan zoals de bron het
schrijft; daar zou vertalen betekenis kunnen verschuiven.

Komt er een nieuwe keuzemogelijkheid bij, dan valt die onvertaald door en meldt
`bouw_site.py` dat aan het eind, met veld en waarde, zodat `VERTAAL` bijgewerkt
kan worden.

Eén bekende bronfout: de toedieningsweg `Intrader meal` is een verschrijving van
`Intradermal` en wordt als *Intradermaal* getoond.

## Wat de kostenbedragen wél en niet zijn

Van de 1.924 middelen hebben er 981 een ingevulde totale kostenraming, samen
ongeveer **€ 54 miljard**. Dat zijn de voorlopige rekenwaarden van de
Horizonscan zelf: kosten per patiënt maal een geschat *maximaal* patiëntaantal,
dat in de bron vaak als bandbreedte staat (`< 550`, `600 - 900`). De export
zegt er zelf bij dat het voorlopige berekeningen zijn.

Lees ze dus als **bovengrens en signaal**, niet als begroting. De pagina zegt
dat er op twee plekken bij: onder de kerncijfertegel en in het detailpaneel.

Voor sorteren wordt de hoogste waarde uit een bandbreedte gebruikt
(`volume_bovengrens()`); bedragen staan in de bron in Engelse notatie
(`€ 53,612,300.00`) en worden zo gelezen.

## De tijdlijn

De verwachte registratie staat in de bron als `10-2027`, als kaal jaartal
(`2027`), of helemaal niet. Alleen de eerste vorm past in een kwartaal; de
pagina meldt onder de grafiek hoeveel middelen daarom buiten beeld blijven en
hoeveel er een al verstreken datum hebben. Met de knop **Per kwartaal** uit
wordt op jaar gegroepeerd, en dan tellen de kale jaartallen wel mee.

De acht domeinen hebben een vaste kleurplek, niet één die met de sortering
meebeweegt: filter je domeinen weg, dan houden de overblijvers hun kleur. Het
kleurenpalet is gecontroleerd op onderscheidbaarheid bij kleurenblindheid, in
lichte en donkere modus.

## Publiceren

`deploy_ftp.py` zet `horizonscan.html` als `index.html` op de server. Het is
overgenomen uit de preferentiebeleid-repo — daar zit de kennis over deze hosting
in (TLS-sessie hergebruiken op het datakanaal, een certificaat op een andere
naam) — met één toevoeging: `controleer_doelmap()` stopt als het FTP-account
niet in de bedoelde map uitkomt. Zonder die controle zou `index.html` in de map
van een andere pagina belanden en die overschrijven.

### Waarom de pagina in een submap staat

Het FTP-account is bij Cloud86 vastgezet op de map `preferentiebeleid`. Voor die
verbinding *is* dat de hoofdmap; een map ernaast bestaat simpelweg niet. Daarom
komt de pagina op:

<https://medicatieadvies.nl/preferentiebeleid/horizonscan/>

Dezelfde beperking geldt voor het add-on dashboard, dat om die reden op
`/preferentiebeleid/addon/` staat en niet op `/addon/`. De ATC-links in het
detailpaneel wijzen daarheen; `/addon/` geeft een 404.

Wil je hem later op `/horizonscan/` hebben, dan is een FTP-account nodig dat
hoger begint — met `public_html/horizonscan` als hoofdmap. Zet dan `FTP_DIR` op
`/` en gebruik `FTP_USER_HORIZONSCAN` en `FTP_PASS_HORIZONSCAN`, die in de
workflow van de gedeelde secrets winnen. Vergeet dan niet `ADDON_DASHBOARD` in
`bouw_site.py` mee te verhuizen als ook het add-on dashboard opschuift.

### Eenmalig instellen

1. Maak in het bestandsbeheer van de hoster de map
   `public_html/preferentiebeleid/horizonscan` aan. Het deployscript maakt die
   niet zelf — met opzet, want dan zou een typefout een nieuwe map opleveren in
   plaats van een foutmelding.
2. Zet één secret klaar (Settings → Secrets and variables → Actions):

   | Secret | Waarde |
   |---|---|
   | `FTP_DIR_HORIZONSCAN` | `horizonscan` |

`FTP_HOST`, `FTP_USER`, `FTP_PASS` en `FTP_CERT_HOST` worden hergebruikt uit de
bestaande secrets; er zijn geen nieuwe inloggegevens nodig. Staat er wel een
`*_HORIZONSCAN`-variant, dan wint die.

Instellingen komen uit omgevingsvariabelen of uit een `.env` naast het script
(die staat in `.gitignore`). Uitproberen zonder iets te versturen:

```
python3 deploy_ftp.py --dry-run
```

## Grafieken en schermbreedte

Alle grafieken worden getekend op de **gemeten** breedte van de plek waar ze
komen, niet op een vaste maat. Dat is geen detail: een SVG met een vaste viewBox
wordt door de browser passend geschaald en de tekst schaalt mee. Met een vaste
breedte liepen de labels terug tot 6,5px in de halve kolommen en 4px op een
telefoon. Nu blijft alles tussen 12 en 14px.

De tijdlijn houdt daarnaast een ondergrens per periode aan en schuift
horizontaal in zijn eigen vak zodra er meer kwartalen zijn dan er passen — de
pagina zelf scrollt nooit horizontaal. Bij het verslepen van het venster worden
de grafieken opnieuw getekend, met vertraging zodat dat niet bij elke pixel
gebeurt.

## Controle bij het bouwen

`bouw_site.py` weigert te schrijven als het paginascript een syntaxfout bevat
(`node --check`). Dat is niet theoretisch: bij het bouwen van het mutatietabblad
belandde een blok CSS in het scriptdeel, waardoor de pagina wel opende maar leeg
bleef. Zonder node wordt de controle overgeslagen, met een melding.
