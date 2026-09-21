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

## Uitleg voor bezoekers

De knop **Uitleg** rechtsboven opent een toelichting in hetzelfde zijpaneel als
het detailpaneel: wat de pagina is, wat elk tabblad doet, hoe filteren en delen
werkt, de koppeling met het add-on dashboard, en hoe je de cijfers leest — met
name dat kosten een bovengrens zijn en dat een stof per indicatie apart staat.

De aantallen in die tekst (regels, stoffen, middelen met ATC of met raming) en
de datums komen uit de data zelf, zodat de uitleg na elke update blijft kloppen.
De tekst staat in `toonUitleg()` in `template.html`.

## Het indicatiefilter

De 85 hoofdindicaties zitten niet in een gewone keuzelijst maar in een eigen
paneel met vinkjes, want je wilt er meer dan één tegelijk kunnen kiezen — en
85 regels in een `<select>` is onwerkbaar.

Drie keuzes daarin:

- **Geen groepering per domein.** Voor de hand liggend, maar vijf indicaties
  komen in meer dan één domein voor (waaronder "Onbekend" en de lege), en dan is
  elke indeling deels willekeurig. Eén alfabetische lijst met een zoekveld is
  eerlijker.
- **De aantallen tellen mét de andere filters maar zónder de indicatiekeuze
  zelf.** Zo gedragen facetten zich: je wilt zien wat een extra vinkje oplevert,
  niet wat er van je huidige keuze overblijft. Zet je een fase aan, dan zakt
  "Longkanker" van 106 naar 10.
- **Indicaties zonder treffers verdwijnen uit de lijst, behalve wat al
  aangevinkt staat.** Anders verdwijnt je eigen keuze uit beeld zodra je een
  ander filter aanzet.

Gekozen indicaties staan bovenaan onder een kopje, zodat je ze bij 84 regels
niet kwijtraakt. In de deelbare link staan ze als `indicaties=Longkanker|Dementie`.

## Deelbare links

De filterstatus staat in de hash van de URL, dus elke weergave is te delen:

```
.../horizonscan/#tab=sluis&domein=Oncologie&sluis=In%20de%20sluis&wees=1
```

De adresbalk loopt mee met wat je instelt, en de knop **Kopieer link** in de
filterbalk zet hem op het klembord. Bewust de hash en geen zoekparameters: dit
is een statische pagina op gewone webhosting, en de hash bereikt de server niet.
Het schrijven gaat via `history.replaceState`, zodat de geschiedenis niet
volloopt bij elke toetsaanslag en het terugschrijven geen `hashchange` uitlokt.

Wat erin kan: `tab` (tabel, tijdlijn, sluis, mutaties), `zoek`, `domein`,
`fase`, `sluis`, `vergoeding`, `kader`, `waarde`, de vinkjes `wees`, `atmp`,
`prime` en `addon`, de sortering (`sorteer` en `richting`), en voor de
afzonderlijke tabbladen `periode`, `kwartaal`, `verstreken` en `sluisstatus`
(meerdere gescheiden door een `|`). Alleen wat van de standaard afwijkt komt in
de link, zodat hij kort blijft.

Twee dingen die in het ontwerp zitten omdat ze anders misgaan:

- **Lezen begint bij de standaard.** Wat niet in de link staat, wordt actief
  uitgezet. Zonder dat bleven bij het plakken van een tweede link de filters van
  de eerste hangen, en zag je een combinatie die in geen van beide links stond.
- **Onbekende waarden worden genegeerd.** `#domein=Onkologie` levert de
  volledige lijst op, niet nul resultaten. Een typefout in een gedeelde link
  laat de pagina anders kapot lijken.

De kopieerknop probeert eerst de klembord-API, dan `execCommand`, en laat als
laatste redmiddel de link geselecteerd in beeld staan. Die terugval is niet
theoretisch: lokaal via `file://` geopend weigert de klembord-API dienst.

## Het sluis-tabblad

Beantwoordt drie vragen tegelijk: welke sluismiddelen kosten het meest, in welke
domeinen zitten die, en om welke indicaties gaat het.

