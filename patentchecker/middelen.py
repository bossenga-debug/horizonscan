# -*- coding: utf-8 -*-
"""Welke middelen de patentchecker volgt, en onder welke naam.

Gedeeld door ophalen.py (die per middel het octrooiregister en ClinicalTrials.gov
bevraagt) en bouw_site.py (die alles samenvoegt). Zo kan de selectie nooit
tussen die twee uit elkaar lopen.

Er zijn twee sets, met dezelfde code en hetzelfde sjabloon (zie SETS):

  addon  add-on geneesmiddelen (intramuraal), elk middel boven DREMPEL in een
         van de twee laatste GIP-jaren. Twee jaren en niet één, omdat het
         laatste jaar voorlopig is: een middel dat in het ene jaar € 11 mln
         kostte en in het halfvolle laatste jaar € 9 mln, hoort er gewoon bij.
  gvs    extramurale geneesmiddelen (GVS): boven DREMPEL_GVS in het laatste
         jaar, maar alleen middelen waar nog iets te volgen valt -- niet
         preferent aangewezen en de bescherming nog niet verlopen. Zonder die
         twee filters zou de lijst vooral uit oude generieken bestaan, want dat
         is het grootste deel van de extramurale farmacie.
"""
import os
import re
import unicodedata
import zipfile

HIER = os.path.dirname(os.path.abspath(__file__))
BRON = os.path.join(HIER, 'bron')

DREMPEL = 10_000_000      # add-on: kostendrempel per jaar
DREMPEL_GVS = 1_000_000   # GVS: lager, want die lijst is al gezeefd op bescherming

# Per set: waar de cijfers vandaan komen, hoe geselecteerd wordt en hoe de
# pagina heet. De rest van de code is voor beide sets gelijk.
SETS = {
    'addon': {
        'naam': 'addon',
        'titel': 'Patentchecker dure add-on geneesmiddelen',
        'kop': 'add-on geneesmiddelen',
        'gip': 'gip_addon.csv',
        'gip_linktekst': r'GIP\s+Addon\s+Zvw\s+meerjaren',
        'selectie': 'drempel',
        'drempel': DREMPEL,
        'jaren': 2,                 # het laatste jaar is voorlopig, dus telt het jaar ervoor mee
        'pagina': 'patentchecker.html',
        'publicatie': 'index.html',
        'historie': 'historie',
        'nl_bron': 'farmatec',      # handelsvergunningen op de add-on GS-lijst
    },
    'gvs': {
        'naam': 'gvs',
        'titel': 'Patentchecker dure GVS-geneesmiddelen',
        'kop': 'nog beschermde extramurale geneesmiddelen (GVS)',
        'gip': 'gip_farmacie.csv',
        'gip_linktekst': r'GIP\s+Farmacie\s+Zvw\s+meerjaren',
        'selectie': 'drempel',
        'drempel': DREMPEL_GVS,
        'jaren': 1,                 # alleen het laatste jaar; dat is hier compleet
        'pagina': 'patentchecker_gvs.html',
        'publicatie': 'gvs.html',
        'historie': os.path.join('historie', 'gvs'),
        'nl_bron': 'preferentie',   # preferentiebeleid van de zorgverzekeraars
        # Alleen middelen waar nog iets te volgen valt: preferent aangewezen of
        # uit patent gaat eruit, en de lijst schuift aan tot TOP. Zo wordt het
        # octrooiregister niet elke maand bevraagd over middelen waarvan de
        # bescherming allang verlopen is.
        'aanvullen': True,
    },
}


def set_van(naam):
    if naam not in SETS:
        raise SystemExit(f'Onbekende set "{naam}"; kies uit: {", ".join(SETS)}')
    return SETS[naam]

# ATC-codes die geen enkelvoudige werkzame stof zijn maar een productgroep. Een
# SPC hoort bij één stof, dus hier valt geen patentdatum te geven. Ze blijven
# wél in het overzicht staan: ze horen bij de duurste middelen, en een lege
# plek zonder uitleg zou lijken op een fout.
GROEPEN = {
    'J06BA02': 'Plasmaproduct: meerdere merken van verschillende donorpools; '
               'geen SPC en geen biosimilarroute.',
    'B02BD02': 'Stollingsfactoren VIII: een groep van recombinante en plasmaproducten, '
               'elk met een eigen INN. Ook de Horizonscan laat stollingsfactoren buiten '
               'het patentoverzicht.',
    'B02BD04': 'Stollingsfactoren IX: een groep van recombinante en plasmaproducten, '
               'elk met een eigen INN. Ook de Horizonscan laat stollingsfactoren buiten '
               'het patentoverzicht.',
    'M03AX01': 'Botulinetoxine: meerdere producten (type A en B) die niet onderling '
               'uitwisselbaar zijn; de oorspronkelijke octrooien zijn lang verlopen.',
}

