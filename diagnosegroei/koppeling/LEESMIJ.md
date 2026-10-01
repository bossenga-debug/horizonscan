# Koppeltabel diagnoses ↔ add-on geneesmiddelen

Er is geen gezamenlijke sleutel tussen Open DIS (diagnoses) en GIP (add-on
uitgaven per ATC). Deze map legt die koppeling vast via **clusters**: een groep
DBC-diagnoses en de add-on middelen die daarbij horen.

| Bestand | Inhoud | Beheer |
|---|---|---|
| `clusters.csv` | cluster, soort, DIS-verstrekkingscodes | handmatig |
| `cluster_diagnoses.csv` | specialisme + diagnosecode per cluster, rol kern/aanvullend | handmatig |
| `cluster_atc.csv` | middelen per cluster, met status | handmatig, gestart vanuit het voorstel |
| `cluster_atc_voorstel.csv` | automatisch voorstel uit Farmatec-indicaties | wordt overschreven |
| `koppeling.py` | maakt het voorstel en controleert de tabellen | |

Bestanden zijn puntkomma-gescheiden UTF-8 met BOM, zodat Excel ze direct goed
opent. Sla ze in Excel op als *CSV UTF-8 (puntkomma)*.

## Nakijken

In `cluster_atc.csv` staat per regel een `status`:

- `concept`: voorgesteld, nog niet bekeken
- `nagekeken`: bevestigd
- `uitgesloten`: onterechte treffer. De regel blijft staan, zodat hij niet
  opnieuw als nieuw wordt gemeld.

`python3 koppeling.py` controleert of alle diagnosecodes bestaan en patiënten
hebben, of de ATC-codes in GIP voorkomen, hoeveel van de add-on-uitgaven
gekoppeld is, en welke middelen in een nieuw voorstel zitten die nog niet in
`cluster_atc.csv` staan. `--voorstel` schrijft het voorstel opnieuw, bijvoorbeeld
na een nieuwe Farmatec-lijst.

## Twee dingen om te weten

- **Onderhuidse middelen staan nauwelijks in DIS.** Verstrekkingscode 039136
  (biologicals per injectie) wordt weinig geregistreerd. Bij psoriasis, eczeem,
  artritis psoriatica, RA en axSpA zegt het aandeel "behandeld" volgens DIS
  daarom weinig. Daar zijn de GIP-gebruikers de maat. Bij infuusmiddelen (MS,
  IBD, myeloom, oncologie) en intravitreale injecties werkt het wel.
- **Gedeelde middelen.** Ongeveer de helft van de gekoppelde uitgaven zit in
  middelen die bij meer clusters horen (pembrolizumab, TNF-remmers,
  ustekinumab). GIP splitst niet per indicatie, dus clusterkosten mag je niet
  zomaar optellen. De kolom `gedeeld_met` laat zien welke dat zijn.

## Officiële groeperingen uit de risicoverevening (FKG en DKG)

`python3 koppeling.py --rv` haalt de referentiebestanden FKG_C en DKG_C op
(bijlagen 2 en 4 bij de Regeling risicoverevening, jaarpagina `zvw-<jaar>` op
zorginstituutnederland.nl, als .ods). Ze worden automatisch als kolom
`fkg_<jaar>` in `cluster_atc.csv` en `dkg_<jaar>` in `cluster_diagnoses.csv`
gezet, en de controle meldt welke add-on-middelen uit de FKG-klassen nog in
geen enkel cluster zitten.

Ze vervangen de koppeltabel niet:

- FKG koppelt ATC → kostengroep, DKG koppelt diagnose → kostengroep, maar er is
  geen officiële brug FKG ↔ DKG.
- De add-on-klassen zijn grof: alle auto-immuun-add-ons zitten in AUT, alle
  oncolytica in CAN. Er wordt niet gesplitst naar RA, IBD of psoriasis, of naar
  longkanker en melanoom.
- De FKG-lijst loopt een jaar achter: model 2026 gebruikt de G-Standaard 2024.
  Nieuwe middelen ontbreken dus. MS-infuusmiddelen (ocrelizumab, natalizumab)
  zitten in geen enkele FKG.
- DKG bevat alleen diagnoses die kosten voorspellen. Eczeem, artritis
  psoriatica en een deel van axSpA ontbreken daarin.

## Voorfase en weergave in het dashboard

`cluster_voorfase.csv` legt per cluster de extramurale eerstelijnsmiddelen vast.
Het bestand wordt één keer voorgesteld uit de FKG-klassen in `VOORFASE` (bovenin
`koppeling.py`): REU, CRO, PSO, RMS, AST, en HOR gesplitst naar prostaat en mamma.
Daarna beheer je het met de hand, net als `cluster_atc.csv`. De
gebruikersaantallen komen uit GIP farmacie.

`koppel_data.py` rekent per cluster vier reeksen uit voor het tabblad
*Add-on koppeling*: diagnose, voorfase, behandeld (DIS) en add-on (GIP). Gedeelde
middelen worden verdeeld naar rato van de behandelde patiënten per cluster.
Het dashboard markeert een cluster als "onvolledig" als DIS minder dan de helft
van de add-on-gebruikers telt. Dat komt door orale en onderhuidse middelen; de
verdeling is daar onzeker.

Deeplinks: `#koppeling-ms` (cluster) en `#atc=L01FF02` of `#L01FF02` (middel).
De kale vorm werkt ook binnen een claude.ai-artifact.

## Behandeld: toedieningsactiviteit of geneesmiddel-zorgproduct

Kolom `behandeld_bron` in `clusters.csv` bepaalt per cluster waar "behandeld"
vandaan komt:

- `activiteit`: verstrekkingsactiviteiten uit 02_DBC_PROFIEL (bijvoorbeeld
  039137 biologicals per infuus). Dit werkt het best bij auto-immuunziekten,
  astma en oog.
- `zorgproduct`: zorgproducten waarvan de omschrijving over toediening,
  begeleiding of verstrekking van geneesmiddelen gaat (bijvoorbeeld 028999017
  "Toediening immunotherapie via infuus/injectie"). Het patroon staat in
  `ZPD_GENEESMIDDEL` in `koppel_data.py`. Deze zorgproducten tellen ook de
  begeleiding van orale therapie, en sluiten bij oncologie en hematologie veel
  beter aan op de add-on gebruikers.

Beide bronnen tellen een patiënt met meer zorgproducten of activiteiten in een
jaar meer keer. Per diagnose wordt daarom begrensd op het aantal patiënten met
die diagnose. Kies `activiteit` als de zorgproductbron tegen die grens aanloopt;
bij myeloom gebeurt dat (100% in alle jaren), en dan valt er geen trend meer te
zien.
