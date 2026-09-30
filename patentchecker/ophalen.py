#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Haalt alle bronnen van de patentchecker op naar bron/.

Er zijn twee sets (zie middelen.SETS): 'addon' en 'gvs'. Wat ze delen (EMA,
Horizonscan, het patentoverzicht) wordt één keer opgehaald; wat per set
verschilt krijgt de setnaam in de bestandsnaam.

Algemene bronnen (één bestand per bron):
  gip_addon.csv         GIP add-on Zvw meerjaren -- welke middelen, wat ze kosten
  gip_farmacie.csv      GIP farmacie Zvw meerjaren -- idem voor de GVS-set
  addon-gs.zip          Farmatec add-on GS-lijst -- handelsvergunningen in NL
  preferentiebeleid.json  preferente middelen per ATC -- concurrentie in NL (GVS-set)
  ema_medicines.xlsx    EMA-medicijnentabel -- geregistreerde biosimilars/generieken
  ema_evaluatie.xlsx    EMA-lijst aanvragen in beoordeling -- wat eraan komt
  hs_<domein>.csv       Horizonscan -- biosimilars/generieken in de pijplijn
  hs_patent.pdf         Horizonscan-overzicht patentverloop -- ter vergelijking

Per middel en per set (pas daarna, want de selectie volgt uit GIP en de namen
uit EMA):
  rvo_<set>.json        SPC's uit het octrooiregister van RVO
  ctgov_<set>.json      biosimilarstudies uit ClinicalTrials.gov

Gebruik:  python3 ophalen.py [--set addon,gvs] [--check] [--ci] [--zonder-register]

  --set              welke sets; standaard allebei
  --check            alleen kijken of er iets veranderd is, niets wegschrijven
  --ci               hard stoppen zodra een bron niet gevonden wordt
  --zonder-register  RVO en ClinicalTrials.gov overslaan (de rest gaat snel;
                     handig bij werken aan de pagina)
