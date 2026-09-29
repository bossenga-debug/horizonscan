# Patentchecker dure geneesmiddelen

Twee zelfstandige pagina's op dezelfde code en hetzelfde sjabloon:

| Set | Pagina | Selectie | Bron van de kosten |
|---|---|---|---|
| `addon` | `patentchecker.html` → `/patentchecker/` | boven € 10 mln per jaar (69 middelen) | GIP add-on Zvw |
| `gvs` | `patentchecker_gvs.html` → `/patentchecker/gvs.html` | boven € 1 mln in het laatste jaar, en alleen wat nog bescherming heeft | GIP farmacie Zvw |

De sets staan in `SETS` in `middelen.py`; `--set addon`, `--set gvs` of allebei
(de standaard). Beide pagina's laten per middel zien:

- wanneer het **SPC** (aanvullend beschermingscertificaat op het Europese
  basisoctrooi) afloopt, inclusief pediatrische verlenging;
- wanneer de **marktbescherming** afloopt (10 jaar na de eerste EU-vergunning);
- welke **biosimilars en generieken** geregistreerd zijn, in beoordeling zijn bij
  EMA, in de Horizonscan-pijplijn staan of in studies zitten;
- hoeveel **handelsvergunningen** er op de Nederlandse add-on-lijst staan;
- of de datum **overeenkomt met het Horizonscan-overzicht** patentverloop.

Wat de sets verschilt, staat bij "Nederlandse concurrentie" hieronder. Zelfde
opzet als de horizonscan- en add-on-pagina's.

## Gebruik

```
python3 bijwerken.py                   # beide sets ophalen en herbouwen (~20 min door het register)
python3 bijwerken.py --altijd          # ook herbouwen als er niets veranderd is
python3 bouw_site.py                   # alleen herbouwen uit bron/ (na een wijziging aan template.html)
python3 bouw_site.py --set gvs         # één set
python3 ophalen.py --set gvs           # idem bij het ophalen
python3 ophalen.py --zonder-register   # snel: alles behalve RVO en ClinicalTrials.gov
python3 deploy_ftp.py [--dry-run]      # beide pagina's uploaden
```

`bouw_site.py --geen-historie` bouwt zonder een meetpunt in het logboek te zetten;
gebruik dat bij proberen, anders krijgt het logboek een extra datum.

## Bestanden

| Bestand | Wat |
|---|---|
| `middelen.py` | de sets, selectie (drempel of top-N, productgroepen), naamkoppeling NL ↔ INN, lezers voor GIP, EMA en Farmatec |
| `ophalen.py` | haalt alle bronnen naar `bron/` (niet in git) |
| `rvo.py` | leest SPC's uit het octrooiregister |
| `hs_pdf.py` | leest de tabel uit het Horizonscan-overzicht patentverloop |
| `bouw_site.py` | voegt samen, vergelijkt met `historie/`, schrijft `patentchecker.html` |
| `template.html` | de pagina; de data komt op de plek van `/*DATA*/null/*DATA*/` |
| `historie/` | momentopname en logboek van de add-on set, plus elke gelezen editie van het Horizonscan-overzicht (wél in git) |
| `historie/gvs/` | idem voor de GVS-set |

## Bronnen

| Bron | Waarvoor | Bijzonderheid |
|---|---|---|
| Octrooiregister RVO (`mijnoctrooi.rvo.nl/fo-eregister-view`) | SPC-einddatum, verlenging, basisoctrooi | geen officiële API; zie hieronder |
| EMA-medicijnentabel (`medicines-output-medicines-report_en.xlsx`) | biosimilars/generieken, eerste vergunning, weesstatus | kop staat niet op regel 1 |
| EMA "applications under evaluation" (maandelijkse xlsx) | aanvragen in beoordeling | URL bevat de maand; EMA geeft snel HTTP 429 |
| Horizonscan-export (8 domeinen) | biosimilars/generieken in de pijplijn | sessiecookie nodig, lezen op kolompositie |
| Horizonscan-overzicht patentverloop (PDF) | vergelijking + terugval | zie "Nieuwe Horizonscan-publicatie" |
| ClinicalTrials.gov API v2 | biosimilarstudies | filter op titel, zie `biosimilar_van()` |
| Farmatec add-on GS-lijst | handelsvergunningen in NL (set addon) | tel `RegistratieNummer`, niet `Fabrikant` |
| Preferentiebeleid (eigen pagina) | concurrentie in NL (set gvs) | JSON uit de broncode van medicatieadvies.nl/preferentiebeleid |
| GIP add-on / farmacie Zvw meerjaren | selectie en kosten | add-on markeert voorlopige jaren met `*`, farmacie niet |

