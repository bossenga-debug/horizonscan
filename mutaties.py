#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Houdt bij wat er tussen twee peildata in de Horizonscan verandert.

Er is geen archief op de site -- alleen PDF-uittreksels uit 2015 en 2016 -- dus
de historie wordt hier zelf opgebouwd. Bij elke run wordt de nieuwe stand
vergeleken met `historie/momentopname.json` en gaan de verschillen als losse
gebeurtenissen naar `historie/mutaties.json`. Beide horen in de repo: zonder de
momentopname is er de volgende maand niets om tegen af te zetten.

Twee signalen, die elkaars gat dekken:

  1. Het versienummer van het Zorginstituut zelf, uit de overzichtspagina. Loopt
     die op, dan is de kaart aangepast -- ook als het een veld betreft dat wij
     niet volgen.
  2. Vergelijking per veld. Die zegt wát er veranderd is.

Bewust niet gevolgd: de onderbouwing en de volledige indicatie. Die teksten
worden voortdurend bijgeschaafd; meenemen zou het logboek vullen met ruis. Loopt
daar iets in, dan blijft signaal 1 over en staat er "herzien".
"""
import json
import os
from datetime import date

HIER = os.path.dirname(os.path.abspath(__file__))
HISTORIE = os.path.join(HIER, 'historie')
MOMENTOPNAME = os.path.join(HISTORIE, 'momentopname.json')
LOGBOEK = os.path.join(HISTORIE, 'mutaties.json')

# Wat als mutatie telt. De volgorde bepaalt de volgorde in het overzicht.
VELDEN = [
    ('fase', 'Registratiefase'),
    ('sluis', 'Sluisstatus'),
    ('vergoeding', 'Vergoeding'),
    ('verwacht', 'Verwachte registratie'),
    ('waarde', 'Therapeutische waarde'),
    ('kosten', 'Kosten per patiënt'),
    ('totale_kosten', 'Totale kosten'),
    ('volume', 'Patiëntvolume'),
    ('kader', 'Bekostigingskader'),
    ('indicatie', 'Hoofdindicatie'),
    ('merk', 'Merknaam'),
]
# Meeverhuisd naar de momentopname zodat een afgevoerd middel nog te benoemen is.
KENMERKEN = ['stof', 'domein', 'slug', 'versie']


def momentopname(middelen):
    return {m['id']: {**{k: m.get(k, '') for k, _ in VELDEN},
                      **{k: m.get(k, '') for k in KENMERKEN}}
            for m in middelen if m.get('id')}


def lees(pad, standaard):
    if not os.path.exists(pad):
        return standaard
    with open(pad, encoding='utf-8') as f:
        return json.load(f)


def vergelijk(oud, nieuw, peildatum):
    """Levert de gebeurtenissen tussen twee momentopnamen."""
    uit = []

    def kenmerk(bron, mid):
        r = bron[mid]
        return {'id': mid, 'stof': r.get('stof', ''), 'domein': r.get('domein', ''),
                'slug': r.get('slug', '')}

    for mid in nieuw.keys() - oud.keys():
        uit.append({'datum': peildatum, 'soort': 'nieuw', **kenmerk(nieuw, mid),
                    'veld': '', 'van': '', 'naar': nieuw[mid].get('indicatie', '')})

    for mid in oud.keys() - nieuw.keys():
        uit.append({'datum': peildatum, 'soort': 'afgevoerd', **kenmerk(oud, mid),
                    'veld': '', 'van': oud[mid].get('indicatie', ''), 'naar': ''})

    for mid in nieuw.keys() & oud.keys():
        veranderd = False
        for veld, label in VELDEN:
            was, wordt = (oud[mid].get(veld) or ''), (nieuw[mid].get(veld) or '')
            if was != wordt:
                veranderd = True
                uit.append({'datum': peildatum, 'soort': 'gewijzigd', **kenmerk(nieuw, mid),
                            'veld': label, 'van': was, 'naar': wordt})
        # Versie opgelopen zonder dat een gevolgd veld anders is: dan is er iets
        # veranderd in tekst die wij niet bijhouden. Dat is het melden waard,
        # maar we doen niet alsof we weten wát.
        oude_versie, nieuwe_versie = oud[mid].get('versie'), nieuw[mid].get('versie')
        if not veranderd and oude_versie and nieuwe_versie and nieuwe_versie > oude_versie:
            uit.append({'datum': peildatum, 'soort': 'herzien', **kenmerk(nieuw, mid),
                        'veld': '', 'van': f'versie {oude_versie}',
                        'naar': f'versie {nieuwe_versie}'})
    return uit


def bijwerken(middelen, peildatum=None, schrijven=True):
    """Vergelijkt met de vorige run en werkt momentopname en logboek bij.

    Geeft (gebeurtenissen van deze run, het hele logboek, eerste_keer) terug.
    """
    peildatum = peildatum or date.today().isoformat()
    nu = momentopname(middelen)
    vorig = lees(MOMENTOPNAME, None)
    logboek = lees(LOGBOEK, {'gestart': peildatum, 'peildata': [], 'gebeurtenissen': []})

    eerste_keer = vorig is None
    nieuw = [] if eerste_keer else vergelijk(vorig.get('middelen', {}), nu, peildatum)

    if schrijven:
        os.makedirs(HISTORIE, exist_ok=True)
        if nieuw or eerste_keer:
            # Een peildatum die al in het logboek staat, wordt vervangen. Anders
            # verdubbelt alles zodra een run op dezelfde dag wordt overgedaan.
            logboek['gebeurtenissen'] = [g for g in logboek['gebeurtenissen']
                                         if g['datum'] != peildatum] + nieuw
            logboek['peildata'] = sorted(set(logboek.get('peildata', []) + [peildatum]))
            with open(LOGBOEK, 'w', encoding='utf-8') as f:
                json.dump(logboek, f, ensure_ascii=False, indent=1, sort_keys=True)
        with open(MOMENTOPNAME, 'w', encoding='utf-8') as f:
            json.dump({'datum': peildatum, 'middelen': nu}, f,
                      ensure_ascii=False, indent=1, sort_keys=True)

    return nieuw, logboek, eerste_keer


def samenvatting(gebeurtenissen):
    uit = {'nieuw': 0, 'afgevoerd': 0, 'gewijzigd': 0, 'herzien': 0}
    middelen = {'gewijzigd': set()}
    for g in gebeurtenissen:
        uit[g['soort']] = uit.get(g['soort'], 0) + 1
        if g['soort'] == 'gewijzigd':
            middelen['gewijzigd'].add(g['id'])
    uit['gewijzigde_middelen'] = len(middelen['gewijzigd'])
    return uit
