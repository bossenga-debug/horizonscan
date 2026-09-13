#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bouwt horizonscan.html uit de opgehaalde brondata.

De acht domein-CSV's worden samengevoegd tot een doorzoekbare pagina met alle
middelen. De opmaak staat in template.html; hier gebeurt alleen het lezen,
opschonen en samenvoegen van de data.

Gebruik:  python3 bouw_site.py
"""
import csv
import difflib
import shutil
import subprocess
import tempfile
import json
import os
import re
import sys
import unicodedata
from datetime import date

import atc as atc_mod
import mutaties as mutaties_mod
from ophalen import DOMEINEN, slugify

HIER = os.path.dirname(os.path.abspath(__file__))
BRON = os.path.join(HIER, 'bron')
SITE = 'https://www.horizonscangeneesmiddelen.nl'
# Het add-on dashboard staat in een submap van preferentiebeleid, niet op
# /addon/: het FTP-account van deze hosting is vastgezet op die map. /addon/
# geeft een 404.
ADDON_DASHBOARD = 'https://medicatieadvies.nl/preferentiebeleid/addon/'
MAANDEN_HISTORIE = 24

# De kolomkoppen komen drie keer als "Additional remarks" en vier keer als
# "References" voor. Op naam lezen levert dan de verkeerde kolom op, dus we
# werken op positie. Deze nummers horen bij de export zoals die er nu uitziet;
# controleer_koppen() hieronder slaat alarm als de site de volgorde wijzigt.
KOLOM = {
    'stof': 0, 'domein': 1, 'reden': 2, 'indicatie': 3, 'uitgebreide_indicatie': 4,
    'huidige_merknaam': 5, 'merknaam': 7, 'fabrikant': 8, 'mechanisme': 10,
    'toediening': 11, 'vorm': 12, 'kader': 13, 'registratieroute': 17,
    'traject': 18, 'bijzonderheid': 19, 'atmp': 20, 'verwacht': 22, 'wees': 23,
    'fase': 24, 'prijsafspraak': 25, 'vergoeding': 26, 'sluis': 27,
    'huidige_behandeling': 29, 'waarde': 30, 'onderbouwing': 31,
    'behandelduur': 32, 'frequentie': 33, 'dosering': 34, 'volume': 37,
    'marktaandeel': 39, 'kosten': 42, 'totale_kosten': 45, 'id': 59,
}
VERWACHTE_KOPPEN = {
    0: 'Active substance', 1: 'Domain', 3: 'Main indication', 8: 'Manufacturer',
    22: 'Expected Registration', 24: 'Registration phase', 27: 'Medicine sluice',
    37: 'Patient volume', 42: 'Cost', 45: 'Total cost', 59: 'id',
}

# Alleen velden met een vaste, korte woordenlijst worden vertaald. Vrije tekst
# (indicaties, onderbouwing, werkingsmechanisme) blijft staan zoals de bron het
# schrijft -- daar zou vertalen betekenis kunnen verschuiven.
VERTAAL = {
    'domein': {
        'Oncology': 'Oncologie', 'Hematology': 'Hematologie',
        'Cardiovascular diseases': 'Cardiovasculaire aandoeningen',
        'Chronic immune diseases': 'Chronische immuunziekten',
        'Infectious diseases': 'Infectieziekten', 'Lung diseases': 'Longziekten',
        'Neurological disorders': 'Neurologische aandoeningen',
        'Metabolism and Endocrinology': 'Stofwisseling en endocrinologie',
    },
    'fase': {
        'Clinical trials': 'Klinisch onderzoek', 'Registered': 'Geregistreerd',
        'Registered and reimbursed': 'Geregistreerd en vergoed',
        'Registered and not reimbursed': 'Geregistreerd, niet vergoed',
        'No registration expected': 'Geen registratie verwacht',
        'Registration application pending': 'Registratieaanvraag loopt',
        'Positive CHMP opinion': 'Positieve CHMP-opinie',
        'Negative CHMP opinion': 'Negatieve CHMP-opinie',
        'Withdrawn': 'Ingetrokken', 'Unknown': 'Onbekend',
    },
    'sluis': {
        'Broadly excluded': 'Breed uitgezonderd', 'Included in the sluice': 'In de sluis',
        'Out of the sluice': 'Uit de sluis', 'Rejected': 'Afgewezen',
        'Sluice candidate': 'Sluiskandidaat',
    },
    'vergoeding': {
        'Reimbursed from the basic package': 'Vergoed uit basispakket',
        'Reimbursement request pending': 'Vergoedingsaanvraag loopt',
        'Excluded from the basic package': 'Uitgesloten van basispakket',
        'Advice Healthcare Institute': 'Advies Zorginstituut',
    },
    'kader': {
        'Intermural (MSZ)': 'Intramuraal (MSZ)', 'Extramural (GVS)': 'Extramuraal (GVS)',
        'Unknown': 'Onbekend',
    },
    'reden': {
        'New medicine (specialité)': 'Nieuw geneesmiddel', 'Indication extension': 'Indicatie-uitbreiding',
        'Generic': 'Generiek', 'Biosimilar': 'Biosimilar',
    },
    'waarde': {
        'No estimate possible yet': 'Nog geen inschatting mogelijk',
        'Possible added value': 'Mogelijk meerwaarde',
        'Possible equal value': 'Mogelijk gelijke waarde',
        'Possible added value for a subgroup': 'Mogelijk meerwaarde voor subgroep',
        'Possible benefit in ease of use': 'Mogelijk gemaksvoordeel',
        'Possibly no place in the treatment regimen': 'Mogelijk geen plaats in behandeling',
        'No judgement': 'Geen oordeel', 'No judgement yet': 'Nog geen oordeel',
    },
    'bijzonderheid': {
        'New therapeutical formulation': 'Nieuwe toedieningsvorm',
        'New medicine with Priority Medicines (PRIME)': 'PRIME-geneesmiddel',
        'Indication extension': 'Indicatie-uitbreiding', 'New medicine': 'Nieuw geneesmiddel',
        'Biosimilar': 'Biosimilar', 'Generic': 'Generiek', 'Unknown': 'Onbekend',
    },
    'registratieroute': {
        'Centralised (EMA)': 'Centraal (EMA)', 'Decentralised': 'Decentraal',
        'National (CBG)': 'Nationaal (CBG)', 'Unknown': 'Onbekend',
    },
    'traject': {
        'Normal trajectory': 'Normale procedure', 'Accelerated assessment': 'Versnelde beoordeling',
        'Conditional marketing authorisation': 'Voorwaardelijke handelsvergunning',
        'Informed consent application': 'Informed consent-aanvraag', 'Unknown': 'Onbekend',
    },
    'toediening': {
        'Oral': 'Oraal', 'Intravenous': 'Intraveneus', 'Subcutaneous': 'Subcutaan',
        'Inhalation': 'Inhalatie', 'Intramuscular': 'Intramusculair', 'Ocular': 'Oculair',
        'Intravitreal': 'Intravitreaal', 'Cutaneous': 'Cutaan', 'Nasal': 'Nasaal',
        'Local': 'Lokaal', 'Intravesical': 'Intravesicaal', 'Intrathecal': 'Intrathecaal',
        'Rectal': 'Rectaal', 'Sublingual': 'Sublinguaal', 'Vaginal': 'Vaginaal',
        'Transdermal': 'Transdermaal', 'Auricular': 'Auriculair',
        'Endocervical': 'Endocervicaal', 'Intra-arterial': 'Intra-arterieel',
        'Intra-articular': 'Intra-articulair', 'Intracardiac': 'Intracardiaal',
        'Intracavernous': 'Intracaverneus', 'Intracerebral': 'Intracerebraal',
        'Intradermal': 'Intradermaal', 'Intrader meal': 'Intradermaal',
        'Intralesional': 'Intralesionaal', 'Intraocular': 'Intraoculair',
        'Intraperitoneal': 'Intraperitoneaal', 'Intratumoral': 'Intratumoraal',
        'Intrauterine': 'Intra-uterien', 'Oromucosal': 'Oromucosaal',
        'Subconjunctival': 'Subconjunctivaal', 'Subretinal': 'Subretinaal',
        'Injection into the salivary glands': 'Injectie in de speekselklieren',
        'Unspecified or multiple': 'Niet gespecificeerd of meerdere',
        'Not applicable': 'Niet van toepassing', 'Unknown': 'Onbekend',
    },
    # De hoofdindicatie is ook een vaste lijst (85 groepen), geen vrije tekst.
    'indicatie': {
        'Lung cancer': 'Longkanker', 'Metabolic diseases': 'Stofwisselingsziekten',
        'Skin diseases': 'Huidaandoeningen', 'Other chronic immune diseases': 'Overige chronische immuunziekten',
        'Eye disorders': 'Oogaandoeningen',
        'Other non-oncological hematological medications': 'Overige niet-oncologische hematologie',
        'Oncology other': 'Oncologie overig', 'Bacterial infections': 'Bacteriële infecties',
        'Breast cancer': 'Borstkanker',
        'Other medication for cardiovascular diseases': 'Overige cardiovasculaire middelen',
        'Diabetes': 'Diabetes', 'Rheumatism': 'Reuma', 'Multiple Myeloma': 'Multipel myeloom',
        'Viral infections other': 'Virale infecties overig', 'Bowel diseases': 'Darmaandoeningen',
        'Neurological disorders other': 'Neurologische aandoeningen overig',
        'Other metabolism and Endocrinology': 'Stofwisseling en endocrinologie overig',
        "Aggressive non-Hodgkin's lymphoma": 'Agressief non-hodgkinlymfoom',
        'Muscular diseases other': 'Spierziekten overig', 'Prostate cancer': 'Prostaatkanker',
        'Bladder cancer': 'Blaaskanker', 'COVID-19': 'COVID-19',
        'Lung diseases other': 'Longziekten overig', 'Multiple sclerosis': 'Multiple sclerose',
        'Lipid-lowering medications': 'Lipidenverlagende middelen', 'Skin cancer': 'Huidkanker',
        'AML / MDS': 'AML / MDS', 'Hemostasis promoting medication': 'Hemostasebevorderende middelen',
        'Epilepsy': 'Epilepsie', 'Asthma': 'Astma', 'HIV': 'Hiv',
        'Cystic fibrosis': 'Cystische fibrose',
        "Indolent non-Hodgkin's lymphoma": 'Indolent non-hodgkinlymfoom',
        'Liver diseases': 'Leveraandoeningen', 'Kidney cancer': 'Nierkanker', 'Unknown': 'Onbekend',
        'Antithrombotic medications': 'Antitrombotica', 'Headache': 'Hoofdpijn',
        'Liver cancer': 'Leverkanker', 'Pain': 'Pijn', 'Stomach cancer': 'Maagkanker',
        'Sleep disorders': 'Slaapstoornissen', 'CLL': 'CLL', 'Duchenne': 'Duchenne', 'COPD': 'COPD',
        'Colon cancer': 'Darmkanker', 'Stem cell transplants': 'Stamceltransplantatie',
        'Brain cancer': 'Hersentumoren', 'Lung other': 'Longen overig',
        'Myeloproliferative disorders': 'Myeloproliferatieve aandoeningen',
        'Infectious diseases other': 'Infectieziekten overig',
        'Schizophrenia, psychosis, bipolar disorder': 'Schizofrenie, psychose, bipolaire stoornis',
        'Ovarian cancer': 'Eierstokkanker', 'Dementia': 'Dementie', 'ALS': 'ALS', 'ALL': 'ALL',
        'Fungal infections': 'Schimmelinfecties', 'Depression': 'Depressie',
        "Parkinson's": 'Parkinson', 'Hormonal disorders': 'Hormonale aandoeningen',
        'Head and neck cancer': 'Hoofd-halskanker', 'Neuroendocrine cancer': 'Neuro-endocriene tumoren',
        'Thyroid cancer': 'Schildklierkanker', 'Cervical cancer': 'Baarmoederhalskanker',
        'CML': 'CML', 'Graft versus Host': 'Graft-versus-hostziekte',
        'Other hematology': 'Hematologie overig', "Hodgkin's lymphoma": 'Hodgkinlymfoom',
        'SMA': 'SMA', 'ADHD': 'ADHD', 'Cardiovascular diseases': 'Cardiovasculaire aandoeningen',
        'Muscular diseases': 'Spierziekten', 'Pancreatic cancer': 'Alvleesklierkanker',
        'Schizophrenia, psychosis': 'Schizofrenie, psychose', 'Other psychiatry': 'Psychiatrie overig',
        'Tumour agnostic medication': 'Tumoragnostische middelen', 'Heart failure': 'Hartfalen',
        'Parasitic infections': 'Parasitaire infecties', 'Hearing disorders': 'Gehooraandoeningen',
        'Psychiatry': 'Psychiatrie', 'Hemostasis': 'Hemostase', 'Allergy': 'Allergie',
        'Bipolar disorder': 'Bipolaire stoornis', 'Mesothelioma': 'Mesothelioom',
    },
    'jaknee': {'Yes': 'Ja', 'No': 'Nee', 'Unknown': 'Onbekend'},
}


ONVERTAALD = set()


def vertaal(veld, waarde):
    # De bron gebruikt door elkaar een rechte en een gekrulde apostrof; zonder
    # gelijktrekken mist "Hodgkin's lymphoma" zijn vertaling.
    waarde = (waarde or '').strip().replace('\u2019', "'")
    lijst = VERTAAL.get(veld, {})
    if waarde and waarde not in lijst:
        # Nieuwe keuzemogelijkheid op de site: die valt onvertaald door, en dat
        # melden we aan het eind zodat de woordenlijst kan worden bijgewerkt.
        ONVERTAALD.add((veld, waarde))
    return lijst.get(waarde, waarde)


def controleer_koppen(koppen, bestand):
    """De kolomnummers hierboven zijn alleen geldig bij deze koppenvolgorde."""
    fout = [f'  kolom {i}: verwacht "{k}", gevonden "{koppen[i] if i < len(koppen) else "(ontbreekt)"}"'
            for i, k in VERWACHTE_KOPPEN.items() if i >= len(koppen) or koppen[i] != k]
    if fout:
        sys.exit(f'\nGESTOPT: de kolomvolgorde in {bestand} is veranderd.\n' + '\n'.join(fout) +
                 '\nPas KOLOM en VERWACHTE_KOPPEN in bouw_site.py aan de nieuwe export aan.')


def bedrag(tekst):
    """Leest '<  € 97,300.00' als 97300.0. De export gebruikt Engelse notatie:
    komma als duizendtal, punt als decimaal."""
    m = re.search(r'[\d,]+(?:\.\d+)?', (tekst or '').replace(' ', ' '))
    if not m:
        return None
    try:
        return float(m.group().replace(',', ''))
    except ValueError:
        return None


def volume_bovengrens(tekst):
    """Patientaantallen staan als '< 550' of '600 - 900'. Voor sorteren nemen we
    de hoogste waarde die er staat; het blijft een schatting uit de bron."""
    getallen = [int(g.replace('.', '')) for g in re.findall(r'\d[\d.]*', (tekst or ''))]
    return max(getallen) if getallen else None


def registratiemaand(tekst):
    """'10-2027' -> '2027-10', '2027' -> '2027-00' (jaar zonder maand).

    De sorteersleutel houdt jaar-zonder-maand apart, zodat die niet doet alsof
    het januari is. Alles wat geen jaartal bevat (zoals 'Unknown') telt niet mee
    in de tijdlijn.
    """
    tekst = (tekst or '').strip()
    m = re.fullmatch(r'(\d{2})-(\d{4})', tekst)
    if m:
        return f'{m.group(2)}-{m.group(1)}'
    m = re.fullmatch(r'(\d{4})', tekst)
    if m:
        return f'{m.group(1)}-00'
    return None


def koppel_slugs(regels, links):
    """Zoekt bij elke regel de juiste detailpagina.

    De export bevat wel een id, maar dat werkt niet als URL. De slugs staan
    alleen in de overzichtspagina, in de vorm <stofnaam> of <stofnaam>-<n>:
    een middel met vijf indicaties heeft vijf pagina's. Welke van die vijf bij
    welke regel hoort, moet uit de linktekst blijken -- die is per pagina of de
    stofnaam of de indicatietekst.

    Aanpak: eerst alle kandidaten per stofnaam, dan de beste combinatie eerst
    vastleggen en elke slug maar een keer vergeven.
    """
    per_stof = {}
    for slug in links:
        per_stof.setdefault(re.sub(r'-\d+$', '', slug), []).append(slug)

    def lijkt_op(a, b):
        return difflib.SequenceMatcher(None, (a or '')[:200].lower(),
                                       (b or '')[:200].lower()).ratio()

    kandidaten = []
    for i, regel in enumerate(regels):
        stof = regel['stof']
        for slug in per_stof.get(slugify(stof), []):
            tekst = links[slug]['tekst']
            score = max(lijkt_op(tekst, stof), lijkt_op(tekst, regel['uitgebreide_indicatie']))
            kandidaten.append((score, i, slug))

    kandidaten.sort(key=lambda k: -k[0])
    toegewezen, gebruikt = {}, set()
    for score, i, slug in kandidaten:
        if i not in toegewezen and slug not in gebruikt:
            toegewezen[i] = slug
            gebruikt.add(slug)
    return toegewezen


def lees_domein(domein):
    pad_csv = os.path.join(BRON, f'hs_{domein}.csv')
    pad_links = os.path.join(BRON, f'links_{domein}.json')
    if not os.path.exists(pad_csv):
        sys.exit(f'GESTOPT: {pad_csv} ontbreekt. Draai eerst: python3 ophalen.py')

    with open(pad_csv, encoding='utf-8-sig', newline='') as f:
        rijen = list(csv.reader(f, delimiter=';'))
    controleer_koppen(rijen[0], f'hs_{domein}.csv')

    with open(pad_links, encoding='utf-8') as f:
        links = json.load(f)

    regels = []
    for rij in rijen[1:]:
        def v(naam):
            i = KOLOM[naam]
            return (rij[i] if i < len(rij) else '').strip()

        regels.append({
            'stof': v('stof'),
            'merk': v('huidige_merknaam') or v('merknaam'),
            'fabrikant': v('fabrikant'),
            'domein': vertaal('domein', v('domein')),
            'indicatie': vertaal('indicatie', v('indicatie')),
            'uitgebreide_indicatie': v('uitgebreide_indicatie'),
            'reden': vertaal('reden', v('reden')),
            'mechanisme': v('mechanisme'),
            'toediening': vertaal('toediening', v('toediening')),
            'vorm': v('vorm'),
            'kader': vertaal('kader', v('kader')),
            'registratieroute': vertaal('registratieroute', v('registratieroute')),
            'traject': vertaal('traject', v('traject')),
            'bijzonderheid': vertaal('bijzonderheid', v('bijzonderheid')),
            'atmp': vertaal('jaknee', v('atmp')),
            'wees': vertaal('jaknee', v('wees')),
            'verwacht': v('verwacht'),
            'maand': registratiemaand(v('verwacht')),
            'fase': vertaal('fase', v('fase')),
            'prijsafspraak': v('prijsafspraak') == 'on',
            'vergoeding': vertaal('vergoeding', v('vergoeding')),
            'sluis': vertaal('sluis', v('sluis')),
            'waarde': vertaal('waarde', v('waarde')),
            'huidige_behandeling': v('huidige_behandeling'),
            'onderbouwing': v('onderbouwing'),
            'behandelduur': v('behandelduur'),
            'frequentie': v('frequentie'),
            'dosering': v('dosering'),
            'marktaandeel': v('marktaandeel'),
            'volume': v('volume'),
            'volume_n': volume_bovengrens(v('volume')),
            'kosten': v('kosten'),
            'kosten_n': bedrag(v('kosten')),
            'totale_kosten': v('totale_kosten'),
            'totale_kosten_n': bedrag(v('totale_kosten')),
            'id': v('id'),
        })

    toegewezen = koppel_slugs(regels, links)
    for i, regel in enumerate(regels):
        slug = toegewezen.get(i) or ''
        regel['slug'] = slug
        # Het versienummer van het Zorginstituut; mutaties.py leest hieraan af of
        # een kaart is aangepast, ook buiten de velden die we volgen.
        regel['versie'] = links[slug]['versie'] if slug else None
    return regels, len(toegewezen)


def controleer_script(pagina):
    """Weigert te schrijven als het paginascript een syntaxfout bevat.

    De data en de opmaak worden hier aan elkaar geplakt, en een fout in dat
    script levert een pagina op die opent en vervolgens leeg blijft -- precies
    het soort storing dat je pas maanden later opmerkt. `node --check` vangt dat
    af. Ontbreekt node, dan gaat het bouwen door zonder controle.
    """
    if not shutil.which('node'):
        return 'node ontbreekt — syntaxcontrole overgeslagen'
    m = re.search(r'<script>\n(const DATA.*?)\n</script>', pagina, re.S)
    if not m:
        sys.exit('GESTOPT: het paginascript is niet teruggevonden in de opgebouwde HTML.')
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(m.group(1))
        tijdelijk = f.name
    try:
        r = subprocess.run(['node', '--check', tijdelijk], capture_output=True, text=True)
    finally:
        os.unlink(tijdelijk)
    if r.returncode:
        regels = [l for l in r.stderr.splitlines() if l.strip()][:4]
        sys.exit('GESTOPT: het paginascript bevat een syntaxfout, er is niets geschreven:\n  '
                 + '\n  '.join(regels))
    return 'syntaxcontrole geslaagd'


def main():
    alles, gekoppeld = [], 0
    for domein, naam in DOMEINEN.items():
        regels, n = lees_domein(domein)
        alles += regels
        gekoppeld += n
        print(f'  {naam:32s} {len(regels):4d} middelen, {n:4d} met detaillink')

    alles.sort(key=lambda r: (r['stof'].lower(), r['indicatie'].lower()))

    # ATC-codes erbij. De Horizonscan geeft die niet; ze komen uit de add-on
    # GS-lijst en het GIP-bestand, zodat er een brug ontstaat naar het add-on
    # dashboard. Een middel zonder ATC heeft daar (nog) geen tegenhanger.
    atc_treffers, twijfel = atc_mod.koppel(sorted({r['stof'] for r in alles}))
    for regel in alles:
        treffer = atc_treffers.get(regel['stof'])
        regel['atc'] = treffer['atc'] if treffer else []
        regel['atc_via'] = treffer['via'] if treffer else ''
        regel['addon'] = bool(treffer and treffer['addon'])
    met_atc = sum(1 for r in alles if r['atc'])
    print(f"\nATC: {len(atc_treffers)} stoffen gekoppeld, {met_atc} van de {len(alles)} regels, "
          f"{sum(1 for r in alles if r['addon'])} nu al add-on")
    for stof, bijna in twijfel:
        print(f'  niet gekoppeld (te verschillend): {stof} ~ {bijna}')

    # Mutaties ten opzichte van de vorige run.
    peildatum = date.today().isoformat()
    verse, logboek, eerste_keer = mutaties_mod.bijwerken(
        alles, peildatum, schrijven='--geen-historie' not in sys.argv)
    if eerste_keer:
        print('\nMutaties: eerste meting, dus nog niets om mee te vergelijken. '
              'Vanaf de volgende run vult het overzicht zich.')
    else:
        t = mutaties_mod.samenvatting(verse)
        print(f"\nMutaties sinds de vorige run: {t['nieuw']} nieuw, {t['afgevoerd']} afgevoerd, "
              f"{t['gewijzigde_middelen']} gewijzigd ({t['gewijzigd']} veldwijzigingen), "
              f"{t['herzien']} herzien")

    jaar, maand = divmod((int(peildatum[:4]) * 12 + int(peildatum[5:7]) - 1) - MAANDEN_HISTORIE, 12)
    grens = f'{jaar:04d}-{maand + 1:02d}-01'

    pad_template = os.path.join(HIER, 'template.html')
    with open(pad_template, encoding='utf-8') as f:
        template = f.read()

    data = {
        'bijgewerkt': peildatum,
        'site': SITE,
        'addon_dashboard': ADDON_DASHBOARD,
        'middelen': alles,
        # Alleen de laatste twee jaar mee de pagina in: het logboek groeit door,
        # maar niemand scrolt drie jaar terug en het scheelt bestandsgrootte.
        'mutaties': [g for g in logboek['gebeurtenissen'] if g['datum'] >= grens],
        'peildata': logboek.get('peildata', []),
        'historie_start': logboek.get('gestart', peildatum),
    }
    uit = template.replace('/*DATA*/null/*DATA*/',
                           json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    if '/*DATA*/' in uit:
        sys.exit('GESTOPT: de datamarkering in template.html is niet vervangen.')

    melding = controleer_script(uit)

    pad_uit = os.path.join(HIER, 'horizonscan.html')
    with open(pad_uit, 'w', encoding='utf-8') as f:
        f.write(uit)
    print(f'\n{melding}')

    if ONVERTAALD:
        print('\nNieuwe waarden zonder vertaling (VERTAAL in bouw_site.py bijwerken):')
        for veld, waarde in sorted(ONVERTAALD):
            print(f'  {veld}: {waarde}')

    print(f'\n{len(alles)} middelen, {gekoppeld} met detaillink '
          f'({gekoppeld / len(alles) * 100:.0f}%)')
    print(f'Geschreven: {pad_uit} ({os.path.getsize(pad_uit) / 1024 / 1024:.1f} MB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
