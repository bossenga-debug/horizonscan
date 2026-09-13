#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Haalt de Horizonscan-data op voor alle acht domeinen.

Per domein worden twee dingen opgehaald:

  bron/hs_<domein>.csv     de CSV-export met alle velden
  bron/links_<domein>.json de slugs van de detailpagina's

De CSV-export zit achter een sessiecookie. Zonder cookie geeft de server
netjes HTTP 200 met een leeg bestand terug -- geen foutmelding, gewoon nul
bytes. Daarom eerst de domeinpagina ophalen (die zet het cookie), en die
pagina daarna als referer meesturen bij de export.

Die pagina hebben we toch nodig: de export bevat wel een id per middel, maar
dat id werkt niet in een URL (het redirect naar pagenotfound). De links naar
de detailpagina's staan alleen in de HTML van het overzicht.

Daarnaast worden de twee bronnen voor de ATC-codes opgehaald, want de
Horizonscan zelf geeft geen ATC.

Gebruik:  python3 ophalen.py [--check] [--ci]

  --check  alleen kijken of er iets veranderd is, niets wegschrijven
  --ci     hard stoppen zodra een bron niet gevonden wordt (voor GitHub Actions)
"""
import csv
import html
import io
import json
import os
import re
import sys
import unicodedata
from urllib.parse import urlencode

import requests

BASIS = 'https://www.horizonscangeneesmiddelen.nl'
HIER = os.path.dirname(os.path.abspath(__file__))
BRON = os.path.join(HIER, 'bron')

# De slugs zoals de site ze gebruikt, met de Nederlandse naam die wij tonen.
DOMEINEN = {
    'oncologie': 'Oncologie',
    'hematologie': 'Hematologie',
    'cardiovasculaire-aandoeningen': 'Cardiovasculaire aandoeningen',
    'chronische-immuunziekten': 'Chronische immuunziekten',
    'infectieziekten': 'Infectieziekten',
    'longziekten-algemeen': 'Longziekten',
    'neurologische-aandoeningen': 'Neurologische aandoeningen',
    'stofwisseling-en-endocrinologie': 'Stofwisseling en endocrinologie',
}

# Bronnen voor de ATC-codes. De Horizonscan zelf geeft geen ATC; die komt uit de
# add-on GS-lijst van Farmatec (het gezaghebbende antwoord op "is dit een add-on
# geneesmiddel") aangevuld met de ATC-namen uit het GIP-bestand, want dat is de
# indeling waarop het add-on dashboard draait.
GS_PAGINA = ('https://www.farmatec.nl/prijsvorming/'
             'add-on-geneesmiddelen-sluismiddelen/actuele-publicaties')
GIP_PAGINA = 'https://www.zorgcijfersdatabank.nl/algemeen/open-data-gip'

KOP = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                     'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36'}


def overzicht_url(domein):
    return f'{BASIS}/geneesmiddelen?' + urlencode({'hoofdniveau': 'domein', 'domein': domein})


def export_url(domein):
    return f'{BASIS}/geneesmiddelen/export?' + urlencode({'publicatiedatum': '', 'domein': domein})


def slugify(tekst):
    """Zelfde vorm als de slugs op de site: alleen a-z, 0-9 en koppeltekens."""
    plat = unicodedata.normalize('NFKD', tekst or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', plat.lower()).strip('-')


def lees_links(pagina):
    """Haalt slug, linktekst en versienummer uit de overzichtspagina.

    De linktekst is soms de stofnaam en soms de indicatietekst; beide zijn
    bruikbaar om later de juiste regel bij de juiste slug te zoeken.

    Het versienummer is de teller van het Zorginstituut zelf. Loopt die op, dan
    is die kaart aangepast -- ook als het gaat om een veld dat wij niet volgen.
    Dat is het tweede, onafhankelijke signaal voor het mutatie-overzicht.
    """
    gevonden = {}
    patroon = r'<a[^>]*href="/geneesmiddelen/([a-z0-9-]+)\?versie=versie-(\d+)"[^>]*>(.*?)</a>'
    for m in re.finditer(patroon, pagina, re.S):
        tekst = re.sub(r'<[^>]+>', ' ', m.group(3))
        gevonden[m.group(1)] = {'tekst': html.unescape(' '.join(tekst.split())),
                                'versie': int(m.group(2))}
    return gevonden


def schrijf_als_gewijzigd(pad, inhoud, alleen_kijken=False):
    """Schrijft alleen bij wijziging; de vorige versie blijft als .vorige staan."""
    if isinstance(inhoud, str):
        inhoud = inhoud.encode('utf-8')
    oud = None
    if os.path.exists(pad):
        with open(pad, 'rb') as f:
            oud = f.read()
    if oud == inhoud:
        return False
    if alleen_kijken:
        return True
    if oud is not None:
        os.replace(pad, pad + '.vorige')
    with open(pad, 'wb') as f:
        f.write(inhoud)
    return True


def haal_domein(sessie, domein, alleen_kijken=False):
    pagina = sessie.get(overzicht_url(domein), headers=KOP, timeout=60)
    pagina.raise_for_status()
    links = lees_links(pagina.text)

    export = sessie.get(export_url(domein), headers=dict(KOP, Referer=overzicht_url(domein)),
                        timeout=120)
    export.raise_for_status()
    if not export.content:
        raise RuntimeError(
            f'{domein}: de export kwam leeg terug. Dat betekent bijna altijd dat het\n'
            f'sessiecookie niet is meegestuurd -- controleer of de domeinpagina eerst\n'
            f'is opgehaald met dezelfde sessie.')

    gewijzigd_csv = schrijf_als_gewijzigd(
        os.path.join(BRON, f'hs_{domein}.csv'), export.content, alleen_kijken)
    gewijzigd_links = schrijf_als_gewijzigd(
        os.path.join(BRON, f'links_{domein}.json'),
        json.dumps(links, ensure_ascii=False, indent=1, sort_keys=True), alleen_kijken)

    # Niet op newlines tellen: velden als de onderbouwing lopen over meerdere
    # regels door, dus alleen de CSV-parser weet hoeveel middelen er staan.
    lezer = csv.reader(io.StringIO(export.content.decode('utf-8-sig')), delimiter=';')
    aantal = max(0, sum(1 for _ in lezer) - 1)
    return gewijzigd_csv or gewijzigd_links, aantal, len(links)


def gs_link(sessie):
    """Nieuwste add-on GS-ZIP via de documentpagina op farmatec.nl.

    De URL bevat de publicatiemaand, dus die moet elke keer opnieuw van de
    overzichtspagina worden afgelezen; een vaste link verloopt na een maand.
    """
    pag = sessie.get(GS_PAGINA, headers=KOP, timeout=60).text
    doc = re.search(r'href="(/documenten/[^"]*excel-bestand-add-on-gs-[^"]*)"', pag)
    if not doc:
        return None, None
    docpag = sessie.get('https://www.farmatec.nl' + doc.group(1), headers=KOP, timeout=60).text
    zip_ = re.search(r'href="(https://[^"]+\.zip)"', docpag)
    return (zip_.group(1), 'addon-gs.zip') if zip_ else (None, None)


def gip_link(sessie):
    """Nieuwste 'GIP Addon Zvw meerjaren'-bestand; de downloadsleutel wisselt
    per paginabezoek, dus ook die wordt van de overzichtspagina gelezen."""
    pag = sessie.get(GIP_PAGINA, headers=KOP, timeout=60).text
    for m in re.finditer(r'<a[^>]*href="(/services/file/get\?key=[^"]+)"[^>]*>(.*?)</a>', pag, re.S):
        label = ' '.join(re.sub(r'<[^>]+>', '', m.group(2)).split())
        if re.search(r'GIP\s+Addon\s+Zvw\s+meerjaren', label, re.I):
            return 'https://www.zorgcijfersdatabank.nl' + m.group(1), 'gip_addon.csv'
    return None, None


def haal_atc_bron(sessie, naam, zoeker, alleen_kijken, streng):
    """Haalt een ATC-bronbestand op. Ontbreekt het, dan gaat de rest gewoon door:
    zonder ATC blijft de pagina bruikbaar, alleen de koppeling met het add-on
    dashboard valt weg. Met --ci is dat wel een harde fout."""
    try:
        url, bestand = zoeker(sessie)
    except Exception as e:                                  # netwerk, DNS, time-out
        url, bestand, e = None, None, e
    if not url:
        melding = f'  {naam:32s} geen link gevonden op de overzichtspagina'
        if streng:
            sys.exit(melding + '\nPagina-indeling gewijzigd? Er is niets gepubliceerd.')
        print(melding + '  [overgeslagen]')
        return False
    data = sessie.get(url, headers=KOP, timeout=180).content
    gewijzigd = schrijf_als_gewijzigd(os.path.join(BRON, bestand), data, alleen_kijken)
    print(f'  {naam:32s} {len(data) / 1024:6.0f} kB  '
          f'[{"gewijzigd" if gewijzigd else "ongewijzigd"}]')
    return gewijzigd


def main():
    alleen_kijken = '--check' in sys.argv
    streng = '--ci' in sys.argv
    os.makedirs(BRON, exist_ok=True)
    sessie = requests.Session()
    iets_gewijzigd = False

    for domein, naam in DOMEINEN.items():
        gewijzigd, regels, links = haal_domein(sessie, domein, alleen_kijken)
        iets_gewijzigd = iets_gewijzigd or gewijzigd
        merk = 'gewijzigd' if gewijzigd else 'ongewijzigd'
        print(f'  {naam:32s} {regels:4d} middelen, {links:4d} detaillinks  [{merk}]')

    print('\nATC-bronnen:')
    for naam, zoeker in (('Farmatec add-on GS-lijst', gs_link), ('GIP add-on Zvw', gip_link)):
        iets_gewijzigd |= haal_atc_bron(sessie, naam, zoeker, alleen_kijken, streng)

    if alleen_kijken:
        print('\n--check: er is niets weggeschreven.')
    elif iets_gewijzigd:
        print('\nBrondata bijgewerkt. Herbouwen met: python3 bouw_site.py')
    else:
        print('\nGeen wijzigingen ten opzichte van de vorige keer.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
