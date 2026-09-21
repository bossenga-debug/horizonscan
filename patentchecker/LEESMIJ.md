# Patentchecker dure add-on geneesmiddelen

Eén zelfstandige pagina (`patentchecker.html`) die voor elk add-on geneesmiddel
met meer dan € 10 mln Zvw-vergoeding per jaar laat zien:

- wanneer het **SPC** (aanvullend beschermingscertificaat op het Europese
  basisoctrooi) afloopt, inclusief pediatrische verlenging;
- wanneer de **marktbescherming** afloopt (10 jaar na de eerste EU-vergunning);
- welke **biosimilars en generieken** geregistreerd zijn, in beoordeling zijn bij
  EMA, in de Horizonscan-pijplijn staan of in studies zitten;
- hoeveel **handelsvergunningen** er op de Nederlandse add-on-lijst staan;
- of de datum **overeenkomt met het Horizonscan-overzicht** patentverloop.

Bedoeld voor <https://medicatieadvies.nl/patentchecker/>. Zelfde opzet als de
horizonscan- en add-on-pagina's.

## Gebruik

```
python3 bijwerken.py            # alles ophalen en herbouwen (duurt ~5 minuten door het register)
python3 bijwerken.py --altijd   # ook herbouwen als er niets veranderd is
python3 bouw_site.py            # alleen herbouwen uit bron/ (bijv. na een wijziging aan template.html)
python3 ophalen.py --zonder-register   # snel: alles behalve RVO en ClinicalTrials.gov
python3 deploy_ftp.py [--dry-run]      # uploaden
```

`bouw_site.py --geen-historie` bouwt zonder een meetpunt in het logboek te zetten;
gebruik dat bij proberen, anders krijgt het logboek een extra datum.

## Bestanden

| Bestand | Wat |
|---|---|
| `middelen.py` | selectie (drempel, productgroepen), naamkoppeling NL ↔ INN, lezers voor GIP, EMA en Farmatec |
| `ophalen.py` | haalt alle bronnen naar `bron/` (niet in git) |
| `rvo.py` | leest SPC's uit het octrooiregister |
| `hs_pdf.py` | leest de tabel uit het Horizonscan-overzicht patentverloop |
| `bouw_site.py` | voegt samen, vergelijkt met `historie/`, schrijft `patentchecker.html` |
| `template.html` | de pagina; de data komt op de plek van `/*DATA*/null/*DATA*/` |
| `historie/` | momentopname, logboek en elke gelezen editie van het Horizonscan-overzicht (wél in git) |

## Bronnen

| Bron | Waarvoor | Bijzonderheid |
|---|---|---|
| Octrooiregister RVO (`mijnoctrooi.rvo.nl/fo-eregister-view`) | SPC-einddatum, verlenging, basisoctrooi | geen officiële API; zie hieronder |
| EMA-medicijnentabel (`medicines-output-medicines-report_en.xlsx`) | biosimilars/generieken, eerste vergunning, weesstatus | kop staat niet op regel 1 |
| EMA "applications under evaluation" (maandelijkse xlsx) | aanvragen in beoordeling | URL bevat de maand; EMA geeft snel HTTP 429 |
| Horizonscan-export (8 domeinen) | biosimilars/generieken in de pijplijn | sessiecookie nodig, lezen op kolompositie |
| Horizonscan-overzicht patentverloop (PDF) | vergelijking + terugval | zie "Nieuwe Horizonscan-publicatie" |
| ClinicalTrials.gov API v2 | biosimilarstudies | filter op titel, zie `biosimilar_van()` |
| Farmatec add-on GS-lijst | handelsvergunningen in NL | tel `RegistratieNummer`, niet `Fabrikant` |
| GIP add-on Zvw meerjaren | selectie en kosten | laatste jaar voorlopig |

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
`patentchecker/`. Hij staat los van de horizonscan-workflow en gebruikt
`FTP_*_HORIZONSCAN` (terugvallend op `FTP_*`) en `FTP_CERT_HOST`. De doelmap
`patentchecker` staat gewoon in de workflow. Die map bestaat in `public_html`;
`deploy_ftp.py` maakt geen mappen aan en stopt als de doelmap niet klopt.

`bron/` wordt genegeerd door de `.gitignore` van de repo (het patroon `bron/`
geldt ook in submappen); `historie/` gaat wél mee.

Onbekend tot de eerste run in GitHub: of het RVO-register verzoeken vanaf de
servers van GitHub (VS) accepteert. `bijwerken.py --ci` stopt als minder dan 30
middelen een SPC uit het register krijgen, zodat een geblokkeerd register nooit
een lege pagina oplevert.
