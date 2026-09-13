#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Koppelt de werkzame stoffen uit de Horizonscan aan een ATC-code.

De Horizonscan geeft zelf geen ATC. Die komt hier uit twee bestanden die
`ophalen.py` binnenhaalt:

  bron/addon-gs.zip    Farmatec add-on GS-lijst -- het gezaghebbende antwoord op
                       de vraag of een middel nú een add-on geneesmiddel is
  bron/gip_addon.csv   GIP add-on Zvw -- levert extra stofnamen, en het is de
                       ATC-indeling waarop het add-on dashboard draait

Beide gebruiken Nederlandse spellingen ("BRENTUXIMAB VEDOTINE") waar de
Horizonscan de Engelse hanteert ("Brentuximab vedotin"), dus exact vergelijken
is niet genoeg.
"""
import csv
import difflib
import io
import json
import os
import re
import unicodedata
import zipfile
from collections import defaultdict

HIER = os.path.dirname(os.path.abspath(__file__))
BRON = os.path.join(HIER, 'bron')
CORRECTIES = os.path.join(HIER, 'atc_correcties.json')

ATC5 = re.compile(r'^[A-Z]\d{2}[A-Z]{2}\d{2}$')


def normaliseer(naam):
    """Stofnamen vergelijkbaar maken: accenten weg, haakjes weg, kleine letters.

    De toevoeging tussen haakjes is een zoutvorm ("Aumolertinib (mesilate)") en
    zegt niets over de ATC-code, dus die kan weg.
    """
    plat = unicodedata.normalize('NFKD', naam or '').encode('ascii', 'ignore').decode()
    plat = re.sub(r'\(.*?\)', ' ', plat.lower())
    return re.sub(r'[^a-z0-9]+', ' ', plat).strip()


def lees_gs_lijst():
    """{genormaliseerde stof: (codes, oorspronkelijke naam)} uit de Farmatec-lijst."""
    pad = os.path.join(BRON, 'addon-gs.zip')
    if not os.path.exists(pad):
        return {}
    from openpyxl import load_workbook
    with zipfile.ZipFile(pad) as z:
        blad = load_workbook(io.BytesIO(z.read(z.namelist()[0])),
                             read_only=True, data_only=True)
    ws = blad[blad.sheetnames[0]]
    rijen = ws.iter_rows(values_only=True)
    kop = list(next(rijen))
    i_atc, i_stof = kop.index('ATC_Code'), kop.index('WerkzameStof')
    uit = defaultdict(lambda: [set(), ''])
    for rij in rijen:
        code = (rij[i_atc] or '').strip()
        stof = (rij[i_stof] or '').strip()
        if not ATC5.match(code) or not stof:
            continue
        sleutel = normaliseer(stof)
        uit[sleutel][0].add(code)
        uit[sleutel][1] = stof
    return {k: (sorted(v[0]), v[1]) for k, v in uit.items()}


def lees_gip():
    """Zelfde vorm, uit het GIP-bestand. GIP vult korte ATC-codes aan met
    underscores; die horen niet bij de code."""
    pad = os.path.join(BRON, 'gip_addon.csv')
    if not os.path.exists(pad):
        return {}
    uit = defaultdict(lambda: [set(), ''])
    with open(pad, encoding='utf-8', errors='replace', newline='') as f:
        for rij in csv.reader(f, delimiter='#'):
            if len(rij) < 3:
                continue
            code = (rij[1] or '').strip().rstrip('_')
            naam = (rij[2] or '').strip()
            if not ATC5.match(code) or not naam:
                continue
            sleutel = normaliseer(naam)
            uit[sleutel][0].add(code)
            uit[sleutel][1] = naam
    return {k: (sorted(v[0]), v[1]) for k, v in uit.items()}


def lees_correcties():
    """Handmatige koppelingen, voor wat het automatisch matchen niet vindt.

    Vorm: {"stofnaam zoals in de Horizonscan": "L01FX05"} of null om een
    automatische koppeling juist te blokkeren.
    """
    if not os.path.exists(CORRECTIES):
        return {}
    with open(CORRECTIES, encoding='utf-8') as f:
        return {normaliseer(k): v for k, v in json.load(f).items()}


def spellingsvariant(a, b):
    """Mag `a` als schrijfwijze van `b` gelden?

    difflib alleen is te ruim: het koppelt deuruxolitinib aan ruxolitinib, twee
    verschillende middelen. Een spellingsvariant verschilt in de staart
    (vedotin/vedotine, abirateron/abiraterone), niet in de kop -- vandaar de eis
    dat het begin gelijk is en de lengte niet ver uiteenloopt.
    """
    return a[:5] == b[:5] and abs(len(a) - len(b)) <= 6


def koppel(stoffen):
    """Zoekt bij elke stofnaam een ATC-code.

    Geeft {stofnaam: {atc, via, bron, addon}} terug, alleen voor wat gevonden is.
    `via` is de naam waarop gekoppeld werd, zodat een twijfelachtige match in de
    pagina zichtbaar is in plaats van als feit te blijven staan.
    """
    gs, gip = lees_gs_lijst(), lees_gip()
    correcties = lees_correcties()
    alles = dict(gip)
    alles.update(gs)                      # de GS-lijst is leidend bij overlap
    sleutels = list(alles)

    uit, twijfel = {}, []
    for stof in stoffen:
        sleutel = normaliseer(stof)
        if sleutel in correcties:
            code = correcties[sleutel]
            if code:
                uit[stof] = {'atc': [code], 'via': 'handmatig',
                             'bron': 'correctie', 'addon': sleutel in gs}
            continue                       # null = bewust niet koppelen

        treffer = sleutel if sleutel in alles else None
        if not treffer:
            for kandidaat in difflib.get_close_matches(sleutel, sleutels, n=3, cutoff=0.88):
                if spellingsvariant(sleutel, kandidaat):
                    treffer = kandidaat
                    break
                twijfel.append((stof, alles[kandidaat][1]))
        if not treffer:
            continue

        codes, naam = alles[treffer]
        uit[stof] = {'atc': codes, 'via': naam,
                     'bron': 'GS' if treffer in gs else 'GIP',
                     'addon': treffer in gs}
    return uit, twijfel


def statistiek(gekoppeld, regels):
    addon = sum(1 for r in regels if (gekoppeld.get(r) or {}).get('addon'))
    return {'stoffen': len(gekoppeld),
            'regels': sum(1 for r in regels if r in gekoppeld),
            'regels_addon': addon}