De statussen zijn los aan te vinken en staan in de volgorde waarin een middel ze
doorloopt — kandidaat, in de sluis, eruit, afgewezen, breed uitgezonderd — niet
alfabetisch. Standaard staan **In de sluis** en **Sluiskandidaat** aan; dat zijn
er nu 57.

Drie grafieken:

- **Hoogste geraamde kosten** — liggende staven per regel, gekleurd naar domein,
  zodat één grafiek zowel "welke" als "welk domein" beantwoordt. Standaard de
  hoogste vijftien, met een knop voor de rest. Klikken opent het detailpaneel.
- **Per domein** — dezelfde domeinkleuren, zodat de twee grafieken op elkaar
  aansluiten.
- **Per indicatie** — hier is de rangorde het punt en niet de identiteit, dus
  één tint. De staart wordt samengevouwen tot "overige N indicaties".

De filterbalk werkt door, met één uitzondering: het sluisfilter daar wordt op
dit tabblad genegeerd, anders zouden twee bedieningen om dezelfde keuze vechten.

### Wat de bedragen wel en niet zijn

De bron heeft twee sluis-specifieke velden, `Total cost for sluice` en
`Maximum patient volume for sluice`. Die zijn **vrijwel overal leeg** — bij 1 van
de 244 sluisregels, en die ene staat op € 0. Daarom staat hier de algemene
kostenraming.

Twee dingen die de pagina zelf ook in de voetnoot zet:

- **17 van de 57** middelen hebben geen raming en tellen in geen van de
  grafieken mee. Zonder die vermelding zou de ranglijst een volledigheid
  suggereren die er niet is.
- **Stoffen kunnen meerdere keren voorkomen**, met een eigen raming per
  indicatie. Belzutifan staat er twee keer in: € 343 mln voor nierkanker en
  € 4,5 mln voor een andere oncologische indicatie. Optellen per stof zou die
  patiëntgroepen door elkaar halen, dus de eenheid is de regel — middel plus
  indicatie.

## Het mutatie-overzicht

De Horizonscan publiceert geen archief — op de site staan alleen
PDF-uittreksels uit 2015 en 2016 — dus de historie wordt hier zelf opgebouwd.
Daarom staat `historie/` wél in de repo, anders dan `bron/`:

| Bestand | Wat |
|---|---|
| `historie/momentopname.json` | de stand van vorige keer; hier draait het vergelijken op |
| `historie/mutaties.json` | het groeiende logboek dat het tabblad voedt |

**Sleutel** is het `id`-veld uit de export (1.924 van 1.924 gevuld en uniek). De
slug is dat niet: die kan verspringen als het Zorginstituut kaarten hernummert.

**Twee signalen, die elkaars gat dekken:**

1. Het **versienummer** van het Zorginstituut zelf, dat in de overzichtspagina
   bij elke link staat (`?versie=versie-7`). Loopt die op, dan is die kaart
   aangepast.
2. **Vergelijking per veld** op de momentopname. Die zegt wát er veranderd is.

Signaal 2 mist wijzigingen in velden die we niet volgen; signaal 1 vangt die op
en levert een regel "herzien" op — zonder te doen alsof we weten wát er is
veranderd.

**Wat als mutatie telt** staat in `VELDEN` in `mutaties.py`: registratiefase,
sluisstatus, vergoeding, verwachte registratie, therapeutische waarde, kosten,
totale kosten, patiëntvolume, kader, hoofdindicatie en merknaam — plus nieuw
opgenomen en afgevoerd. Bewust **niet** de onderbouwing en de volledige
indicatie: die teksten worden voortdurend bijgeschaafd en zouden het logboek
vullen met ruis.

**Alleen de maandrun legt mutaties vast** (en een handmatige run via *Run
workflow*). Een push — een wijziging aan de tool zelf — bouwt de pagina wel vers,
maar met `--geen-historie`, dus zonder meetpunt. Anders kreeg het logboek bij
elke codewijziging een extra datum en klopte "sinds de vorige maandelijkse
update" niet meer. Wat er intussen verandert gaat niet verloren: het telt mee bij
de volgende maandrun, die tegen de laatst vastgelegde momentopname vergelijkt.
Lokaal testen doe je om dezelfde reden met `python3 bouw_site.py --geen-historie`.