"""
import datetime
import json
import os
import re
import sys
import time
from urllib.parse import urlencode

import requests

import bouw_site           # voor dezelfde beoordeling van 'nog beschermd'
import middelen
import rvo

HIER = os.path.dirname(os.path.abspath(__file__))
BRON = middelen.BRON
KOP = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                     'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36'}

HS = 'https://www.horizonscangeneesmiddelen.nl'
HS_DOMEINEN = ['oncologie', 'hematologie', 'cardiovasculaire-aandoeningen',
               'chronische-immuunziekten', 'infectieziekten', 'longziekten-algemeen',
               'neurologische-aandoeningen', 'stofwisseling-en-endocrinologie']
GS_PAGINA = ('https://www.farmatec.nl/prijsvorming/'
             'add-on-geneesmiddelen-sluismiddelen/actuele-publicaties')
GIP_PAGINA = 'https://www.zorgcijfersdatabank.nl/algemeen/open-data-gip'
PREFERENTIE = 'https://medicatieadvies.nl/preferentiebeleid/'
EMA_TABEL = 'https://www.ema.europa.eu/en/documents/report/medicines-output-medicines-report_en.xlsx'
EMA_EVAL = ('https://www.ema.europa.eu/en/documents/report/'
            'applications-new-human-medicines-under-evaluation-{maand}-{jaar}_en.xlsx')
CTGOV = 'https://clinicaltrials.gov/api/v2/studies'
MAANDEN = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
           'september', 'october', 'november', 'december']


def schrijf_als_gewijzigd(pad, inhoud, alleen_kijken=False):
    """Schrijft alleen bij wijziging; de vorige versie blijft als .vorige staan."""
    if isinstance(inhoud, str):
        inhoud = inhoud.encode('utf-8')
    oud = open(pad, 'rb').read() if os.path.exists(pad) else None
    if oud == inhoud:
        return False
    if alleen_kijken:
        return True
    if oud is not None:
        os.replace(pad, pad + '.vorige')
    with open(pad, 'wb') as f:
        f.write(inhoud)
    return True


def haal(sessie, url, pogingen=4, **kw):
    """GET met geduld: EMA geeft bij een paar snelle verzoeken HTTP 429."""
    for i in range(pogingen):
        r = sessie.get(url, headers=dict(KOP, **kw.pop('headers', {})), timeout=180, **kw)
        if r.status_code != 429:
            return r
        time.sleep(15 * (i + 1))
    return r


# ---------- links die elke maand verspringen ----------

def gip_link(sessie, linktekst):
    """De downloadsleutel wisselt per paginabezoek, dus die lezen we elke keer af."""
    pag = haal(sessie, GIP_PAGINA).text
    for m in re.finditer(r'<a[^>]*href="(/services/file/get\?key=[^"]+)"[^>]*>(.*?)</a>', pag, re.S):
        label = ' '.join(re.sub(r'<[^>]+>', '', m.group(2)).split())
        if re.search(linktekst, label, re.I):
            return 'https://www.zorgcijfersdatabank.nl' + m.group(1)


def gs_link(sessie):
    """De URL bevat de publicatiemaand; een vaste link verloopt na een maand."""
    pag = haal(sessie, GS_PAGINA).text
    doc = re.search(r'href="(/documenten/[^"]*excel-bestand-add-on-gs-[^"]*)"', pag)
    if doc:
        docpag = haal(sessie, 'https://www.farmatec.nl' + doc.group(1)).text
        zip_ = re.search(r'href="(https://[^"]+\.zip)"', docpag)
        return zip_.group(1) if zip_ else None


def hs_patent_link(sessie):
    """Nieuwste Horizonscan-update over patentverloop. De nieuwspagina zet de
    nieuwste bovenaan; oudere updates hebben een -0, -1, ... achter de slug."""
    pag = haal(sessie, HS + '/nieuws').text
    m = re.search(r'href="(/nieuws/[^"]*patentverloop[^"]*)"', pag)
    if not m:
        return None, None
    nieuws = haal(sessie, HS + m.group(1)).text
    pdf = re.search(r'href="(/services/file/get\?key=[^"]+)"', nieuws)
    return (HS + html_unescape(pdf.group(1)) if pdf else None), HS + m.group(1)


def html_unescape(s):
    import html
    return html.unescape(s)


def ema_evaluatie(sessie):
    """De lijst heet naar de maand; probeer deze maand en daarna terug."""
    vandaag = datetime.date.today()
    for terug in range(4):
        m = (vandaag.month - 1 - terug) % 12
        j = vandaag.year - (1 if vandaag.month - 1 - terug < 0 else 0)
        url = EMA_EVAL.format(maand=MAANDEN[m], jaar=j)
        r = haal(sessie, url)
        if r.status_code == 200 and r.content[:2] == b'PK':
            return r.content, f'{MAANDEN[m]} {j}'
    return None, None


def preferentiebeleid(sessie):
    """Preferente middelen per ATC-code, van onze eigen preferentiepagina.

    Voor GVS-middelen bestaat geen lijst zoals de add-on GS-lijst van Farmatec.
    Dat een middel preferent is aangewezen zegt wél iets: preferentiebeleid kan
    alleen bij een stof met meerdere leveranciers. De pagina heeft de data als
    JSON in de broncode staan; we bewaren er per ATC-code een samenvatting van.
    Lukt het niet, dan mist alleen die kolom."""
    pag = haal(sessie, PREFERENTIE).text
    merk = 'const DATA ='
    if merk not in pag:
        return None
    # Niet met een regex: de data bevat zelf accolades, dus laat de JSON-lezer
    # bepalen waar het object eindigt.
    data, _ = json.JSONDecoder().raw_decode(pag[pag.index(merk) + len(merk):].lstrip())
    per = {}
    for cluster in data.get('rijen', []):
        atc = (cluster.get('a') or '').upper()
        if not middelen.ATC5.match(atc):
            continue
        o = per.setdefault(atc, {'stof': cluster.get('s', ''), 'verzekeraars': set(),
                                 'fabrikanten': set(), 'clusters': 0})
        o['clusters'] += 1
        for key, keuzes in (cluster.get('ins') or {}).items():
            o['verzekeraars'].add(key)
            for k in keuzes:
                if k.get('f'):
                    o['fabrikanten'].add(k['f'])
    uit = {a: {'stof': o['stof'], 'verzekeraars': sorted(o['verzekeraars']),
               'fabrikanten': sorted(o['fabrikanten']), 'clusters': o['clusters']}
           for a, o in per.items()}
    return {'bron': PREFERENTIE, 'gegenereerd': data.get('gegenereerd', ''), 'atc': uit}


# ---------- algemene bronnen ----------

def algemene_bronnen(sessie, sets, alleen_kijken, streng):
    gewijzigd = False

    def meld(naam, data, bestand, extra=''):
        nonlocal gewijzigd
        g = schrijf_als_gewijzigd(os.path.join(BRON, bestand), data, alleen_kijken)
        gewijzigd |= g
        print(f'  {naam:34s} {len(data) / 1024:7.0f} kB  [{"gewijzigd" if g else "ongewijzigd"}]{extra}')

    def mislukt(naam, waarom):
        melding = f'  {naam:34s} {waarom}'
        if streng:
            sys.exit(melding + '\nEr is niets gepubliceerd.')
        print(melding + '  [overgeslagen; vorige versie blijft staan]')

    for s in sets:
        naam = f"GIP {'add-on' if s['naam'] == 'addon' else 'farmacie'} Zvw"
        url = gip_link(sessie, s['gip_linktekst'])
        if url:
            meld(naam, haal(sessie, url).content, s['gip'])
        else:
            mislukt(naam, 'geen link gevonden op de overzichtspagina')

    if any(s['nl_bron'] == 'farmatec' for s in sets):
        url = gs_link(sessie)
        if url:
            meld('Farmatec add-on GS-lijst', haal(sessie, url).content, 'addon-gs.zip')
        else:
            mislukt('Farmatec add-on GS-lijst', 'geen link gevonden')

    if any(s['nl_bron'] == 'preferentie' for s in sets):
        try:
            pref = preferentiebeleid(sessie)
        except Exception as e:
            pref = None
            print(f'  Preferentiebeleid: {e}')
        if pref:
            meld('Preferentiebeleid (eigen pagina)',
                 json.dumps(pref, ensure_ascii=False, indent=1, sort_keys=True).encode(),
                 'preferentiebeleid.json', f"  ({len(pref['atc'])} ATC-codes)")
        else:
            # Alleen deze kolom valt weg; de pagina blijft bruikbaar.
            print('  Preferentiebeleid (eigen pagina)   niet gelezen  [overgeslagen]')

    r = haal(sessie, EMA_TABEL)
    if r.status_code == 200 and r.content[:2] == b'PK':
        meld('EMA-medicijnentabel', r.content, 'ema_medicines.xlsx')
    else:
        mislukt('EMA-medicijnentabel', f'HTTP {r.status_code}')

    data, maand = ema_evaluatie(sessie)
    if data:
        meld('EMA aanvragen in beoordeling', data, 'ema_evaluatie.xlsx', f'  ({maand})')
    else:
        mislukt('EMA aanvragen in beoordeling', 'geen lijst van de laatste vier maanden')

    # Horizonscan: de export zit achter een sessiecookie. Zonder cookie komt er
    # HTTP 200 met nul bytes terug; eerst de domeinpagina ophalen en die als
    # referer meesturen (zelfde les als in de horizonscan-tool).
    for dom in HS_DOMEINEN:
        overzicht = HS + '/geneesmiddelen?' + urlencode({'hoofdniveau': 'domein', 'domein': dom})
        haal(sessie, overzicht)
        export = haal(sessie, HS + '/geneesmiddelen/export?' +
                      urlencode({'publicatiedatum': '', 'domein': dom}), headers={'Referer': overzicht})
        if export.status_code == 200 and export.content:
            meld(f'Horizonscan {dom}', export.content, f'hs_{dom}.csv')
        else:
            mislukt(f'Horizonscan {dom}', 'lege export')

    pdf, nieuws = hs_patent_link(sessie)
    r = haal(sessie, pdf, headers={'Referer': nieuws}) if pdf else None
    if r is not None and r.content[:4] == b'%PDF':
        meld('Horizonscan patentoverzicht', r.content, 'hs_patent.pdf')
        schrijf_als_gewijzigd(os.path.join(BRON, 'hs_patent.url'), nieuws, alleen_kijken)
    else:
        # Niet hard: dit is een vergelijkingsbron, de pagina werkt ook zonder.
        print('  Horizonscan patentoverzicht        niet gevonden  [overgeslagen]')
    return gewijzigd


# ---------- per middel ----------

def lijst_middelen(set_):
    gip, _ = middelen.lees_gip(os.path.join(BRON, set_['gip']))
    gekozen, _ = middelen.selectie(gip, set_)
    ema = middelen.lees_ema()
    inns = sorted({(r['International non-proprietary name (INN) / common name'] or '').strip()
                   for r in ema} - {''})
    uit = []
    for atc in gekozen:
        if middelen.groep_van(atc, gip[atc]['naam']):
            continue                           # productgroep: geen enkelvoudig SPC
        inn = middelen.inn_voor(atc, gip[atc]['naam'], inns)
        merken = sorted({r['Name of medicine'] for r in ema
                         if middelen.zelfde_stof(r['International non-proprietary name (INN) / common name'], inn)
                         and r['Biosimilar'] != 'Yes' and r['Generic'] != 'Yes'})
        # Zoektermen voor het register: bij een combinatie zoeken we op elke stof
        # apart, want het register kent geen ';'-namen. Filteren op de juiste
        # certificaten gebeurt in bouw_site.hoofdcertificaat().
        delen = middelen.componenten(inn)
        termen = delen if len(delen) > 1 else [inn]
        uit.append((atc, inn, merken, termen + middelen.RVO_EXTRA.get(atc, [])))
    return uit


def vervolgoctrooien(reg, alleen_kijken):
    """Status en einddatum van de vervolgoctrooien uit middelen.VERVOLGOCTROOIEN.

    Een handvol nummers, dus dit kost niets; en zo staat er nergens een datum in
    de code die stilletjes veroudert."""
    uit = {}
    for ep in middelen.vervolg_eps():
        try:
            gevonden = reg.octrooi(ep)
        except Exception as e:
            print(f'  {ep}: {e}  [overgeslagen]')
            continue
        if not gevonden:
            print(f'  {ep}: niet gevonden in het register  [overgeslagen]')
            continue
        uit[ep] = gevonden
        print(f"  {ep}  {gevonden['status'][:34]:34} tot {gevonden['einde'] or '—'}  "
              f"{gevonden['houder'][:28]}")
    if alleen_kijken or not uit:
        return False
    return schrijf_als_gewijzigd(os.path.join(BRON, 'vervolgoctrooien.json'),
                                 json.dumps(uit, ensure_ascii=False, indent=1, sort_keys=True))


def middel_info(atc, gip, inns, ema):
    """Naam, INN, merken en de eerste EU-vergunning van één ATC-code."""
    naam = gip[atc]['naam']
    inn = middelen.inn_voor(atc, naam, inns)
    eigen = [r for r in ema if middelen.zelfde_stof(
        r['International non-proprietary name (INN) / common name'], inn)]
    orig = [r for r in eigen if r['Biosimilar'] != 'Yes' and r['Generic'] != 'Yes'
            and r['Marketing authorisation date']]
    vergunning = sorted(bouw_site.ema_datum(r['Marketing authorisation date']) for r in orig)
    return {'naam': naam, 'inn': inn,
            'merken': sorted({r['Name of medicine'] for r in orig}),
            'vergunning': vergunning[0] if vergunning else ''}


def vul_aan(sessie, set_, alleen_kijken):
    """Loopt de kandidaten boven de drempel af en houdt over wat nog bescherming heeft.

    Preferent aangewezen middelen en middelen die eerder al uit patent bleken,
    slaan we over: daar valt niets meer te volgen en het scheelt elke maand
    honderden verzoeken aan het octrooiregister. Wie er nieuw bij komt wordt één
    keer opgezocht; blijkt de bescherming verlopen, dan wordt dat onthouden in
    historie/<set>/uitgesloten.json en schuift de lijst aan."""
    gip, _ = middelen.lees_gip(os.path.join(BRON, set_['gip']))
    jaar = sorted({j for o in gip.values() for j in o['kosten']})[-1]
    ema = middelen.lees_ema()
    inns = sorted({(r['International non-proprietary name (INN) / common name'] or '').strip()
                   for r in ema} - {''})
    stoffen = {middelen.sleutel(c)[:8] for naam in [o['naam'] for o in gip.values()] + inns
               for c in middelen.componenten(naam) if len(c) > 5}
    stoffen = {s for s in stoffen if len(s) == 8}
    pdf, _fout = bouw_site.lees_hs_overzicht()

    rvo_data = lees_bron(f"rvo_{set_['naam']}.json")
    ctgov_data = lees_bron(f"ctgov_{set_['naam']}.json")
    uitgesloten = middelen.lees_uitsluitingen(set_)
    preferent = middelen.preferente_atc()
    reg = rvo.Register()

    gekozen, nieuw, weg, fout = [], 0, 0, 0
    try:
      for atc in middelen.kandidaten(gip, jaar, overslaan=preferent | set(uitgesloten),
                                     drempel=set_['drempel']):
        info = middel_info(atc, gip, inns, ema)
        groep = middelen.groep_van(atc, info['naam'])
        if atc not in rvo_data and not groep:
            delen = middelen.componenten(info['inn'])
            termen = (delen if len(delen) > 1 else [info['inn']]) + middelen.RVO_EXTRA.get(atc, [])
            try:
                rvo_data[atc] = zoek_certificaten(reg, termen)
                ctgov_data[atc] = zoek_studies(sessie, info['inn'], info['merken'])
            except Exception as e:
                # Eén middel dat niet op te vragen is, mag de hele ronde niet
                # stilleggen: overslaan en de volgende keer opnieuw proberen.
                print(f'  {atc}: {e}  [overgeslagen]')
                rvo_data.pop(atc, None)
                fout += 1
                continue
            nieuw += 1
        b = bouw_site.bescherming(atc, info['naam'], info['inn'], info['merken'],
                                  rvo_data.get(atc, []),
                                  bouw_site.plus_jaren(info['vergunning'], 10) if info['vergunning'] else '',
                                  pdf, groep, stoffen)
        if not groep and bouw_site.nog_beschermd(b['toetreding']):
            gekozen.append(atc)
            print(f"  {len(gekozen):3d}. {atc:8s} {info['naam'][:34]:34s} "
                  f"€ {gip[atc]['kosten'].get(jaar, 0) / 1e6:5.1f} mln  tot {b['toetreding']}")
        else:
            weg += 1
            uitgesloten[atc] = {'naam': info['naam'], 'sinds': datetime.date.today().isoformat(),
                                'reden': 'productgroep' if groep else 'bescherming verlopen',
                                'toetreding': b['toetreding']}
    finally:
        # Ook bij een onderbreking bewaren wat er is opgehaald; het register
        # bevragen kost te veel tijd om weg te gooien.
        if not alleen_kijken:
            middelen.schrijf_uitsluitingen(set_, uitgesloten)
            schrijf_als_gewijzigd(os.path.join(BRON, f"rvo_{set_['naam']}.json"),
                                  json.dumps(rvo_data, ensure_ascii=False, indent=1, sort_keys=True))
            schrijf_als_gewijzigd(os.path.join(BRON, f"ctgov_{set_['naam']}.json"),
                                  json.dumps(ctgov_data, ensure_ascii=False, indent=1, sort_keys=True))
    print(f'  {len(gekozen)} middelen met bescherming, {nieuw} nieuw opgezocht, '
          f'{weg} afgevallen{f", {fout} overgeslagen door een fout" if fout else ""}; '
          f'{len(uitgesloten)} staan blijvend buiten de lijst')
    # Wegschrijven gebeurde al in het finally-blok hierboven.
    return not alleen_kijken and bool(nieuw or weg)


def lees_bron(naam):
    pad = os.path.join(BRON, naam)
    return json.load(open(pad, encoding='utf-8')) if os.path.exists(pad) else {}


def zoek_certificaten(reg, termen):
    gezien = {}
    for term in termen:
        for rec in reg.zoek(term):
            gezien.setdefault(rec['id'], rec)
        time.sleep(rvo.PAUZE)
    return list(gezien.values())


def register(lijst, set_, alleen_kijken):
    reg = rvo.Register()
    uit = {}
    for atc, inn, _, termen in lijst:
        gezien = {}
        for term in termen:
            for rec in reg.zoek(term):
                gezien.setdefault(rec['id'], rec)
            time.sleep(rvo.PAUZE)
        uit[atc] = list(gezien.values())
        actief = [r for r in uit[atc] if r.get('einde')]
        print(f'  {atc:8s} {inn[:30]:30s} {len(uit[atc]):2d} certificaten'
              f'{", laatste einde " + max(r["einde"] for r in actief) if actief else ""}')
    data = json.dumps(uit, ensure_ascii=False, indent=1, sort_keys=True)
    return schrijf_als_gewijzigd(os.path.join(BRON, f"rvo_{set_['naam']}.json"), data, alleen_kijken)


def ctgov(sessie, lijst, set_, alleen_kijken):
    """Biosimilarstudies per middel.

    Zoeken op 'biosimilar' levert ook studies op waarin een ándere biosimilar
    voorkomt: 'Faricimab vs Biosimilar Ranibizumab', 'Guselkumab after switching
    from ustekinumab'. Stof en 'biosimilar' ergens in dezelfde titel is dus niet
    genoeg; ze moeten bij elkaar staan (zie biosimilar_van)."""
    uit = {}
    for atc, inn, merken, _ in lijst:
        uit[atc] = zoek_studies(sessie, inn, merken)
        if uit[atc]:
            print(f'  {atc:8s} {inn[:30]:30s} {len(uit[atc]):2d} biosimilarstudies')
    data = json.dumps(uit, ensure_ascii=False, indent=1, sort_keys=True)
    return schrijf_als_gewijzigd(os.path.join(BRON, f"ctgov_{set_['naam']}.json"), data, alleen_kijken)


def zoek_studies(sessie, inn, merken):
    """Biosimilarstudies van één stof, met het filter uit biosimilar_van().

    De zoekterm wordt eerst ontdaan van alles wat geen letter is: een GIP-naam als
    "Bromocriptine (tabl. 2 5 mg" maakt van de haak een onafgesloten groep in de
    zoektaal van ClinicalTrials.gov, en dat geeft HTTP 400."""
    term = ' '.join(re.sub(r'[^A-Za-z ]+', ' ', middelen.componenten(inn)[0]).split())
    if len(term) < 4:
        return []
    naam = biosimilar_van(middelen.componenten(inn) + merken)
    studies, token = [], None
    for _ in range(5):
        p = {'query.intr': term, 'query.term': 'biosimilar', 'pageSize': 100,
             'fields': 'NCTId,BriefTitle,OfficialTitle,LeadSponsorName,Phase,'
                       'OverallStatus,StartDate,PrimaryCompletionDate'}
        if token:
            p['pageToken'] = token
        r = sessie.get(CTGOV, params=p, headers=KOP, timeout=60)
        r.raise_for_status()
        j = r.json()
        for s in j.get('studies', []):
            ps = s['protocolSection']
            idm = ps['identificationModule']
            titel = idm.get('briefTitle', '') + ' | ' + idm.get('officialTitle', '')
            if not naam.search(titel):
                continue
            studies.append({
                'nct': idm['nctId'],
                'titel': idm.get('briefTitle', ''),
                'sponsor': ps.get('sponsorCollaboratorsModule', {}).get('leadSponsor', {}).get('name', ''),
                'fase': '/'.join(ps.get('designModule', {}).get('phases', []) or []),
                'status': ps.get('statusModule', {}).get('overallStatus', ''),
                'start': ps.get('statusModule', {}).get('startDateStruct', {}).get('date', ''),
            })
        token = j.get('nextPageToken')
        if not token:
            break
        time.sleep(0.3)
    return sorted(studies, key=lambda s: s['start'], reverse=True)


def biosimilar_van(namen):
    """Regex die alleen raakt als de titel een biosimilar van déze stof noemt:

      'biosimilar (to/of) ranibizumab'          -> biosimilar vóór de naam
      'CKD-704 (Risankizumab Biosimilar)'       -> naam vóór biosimilar, hooguit één woord ertussen
                                                   (geen 'vs', 'to' of 'from': 'Faricimab vs Biosimilar
                                                   Ranibizumab' gaat over ranibizumab)
      'SB12 ... compared to Soliris', 'versus EU-Opdivo', 'M834 and Orencia'
                                                -> vergelijking met het origineel,
                                                   mits 'biosimilar' elders in de titel staat
    """
    n = '(?:' + '|'.join(re.escape(x) for x in namen if x) + ')'
    herkomst = r'(?:(?:eu|us|eu-/us|eu/us|eu-authori[sz]ed|us-licensed|reference)[-\s]*)*'
    return re.compile(
        rf'biosimilar\w*\s+(?:(?:to|of|version of)\s+)?{n}\b'
        rf'|\b{n}\W+(?:(?!(?:vs|versus|and|or|with|to|from|after)\b)\w+\s+)?biosimilar'
        rf'|(?=.*biosimilar).*\b(?:compar\w*(?:\s+(?:to|with))?|versus|vs\.?|and)\s+{herkomst}{n}\b',
        re.I)


def gekozen_sets():
    for i, arg in enumerate(sys.argv):
        if arg == '--set' and i + 1 < len(sys.argv):
            return [middelen.set_van(n) for n in sys.argv[i + 1].split(',')]
        if arg.startswith('--set='):
            return [middelen.set_van(n) for n in arg.split('=', 1)[1].split(',')]
    return list(middelen.SETS.values())


def main():
    alleen_kijken = '--check' in sys.argv
    streng = '--ci' in sys.argv
    sets = gekozen_sets()
    os.makedirs(BRON, exist_ok=True)
    sessie = requests.Session()

    print('Algemene bronnen:')
    gewijzigd = algemene_bronnen(sessie, sets, alleen_kijken, streng)

    if alleen_kijken:
        # Zonder weggeschreven GIP-bestand is de selectie niet te maken; --check
        # gaat dus alleen over de algemene bronnen.
        print('\n--check: het register en ClinicalTrials.gov zijn overgeslagen.')
    elif '--zonder-register' not in sys.argv:
        print('\nVervolgoctrooien (handmatige lijst, status uit het register):')
        try:
            gewijzigd |= vervolgoctrooien(rvo.Register(), alleen_kijken)
        except Exception as e:
            print(f'  mislukt: {e}  [vorige versie blijft staan]')
        for s in sets:
            if s.get('aanvullen'):
                print(f"\nOctrooiregister RVO, set {s['naam']}: middelen boven "
                      f"€ {s['drempel'] / 1e6:.0f} mln die nog bescherming hebben")
                try:
                    gewijzigd |= vul_aan(sessie, s, alleen_kijken)
                except Exception as e:
                    if streng:
                        sys.exit(f'Aanvullen set {s["naam"]}: {e}\nEr is niets gepubliceerd.')
                    print(f'  mislukt: {e}  [vorige versie blijft staan]')
                continue
            lijst = lijst_middelen(s)
            print(f"\nOctrooiregister RVO, set {s['naam']} ({len(lijst)} middelen):")
            try:
                gewijzigd |= register(lijst, s, alleen_kijken)
            except Exception as e:
                if streng:
                    sys.exit(f'RVO-register: {e}\nEr is niets gepubliceerd.')
                print(f'  mislukt: {e}  [vorige versie blijft staan]')
            print(f"\nClinicalTrials.gov, set {s['naam']}:")
            try:
                gewijzigd |= ctgov(sessie, lijst, s, alleen_kijken)
            except Exception as e:
                if streng:
                    sys.exit(f'ClinicalTrials.gov: {e}\nEr is niets gepubliceerd.')
                print(f'  mislukt: {e}  [vorige versie blijft staan]')

    if alleen_kijken:
        print('\n--check: er is niets weggeschreven.')
    elif gewijzigd:
        print('\nBrondata bijgewerkt. Herbouwen met: python3 bouw_site.py')
    else:
        print('\nGeen wijzigingen ten opzichte van de vorige keer.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