# De Engelse INN waaronder het middel bij EMA en in het octrooiregister staat,
# waar die niet vanzelf uit de GIP-naam volgt (zie inn_voor()).
INN = {
    'L01XL03': 'axicabtagene ciloleucel',
    'H01AC01': 'somatropin',
    'L02BX03': 'abiraterone',
}

# Extra zoektermen voor het octrooiregister. Het register zoekt in de titel van
# het certificaat, en die is soms een merknaam of een chemische naam in plaats
# van de INN. Wat hier niet staat en toch niet gevonden wordt, valt terug op de
# datum uit de Horizonscan-PDF -- dat is op de pagina te zien.
RVO_EXTRA = {
    'L01EB04': ['Tagrisso'],
    'L01EC02': ['Tafinlar'],
    'L01XL03': ['Yescarta', 'axicabtagen'],
    'L04AB02': ['Remicade'],
    'M09AX09': ['Zolgensma'],
}


def sleutel(tekst):
    """Vergelijkingssleutel die Nederlandse en Engelse stofnamen gelijk maakt.

    GIP schrijft 'Darbepoetine alfa' en 'Onasemnogeen', EMA 'darbepoetin alfa'
    en 'onasemnogene'. Per woord de slot-e weg en ee -> e maakt die gelijk,
    zonder te gaan gokken: twee verschillende stoffen krijgen zo nooit dezelfde
    sleutel (anders dan bij fuzzy matchen, waar deuruxolitinib bij ruxolitinib
    uitkomt).
    """
    plat = unicodedata.normalize('NFKD', tekst or '').encode('ascii', 'ignore').decode().lower()
    woorden = re.findall(r'[a-z0-9]+', plat)
    return ' '.join(re.sub(r'e$', '', w.replace('ee', 'e')) for w in woorden)


# Zoutvormen die in de INN-kolom van EMA achter de stofnaam kunnen staan.
# 'trastuzumab emtansine' is géén zoutvorm van trastuzumab -- daarom een lijst en
# geen 'alles wat met de naam begint'.
ZOUTEN = {'hydrochloride', 'dihydrochloride', 'mesylate', 'mesilate', 'phosphate',
          'hemifumarate', 'fumarate', 'maleate', 'acetate', 'citrate', 'tartrate',
          'besilate', 'sulfate', 'sodium', 'potassium', 'calcium', 'tosylate',
          'succinate', 'hydrobromide', 'monohydrate', 'isethionate', 'etexilate'}


def zelfde_stof(ema_inn, inn):
    a, b = (ema_inn or '').lower().strip(), inn.lower().strip()
    if a == b:
        return True
    if a.startswith(b + ' '):
        rest = a[len(b) + 1:].split()
        return bool(rest) and all(w in ZOUTEN for w in rest)
    return False


ATC5 = re.compile(r'^[A-Z]\d{2}[A-Z]{2}\d{2}$')


def lees_gip(pad):
    """GIP-meerjarenbestand (add-on of farmacie) ->
    {atc: {'naam', 'kosten': {jaar: €}, 'gebruikers': {...}}}

    Beide bestanden hebben dezelfde eerste kolommen. Het bestand gebruikt '#' als
    scheidingsteken en zet een '*' achter voorlopige jaren; die ster bewaren we
    apart. Regels zonder geldige ATC-5 (het farmaciebestand heeft een regel
    'XXXXXXX Geen ATC-code' van ruim € 100 mln) vallen af: zonder stof valt er
    niets over octrooien te zeggen."""
    uit, voorlopig = {}, set()
    with open(pad, encoding='utf-8-sig') as f:
        kop = [k.strip() for k in f.readline().split('#')]
        if kop[:4] != ['jaar', 'atclaatst', 'atclaatst_naam_tekst', 'vergoeding']:
            raise RuntimeError(f'GIP-bestand heeft een onverwachte kop: {kop}')
        for regel in f:
            v = [x.strip() for x in regel.split('#')]
            if len(v) < 5 or not v[1]:
                continue
            jaar = v[0].rstrip('*')
            if v[0].endswith('*'):
                voorlopig.add(jaar)
            if not ATC5.match(v[1].upper()):
                continue
            o = uit.setdefault(v[1], {'naam': ' '.join(v[2].split()), 'kosten': {}, 'gebruikers': {}})
            o['kosten'][jaar] = float(v[3] or 0)
            o['gebruikers'][jaar] = int(float(v[4] or 0))
    return uit, sorted(voorlopig)