## Wat de GVS-set overslaat

De extramurale farmacie bestaat voor het grootste deel uit oude generieken; een
lijst op kosten alleen zou daar vol mee staan. De GVS-set slaat daarom over:

- middelen die **preferent zijn aangewezen** (uit de preferentiepagina, zie
  hieronder) — preferentiebeleid kan alleen bij meerdere leveranciers, dus daar
  is de bescherming al voorbij;
- middelen waarvan de **bescherming verlopen** is, dat wil zeggen dat de
  vroegste toetreding (SPC-einde of marktbescherming) in het verleden ligt.

Die tweede groep wordt onthouden in `historie/gvs/uitgesloten.json`, met naam,
datum en reden. Dat bestand staat in git en zorgt dat het octrooiregister niet
elke maand opnieuw wordt bevraagd over middelen waar niets meer te volgen valt;
`ophalen.py` slaat ze over en `bouw_site.py` houdt ze uit de pagina. Blijkt bij
een bouw een middel alsnog uit patent, dan wordt het daar toegevoegd.

Haal een middel uit dat bestand als je het opnieuw wilt laten beoordelen (bijv.
na een nieuw certificaat); de volgende run zoekt het dan weer op.

## Nederlandse concurrentie

Voor add-on middelen telt het aantal handelsvergunningen op de Farmatec
add-on GS-lijst. Voor GVS-middelen bestaat zo'n lijst niet. Daar gebruiken we
of het middel **preferent is aangewezen**: preferentiebeleid kan alleen bij een
stof met meerdere leveranciers, dus aangewezen betekent dat er generieken op de
Nederlandse markt zijn. Die gegevens komen uit de preferentiepagina van deze
site zelf (`const DATA` in de HTML; lezen met `json.JSONDecoder().raw_decode`,
niet met een regex — de data bevat zelf accolades). Lukt dat niet, dan valt
alleen die kolom weg.

## Het octrooiregister

Er is geen gedocumenteerde API, maar de zoekpagina praat JSON met de server:
startpagina ophalen (cookie + `_csrf`), `POST /search` met `rightType[0]=SPC` en
`title=<INN>`, dan per treffer de detailpagina. **Let op:** in het detail-adres
staat de positie van de treffer op de *derde* plek
(`details/<id>/0/<positie>/1/10/0/1/0/...`). Op de zesde plek werken alleen de
eerste twee treffers; daarna komt een lege pagina met HTTP 200 terug.

Het register zoekt op woorden in de titel van het certificaat. Staat een SPC
onder een merk- of chemische naam, voeg dan een zoekterm toe aan `RVO_EXTRA`
in `middelen.py`. Wat dan nog niet gevonden wordt, valt terug op de datum uit
het Horizonscan-overzicht (op de pagina gemarkeerd met **HS**). Nu geldt dat
voor dabrafenib, infliximab, axicabtagene ciloleucel en agalsidase bèta;
osimertinib, nusinersen en onasemnogene staan in het register alleen als
lopende aanvraag.

Keuze van het "bepalende" certificaat: alleen certificaten over de stof zelf
(niet combinaties of afgeleide stoffen, zie `hoofdcertificaat()`), dan het
actieve met de laatste einddatum, anders een lopende aanvraag, anders het
laatst verlopen certificaat. Bij een vervallen certificaat (jaartaks niet
betaald) telt de vervaldatum, bij een ongeldig certificaat (basisoctrooi
vervallen) is de einddatum onbekend.

## Nieuwe Horizonscan-publicatie