Het tabblad toont de laatste 24 maanden (`MAANDEN_HISTORIE` in `bouw_site.py`);
het logboek zelf bewaart alles. Een peildatum die al in het logboek staat, wordt
bij een herhaalde run vervangen in plaats van verdubbeld.

## De ATC-koppeling met het add-on dashboard

De Horizonscan geeft zelf geen ATC-code. Die komt uit twee bestanden die
`ophalen.py` meehaalt: de **Farmatec add-on GS-lijst** (het gezaghebbende
antwoord op de vraag of iets nú een add-on geneesmiddel is) en het
**GIP-bestand** (de indeling waarop het add-on dashboard draait).

Beide schrijven Nederlands waar de Horizonscan Engels schrijft
(`BRENTUXIMAB VEDOTINE` tegenover `Brentuximab vedotin`), dus exact vergelijken
is niet genoeg. De koppeling gaat in drie stappen: exact op genormaliseerde
stofnaam, dan een spellingsvariant, dan `atc_correcties.json`.

Een spellingsvariant moet in de **staart** verschillen, niet in de kop — vandaar
de eis in `spellingsvariant()` dat de eerste vijf letters gelijk zijn. Zonder die
eis koppelt `difflib` **deuruxolitinib aan ruxolitinib**, twee verschillende
middelen. Zo'n afgewezen bijna-treffer wordt bij het bouwen gemeld, zodat je hem
desgewenst handmatig kunt vastleggen:

```json
{ "Deuruxolitinib": "D11AH09", "Een middel dat juist níét gekoppeld moet worden": null }
```

**Dekking: 636 van de 1.924 regels (200 stoffen), waarvan 634 nu al add-on.**
Dat is geen tekortkoming van het matchen maar de werkelijke overlap: de
GS-lijst bevat ruim 350 stoffen, en een Horizonscan-middel zonder ATC heeft
simpelweg nog geen add-on tegenhanger. Juist dat maakt het filter **"Al add-on"**
bruikbaar — wat eronder valt is de pijplijn die er de komende jaren bij kan komen.

In het detailpaneel staat de naam waaróp gekoppeld is erbij, zodat een verkeerde
koppeling opvalt in plaats van als feit te blijven staan. De link gaat naar
`…/preferentiebeleid/addon/#atc=<code>`; dat dashboard zet die code bij het
laden in zijn zoekveld.

## Publiceren

`deploy_ftp.py` zet `horizonscan.html` als `index.html` op de server. Het is
overgenomen uit de preferentiebeleid-repo — daar zit de kennis over deze hosting
in (TLS-sessie hergebruiken op het datakanaal, een certificaat op een andere
naam) — met één toevoeging: `controleer_doelmap()` stopt als het FTP-account
niet in de bedoelde map uitkomt. Zonder die controle zou `index.html` in de map
van een andere pagina belanden en die overschrijven.

### Welk FTP-account

De pagina staat op <https://medicatieadvies.nl/horizonscan/>.

Dat vraagt een FTP-account met `public_html` als hoofdmap. Het oorspronkelijke
account van het preferentiebeleid is bij Cloud86 vastgezet op zijn eigen map —
voor die verbinding *is* dat de hoofdmap en bestaat er niets ernaast. Daarom
draait deze pagina op een tweede account dat een niveau hoger begint, ingesteld
via `FTP_USER_HORIZONSCAN` en `FTP_PASS_HORIZONSCAN`. Het preferentiebeleid
blijft zijn eigen account gebruiken en is hier niet door geraakt.

Tot 14 september 2026 stond de pagina op `/preferentiebeleid/horizonscan/`.

### Eenmalig instellen

1. Maak in het bestandsbeheer van de hoster de map `public_html/horizonscan`
   aan. Het deployscript maakt die niet zelf — met opzet, want dan zou een
   typefout een nieuwe map opleveren in plaats van een foutmelding.

   Vergeet je dit, dan gaat er niets stuk: `controleer_doelmap()` stopt vóór het
   uploaden zodra de verbinding niet in de bedoelde map uitkomt. Zonder die
   controle zou `index.html` in `public_html` belanden en de homepage van de
   site overschrijven.
