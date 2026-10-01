# Diagnosegroei per specialisme

Dashboard met de groei van DBC-diagnoses per specialisme (Open DIS, NZa),
geschatte DBC-kosten, en de koppeling met add-on geneesmiddelen (GIP,
Zorginstituut). Live op <https://medicatieadvies.nl/diagnosegroei/>.

## Bestanden

| Bestand | Wat |
|---|---|
| `dashboard.html` | het dashboard, één zelfstandig bestand (wordt `index.html` op de site) |
| `template.html` | opmaak en paginacode; hier pas je het dashboard aan |
| `build.py` | haalt Open DIS op en bouwt `dashboard.html` uit de template |
| `koppel_data.py` | rekent de add-on-koppeling per cluster uit |
| `bijwerken.py` | kijkt of er nieuwe data is, haalt GIP op, bouwt en controleert |
| `stand.json` | peildatum en GIP-bestanden van de laatste bouw (wijzigingssignaal) |
| `koppeling/` | handmatige koppeltabel diagnoses ↔ add-ons, zie `koppeling/LEESMIJ.md` |
| `deploy_ftp.py`, `htaccess` | upload naar medicatieadvies.nl (zelfde aanpak als de patentchecker) |
| `data/` | brondata, staat niet in git en wordt elke run opgehaald |

## Bijwerken

```
python3 bijwerken.py            # alleen bouwen als er nieuwe data is
python3 bijwerken.py --check    # alleen kijken
python3 bijwerken.py --forceer  # altijd bouwen, bijvoorbeeld na een wijziging aan de koppeltabel
```

De workflow `.github/workflows/diagnosegroei.yml` draait op de 20e en 27e van
de maand, bij een push naar de template, de scripts of de koppeltabel, en met de
hand. Het geheel duurt ongeveer twee minuten. Uploaden gebeurt pas als de
repository-variabele `DIAGNOSEGROEI_LIVE` op `true` staat.

## Bronnen en hun eigenaardigheden

- **Open DIS**: `https://opendisdata.nza.nl/download/csv/<bestand>` (let op:
  `/download/`, niet `/downloads/`). De server weigert de standaard
  Python-user-agent met een 403. `02_DBC_PROFIEL.csv` is ongeveer 750 MB; daaruit
  bewaren we alleen de verstrekkingsactiviteiten voor dure geneesmiddelen.
- **GIP**: de downloadsleutel op de open-datapagina wisselt per bezoek, dus de
  link wordt elke keer uitgelezen. Dat is dezelfde aanpak als het add-on-dashboard.
- **Recente jaren zijn onvolledig.** Een DBC telt in zijn startjaar en komt pas
  na sluiting in DIS. Het jaar vóór de peildatum is voorlopig, het lopende jaar
  grotendeels leeg. In GIP zijn de laatste twee jaren voorlopig (`*`).