def kandidaten(gip, jaar, overslaan=(), drempel=0):
    """Alle ATC-codes op kosten van dat jaar, duurste eerst, zonder de overgeslagen
    en zonder wat onder de drempel valt."""
    gesorteerd = sorted(gip, key=lambda a: -gip[a]['kosten'].get(jaar, 0))
    return [a for a in gesorteerd if a not in overslaan
            and gip[a]['kosten'].get(jaar, 0) >= drempel]


def selectie(gip, set_=None, overslaan=()):
    """De middelen van een set, duurste eerst, plus de jaren in het bestand.

    `overslaan` is voor de GVS-set: middelen die preferent zijn aangewezen of
    waarvan de bescherming al verlopen is, doen niet mee. Daar valt niets meer
    te volgen, en dan is het zonde om er elke maand het octrooiregister voor te
    bevragen. De lijst schuift aan tot er weer TOP middelen in staan."""
    set_ = set_ or SETS['addon']
    jaren = sorted({j for o in gip.values() for j in o['kosten']})
    laatste = jaren[-set_.get('jaren', 2):]
    drempel = set_.get('drempel', DREMPEL)
    sleutel = lambda a: -max(gip[a]['kosten'].get(j, 0) for j in laatste)
    gekozen = [a for a, o in gip.items() if a not in overslaan
               and max(o['kosten'].get(j, 0) for j in laatste) >= drempel]
    return sorted(gekozen, key=sleutel), jaren


def groep_van(atc, naam):
    """Productgroepen: een ATC-code die geen enkelvoudige stof is. Naast de vaste
    lijst herkennen we ze aan de GIP-naam: 'Macrogol combinatiepreparaten' en
    'Fluticason combinatiepreparaten' zijn verzamelingen van producten."""
    if atc in GROEPEN:
        return GROEPEN[atc]
    if re.search(r'combinatiepreparaten', naam, re.I):
        return ('Verzamelcode voor combinatiepreparaten: meerdere samenstellingen onder '
                'één ATC-code, elk met een eigen registratie. Eén SPC-datum bestaat hier niet.')
    return ''


def lees_ema(pad=None):
    """EMA-medicijnentabel -> lijst dicts (alleen humane middelen).

    De kop staat niet op de eerste regel (er gaan een paar regels met
    exportinformatie aan vooraf), dus we zoeken hem op."""
    import openpyxl
    pad = pad or os.path.join(BRON, 'ema_medicines.xlsx')
    rijen = openpyxl.load_workbook(pad, read_only=True).active.iter_rows(values_only=True)
    kop = None
    uit = []
    for r in rijen:
        if kop is None:
            if r and r[0] == 'Category':
                kop = [str(k or '').replace('\n', ' ').strip() for k in r]
                for nodig in ('Name of medicine', 'Medicine status', 'Biosimilar', 'Generic',
                              'International non-proprietary name (INN) / common name',
                              'Marketing authorisation date', 'Orphan medicine'):
                    if nodig not in kop:
                        raise RuntimeError(f'EMA-tabel: kolom "{nodig}" ontbreekt')
            continue
        if r and r[0] == 'Human':
            uit.append(dict(zip(kop, r)))
    if kop is None:
        raise RuntimeError('EMA-tabel: kopregel niet gevonden')
    return uit


def componenten(naam):
    """De losse stoffen in een GIP-naam: 'Ivacaftor met tezacaftor en elexacaftor'
    -> drie namen. Combinaties schrijft GIP met 'met' en 'en', EMA met schuine
    strepen of komma's."""
    delen = re.split(r'\s+met\s+|\s+en\s+|\s*[/,;]\s*', naam, flags=re.I)
    return [d.strip() for d in delen if len(d.strip()) > 3]