2. Zet vijf secrets klaar (Settings → Secrets and variables → Actions):

   | Secret | Waarde |
   |---|---|
   | `FTP_HOST` | `ftp.medicatieadvies.nl` |
   | `FTP_USER` | het Cloud86-account dat op de map `preferentiebeleid` is vastgezet |
   | `FTP_PASS` | het wachtwoord daarvan |
   | `FTP_CERT_HOST` | `shared21.cloud86-host.nl` |
   | `FTP_USER_HORIZONSCAN` | het account met `public_html` als hoofdmap |
   | `FTP_PASS_HORIZONSCAN` | het wachtwoord daarvan |
   | `FTP_DIR_HORIZONSCAN` | `horizonscan` |

**Secrets gelden per repository.** Dit is een eigen repo, dus de secrets van
`preferentiebeleid` gelden hier níét — ook al is het hetzelfde FTP-account. Bij
het add-on dashboard hoefde alleen `FTP_DIR_ADDON` gezet te worden, maar dat zit
ín die andere repo en deelt daardoor de rest. Hier moeten alle vijf.

`FTP_CERT_HOST` is niet optioneel op deze hosting: het certificaat van de
FTP-server staat op `shared21.cloud86-host.nl` en niet op de naam waarmee je
verbindt. Zonder dat secret loopt de verbinding op een certificaatfout vast.
Uit te lezen met:

```python
import deploy_ftp; print(deploy_ftp.certificaatnamen("ftp.medicatieadvies.nl"))
```

Reset je het FTP-wachtwoord, werk het dan **in beide repo's** bij — anders valt
de maandelijkse run van het preferentiebeleid stil.

Let op: een secret toevoegen of wijzigen start geen workflow. Na het instellen
moet je hem zelf aftrappen met *Run workflow*.

Instellingen komen uit omgevingsvariabelen of uit een `.env` naast het script
(die staat in `.gitignore`). Uitproberen zonder iets te versturen:

```
python3 deploy_ftp.py --dry-run
```

### Het add-on dashboard

Staat sinds 14 september 2026 op <https://medicatieadvies.nl/addon/> en draait
op hetzelfde tweede FTP-account, via `FTP_USER_ADDON` en `FTP_PASS_ADDON` in de
`preferentiebeleid`-repo. Daarvoor stond het op `/preferentiebeleid/addon/`.

`ADDON_DASHBOARD` in `bouw_site.py` wijst daarheen; dat is waar de ATC-links in
het detailpaneel op uitkomen. **Verhuist dat dashboard nog eens, dan moet deze
constante mee en moet horizonscan opnieuw draaien** — anders wijzen 636 links
naar een map die stil is komen te staan.

### Achtergebleven mappen

Een verhuisde map blijft gewoon staan met de laatste versie erin. Die pagina
ziet er goed uit maar bevriest, en dat is lastiger te herkennen dan een 404.
Zet er daarom een `.htaccess` neer die doorverwijst:

```apache
RedirectMatch 301 ^/preferentiebeleid/horizonscan/?$ /horizonscan/
```

Browsers houden de hash bij een doorverwijzing vast, dus eerder gedeelde links
met filters blijven werken.

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

## Bezoekersteller

Onderaan `template.html` staat GoatCounter, hetzelfde account als bij het add-on
dashboard: <https://bossenga.goatcounter.com>. Geen cookies, geen
persoonsgegevens.

Het pad is **vast** op `horizonscan` in plaats van de URL. Dat is hier geen
detail: de filters staan in de hash, dus met de standaardinstelling zou elke
gedeelde link als een aparte pagina in de statistieken belanden en was het
totaal nergens meer af te lezen.

Lokaal testen vervuilt de cijfers niet — `count.js` telt niet op `localhost` of
via `file://`. Te controleren in de console van de pagina:

```js
window.goatcounter.filter()   // geeft "localhost", dus er wordt niets verstuurd
```

## Controle bij het bouwen

`bouw_site.py` weigert te schrijven als het paginascript een syntaxfout bevat
(`node --check`). Dat is niet theoretisch: bij het bouwen van het mutatietabblad
belandde een blok CSS in het scriptdeel, waardoor de pagina wel opende maar leeg
bleef. Zonder node wordt de controle overgeslagen, met een melding.