Gaat vanzelf. `ophalen.py` neemt steeds het bovenste bericht over
"patentverloop" op de nieuwspagina van de Horizonscan (die zet het nieuwste
bovenaan; oudere berichten krijgen `-0`, `-1`, ... achter de slug) en haalt de
PDF op. Verschijnt er een nieuwe editie, dan:

1. wordt de vergelijking op de pagina tegen die editie gemaakt;
2. komt er een regel "Nieuw Horizonscan-overzicht" in het logboek;
3. wordt de gelezen tabel bewaard als `historie/hs_patent_<stand>.json`, zodat
   oudere edities niet verloren gaan.

Kan de nieuwe PDF niet worden gelezen (minder dan 30 regels of geen "stand van
zaken"), dan wordt de pagina tóch gebouwd, zonder vergelijking en met een
melding op het tabblad Vergelijking. Pas dan `hs_pdf.py` aan. Testen kan los:
`python3 hs_pdf.py bron/hs_patent.pdf`.

Een naam in de PDF die niet koppelt (een typefout zoals "Ocrilizumab"), zet je
in `PDF_NAAM` in `bouw_site.py`.

## Combinatiepreparaten

GIP schrijft "Ivacaftor met tezacaftor en elexacaftor", EMA
"ivacaftor;tezacaftor;elexacaftor". `inn_voor()` koppelt daarom als tweede stap
op de vérzameling stofnamen — nog steeds exact per stof. In het octrooiregister
wordt per component gezocht, en een certificaat telt alleen mee als álle stoffen
in de titel staan: een SPC op alleen valsartan hoort niet bij valsartan met
sacubitril.

## Interpretatie

- **Vroegste toetreding** = de laatste van SPC-einde en marktbescherming. Het is
  een ondergrens: vervolgoctrooien, rechtszaken en lanceerplanning kunnen later
  uitkomen. Een generiek mag wél al vóór die datum geregistreerd worden.
- Marktbescherming is gerekend als 10 jaar; +1 jaar bij een nieuwe indicatie
  staat niet in de brondata.
- Een verschil van precies 6 maanden met de Horizonscan is een pediatrische
  verlenging die na dat overzicht is toegekend. Andere verschillen (nu:
  secukinumab, register 2030 tegenover Horizonscan 2033) zijn het nakijken waard.
- Het oudste product van een stof bij EMA geldt als origineel; latere producten
  zonder biosimilarvlag van een andere houder staan in het detailpaneel als
  "andere producten" (bijv. ABP 710 bij infliximab), die van dezelfde houder als
  eigen lijnextensie (Finlee naast Tafinlar).

## Publicatie

Staat als submap in de repo `bossenga-debug/horizonscan`, omdat die repo al de
secrets heeft van het FTP-account met `public_html` als hoofdmap. GitHub-secrets
zijn niet terug te lezen en gelden per repository; een eigen repo had betekend
dat het FTP-wachtwoord opnieuw opgezocht moest worden.

Workflow `../.github/workflows/patentchecker.yml` draait op de 10e van de maand
(horizonscan de 5e, addon de 8e), bij een handmatige start en bij een push naar
`patentchecker/`. Eén run doet beide sets en zet ze in dezelfde map:
`index.html` (add-on) en `gvs.html` (GVS). Reken op ruim twintig minuten;
het octrooiregister is het langste onderdeel. Hij staat los van de horizonscan-workflow en gebruikt
`FTP_*_HORIZONSCAN` (terugvallend op `FTP_*`) en `FTP_CERT_HOST`. De doelmap
`patentchecker` staat gewoon in de workflow. Die map bestaat in `public_html`;
`deploy_ftp.py` maakt geen mappen aan en stopt als de doelmap niet klopt.

`bron/` wordt genegeerd door de `.gitignore` van de repo (het patroon `bron/`
geldt ook in submappen); `historie/` gaat wél mee.

Onbekend tot de eerste run in GitHub: of het RVO-register verzoeken vanaf de
servers van GitHub (VS) accepteert. `bijwerken.py --ci` stopt als minder dan 30
middelen een SPC uit het register krijgen, zodat een geblokkeerd register nooit
een lege pagina oplevert.