def inn_voor(atc, gip_naam, ema_inns):
    """De Engelse INN bij een GIP-regel: handmatig, anders via de sleutel.

    Voor combinatiepreparaten valt de hele naam niet samen ('Emtricitabine
    tenofoviralafenamide darunavir cobicistat' tegenover
    'darunavir / cobicistat / emtricitabine / tenofovir alafenamide'), maar de
    verzameling stofnamen wel. Daarom als tweede stap op die verzameling
    vergelijken -- nog steeds exact per stof, dus zonder te gokken."""
    if atc in INN:
        return INN[atc]
    k = sleutel(gip_naam)
    for inn in ema_inns:
        if sleutel(inn) == k:
            return inn
    eigen = {sleutel(c) for c in componenten(gip_naam)}
    if len(eigen) > 1:
        for inn in ema_inns:
            if {sleutel(c) for c in componenten(inn)} == eigen:
                return inn
        # Ook met de losse woorden: GIP plakt soms twee stofnamen aan elkaar.
        woorden = set(sleutel(gip_naam).split())
        for inn in ema_inns:
            k2 = set(sleutel(inn).split())
            if len(k2) > 1 and k2 == woorden:
                return inn
    return gip_naam.lower()


def lees_uitsluitingen(set_):
    """Middelen die niet meer gevolgd worden, met de reden. Staat in historie/,
    dus hij gaat mee in git en blijft tussen runs bestaan."""
    pad = os.path.join(HIER, set_['historie'], 'uitgesloten.json')
    if not os.path.exists(pad):
        return {}
    import json
    with open(pad, encoding='utf-8') as f:
        return json.load(f)


def schrijf_uitsluitingen(set_, uitgesloten):
    import json
    map_ = os.path.join(HIER, set_['historie'])
    os.makedirs(map_, exist_ok=True)
    with open(os.path.join(map_, 'uitgesloten.json'), 'w', encoding='utf-8') as f:
        json.dump(uitgesloten, f, ensure_ascii=False, indent=1, sort_keys=True)


def preferente_atc(bron_json=None):
    """ATC-codes die minstens één verzekeraar preferent aanwijst."""
    import json
    pad = bron_json or os.path.join(BRON, 'preferentiebeleid.json')
    if not os.path.exists(pad):
        return set()
    with open(pad, encoding='utf-8') as f:
        return {a for a, o in json.load(f).get('atc', {}).items() if o.get('verzekeraars')}


def lees_gs(pad=None):
    """Farmatec add-on GS-lijst -> {atc: {'reg': {EU-nummer: fabrikant}, 'artikelen': [...]}}

    Zelfde lezing als het add-on dashboard: voor concurrentie tellen de
    handelsvergunningen, niet de kolom fabrikant (die telt parallelimport mee)."""
    import openpyxl
    pad = pad or os.path.join(BRON, 'addon-gs.zip')
    zf = zipfile.ZipFile(pad)
    naam = next(n for n in zf.namelist() if n.lower().endswith('.xlsx'))
    maand = re.search(r'(januari|februari|maart|april|mei|juni|juli|augustus|september|'
                      r'oktober|november|december)[-_ ]?(\d{4})', naam, re.I)
    it = openpyxl.load_workbook(zf.open(naam), read_only=True, data_only=True).active.iter_rows(values_only=True)
    next(it)
    uit = {}
    for r in it:
        if r[0] is None:
            continue
        zi, art, code, stof, regnr, fab = r[:6]
        code = (code or '').replace('_', '').strip()
        if not code:
            continue
        o = uit.setdefault(code, {'reg': {}, 'artikelen': set()})
        m = re.match(r'(EU/\d+/\d+/\d+)', str(regnr or '').strip())
        reg = m.group(1) if m else str(regnr or '').strip()[:14]
        if reg:
            o['reg'].setdefault(reg, str(fab or '').strip())
        merk = re.split(r'\s+\d', str(art or '').strip())[0].strip().title()
        if merk:
            o['artikelen'].add(merk)
    versie = maand.group(0).replace('-', ' ').replace('_', ' ') if maand else ''
    return {a: {'reg': o['reg'], 'artikelen': sorted(o['artikelen'])} for a, o in uit.items()}, versie
