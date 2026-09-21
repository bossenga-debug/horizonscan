#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voegt de bronnen samen tot één zelfstandige pagina: patentchecker.html.

Per middel boven de drempel (zie middelen.py):
  - het bepalende SPC uit het octrooiregister, met alle andere certificaten erbij
  - de datum uit het Horizonscan-overzicht, en of die afwijkt
  - marktbescherming: 10 jaar na de eerste EU-handelsvergunning
  - geregistreerde en aangevraagde biosimilars/generieken (EMA)
  - biosimilars in de pijplijn (Horizonscan) en in studies (ClinicalTrials.gov)
  - handelsvergunningen op de Nederlandse add-on-lijst (Farmatec)

Daarna vergelijkt het de uitkomst met de vorige momentopname in historie/ en
schrijft wat er veranderd is in het logboek.

Gebruik:  python3 bouw_site.py [--geen-historie]
"""
import csv
import datetime
import glob
import io
import json
import os
import re
import sys

import middelen
import hs_pdf

HIER = middelen.HIER
BRON = middelen.BRON
HISTORIE = os.path.join(HIER, 'historie')
UIT = os.path.join(HIER, 'patentchecker.html')
VANDAAG = datetime.date.today()

ADDON_DASHBOARD = 'https://medicatieadvies.nl/addon/'
HORIZONSCAN_SITE = 'https://medicatieadvies.nl/horizonscan/'

# Namen in de Horizonscan-PDF die niet via de gewone sleutel te koppelen zijn.
PDF_NAAM = {'ocrilizumab': 'L04AG08'}

# Hoe lang "loopt binnenkort af" is.
BINNENKORT_MAANDEN = 36


def lees_json(naam, standaard):
    pad = os.path.join(BRON, naam)
    return json.load(open(pad, encoding='utf-8')) if os.path.exists(pad) else standaard


def plus_jaren(iso, jaren):
    d = datetime.date.fromisoformat(iso)
    try:
        return d.replace(year=d.year + jaren).isoformat()
    except ValueError:                         # 29 februari
        return d.replace(year=d.year + jaren, day=28).isoformat()


def ema_datum(v):
    if isinstance(v, datetime.datetime):
        return v.date().isoformat()
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})', str(v or ''))
    return f'{m.group(3)}-{m.group(2)}-{m.group(1)}' if m else ''


# ---------- octrooiregister ----------

def klasse(status):
    s = status.lower()
    if 'in force' in s or 'granted' in s:
        return 'actief'
    if s.startswith(('expired', 'lapsed', 'invalid', 'renounc', 'revoked', 'nullif')):
        return 'verlopen'
    if 'pending' in s or 'filed' in s:
        return 'aanvraag'
    return 'afgewezen'                         # refused, withdrawn


VERVOLG = re.compile(r'^(of|or|desgewenst|een|a|in|inclusief|including|dan wel|'
                     r'en (zouten|farmaceutisch)|and (salts|pharmaceutically))\b', re.I)


def hoofdcertificaat(titel, namen, merken):
    """Gaat dit certificaat over de stof zelf, en niet over een combinatie of
    een afgeleide? 'Ruxolitinib of een farmaceutisch aanvaardbaar zout' en
    'Osimertinib (Tagrisso)' wel; 'Trastuzumab emtansine' niet (voor
    trastuzumab), 'daratumumab, bortezomib en dexamethason' ook niet."""
    t = ' '.join(titel.lower().split())
    for naam in namen:
        n = naam.lower()
        if not t.startswith(n):
            continue
        rest = re.sub(r'^[\s,.;:()]+', '', t[len(n):])
        if not rest or VERVOLG.match(rest) or rest.startswith(tuple(m.lower() for m in merken)):
            return True
    return False


def kies_spc(certs, namen, merken):
    """Het bepalende certificaat: het actieve met de laatste einddatum; anders een
    lopende aanvraag; anders het laatst verlopen certificaat."""
    for c in certs:
        c['klasse'] = klasse(c['status'])
        # Bij een vervallen of ongeldig certificaat is de einddatum in het register
        # de datum waarop het zou zijn afgelopen, niet waarop het afliep.
        # Vervallen door niet betalen heeft een eigen datum; bij 'ongeldig omdat
        # het basisoctrooi verviel' is de werkelijke datum onbekend (maar voorbij).
        if c['status'].startswith('Lapsed') and c.get('vervallen'):
            c['einde_register'], c['einde'] = c.get('einde', ''), c['vervallen']
        elif c['status'].startswith('Invalid') and c.get('einde'):
            c['einde_register'], c['einde'] = c['einde'], ''
        c['hoofd'] = hoofdcertificaat(c['titel'], namen, merken) or \
            any(c['titel'].lower().startswith(m.lower()) for m in merken)
        v = (c.get('verlenging') or '').lower()
        c['verlenging_loopt'] = ('pending' in v or 'filed' in v) and 'granted' not in v
    hoofd = [c for c in certs if c['hoofd']]
    for soort in ('actief', 'aanvraag', 'verlopen'):
        kandidaten = [c for c in hoofd if c['klasse'] == soort]
        if soort == 'actief':
            kandidaten = [c for c in kandidaten if c.get('einde')]
        if kandidaten:
            return max(kandidaten, key=lambda c: c.get('einde') or '')
    return None


# ---------- EMA ----------

def lees_evaluatie():
    import openpyxl
    pad = os.path.join(BRON, 'ema_evaluatie.xlsx')
    if not os.path.exists(pad):
        return [], ''
    rijen = list(openpyxl.load_workbook(pad, read_only=True).active.iter_rows(values_only=True))
    peil = ''
    for r in rijen[:8]:
        for c in r:
            m = re.search(r'Data extracted (\d{1,2} \w+ \d{4})', str(c or ''))
            if m:
                peil = m.group(1)
    kop = next((i for i, r in enumerate(rijen) if r and str(r[0] or '').startswith('International non')), None)
    if kop is None:
        raise RuntimeError('EMA-evaluatielijst: kopregel niet gevonden')
    k = [str(c or '').strip() for c in rijen[kop]]
    i_inn, i_soort = 0, k.index('Generic, hybrid or Biosimilar')
    i_start = k.index('Start of evaluation')
    i_type = next((i for i, c in enumerate(k) if c.startswith('Substance type')), None)
    uit = []
    for r in rijen[kop + 1:]:
        if not r or not r[i_inn]:
            continue
        uit.append({'inn': str(r[i_inn]).strip(), 'kopie': str(r[i_soort] or '').strip().upper() == 'Y',
                    'type': str(r[i_type] or '') if i_type is not None else '',
                    'start': ema_datum(r[i_start]) or str(r[i_start] or '')[:10]})
    return uit, peil


# ---------- Horizonscan ----------

def lees_hs_pijplijn():
    """Biosimilars en generieken uit de Horizonscan-export. Lezen op positie:
    de kolomkoppen komen dubbel voor (drie keer 'Additional remarks')."""
    uit = []
    for pad in sorted(glob.glob(os.path.join(BRON, 'hs_*.csv'))):
        tekst = open(pad, encoding='utf-8-sig').read()
        lezer = csv.reader(io.StringIO(tekst), delimiter=';')
        kop = next(lezer)
        if kop[0] != 'Active substance' or kop[2] != 'Reason of inclusion':
            raise RuntimeError(f'{os.path.basename(pad)}: onverwachte kolomindeling')
        for r in lezer:
            if len(r) < 25 or r[2].strip() not in ('Biosimilar', 'Generic'):
                continue
            uit.append({'stof': r[0].strip(), 'reden': r[2].strip(), 'merk': r[7].strip(),
                        'fabrikant': r[8].strip(), 'indiening': r[21].strip(),
                        'verwacht': r[22].strip(), 'fase': r[24].strip(),
                        'domein': r[1].strip()})
    # Hetzelfde product staat per indicatie én soms in twee domeinen.
    gezien, schoon = set(), []
    for p in uit:
        k = (p['stof'].lower(), p['merk'].lower(), p['fabrikant'].lower())
        if k not in gezien:
            gezien.add(k)
            schoon.append(p)
    return schoon


def hs_stof_past(stof, inn):
    """'Secukinumab-bthr' en 'Ustekinumab' horen bij hun INN; 'Trastuzumab
    deruxtecan' niet bij trastuzumab."""
    s = re.sub(r'-[a-z]{4}$', '', stof.lower().strip())
    return middelen.zelfde_stof(s, inn)


# ---------- samenvoegen ----------

def maanden_tot(iso):
    if not iso:
        return None
    d = datetime.date.fromisoformat(iso)
    return (d.year - VANDAAG.year) * 12 + d.month - VANDAAG.month


def fase(m):
    if m['groep']:
        return 'groep'
    grens = m['toetreding']
    heeft_concurrent = bool(m['ema_kopie']) or m['nl']['n'] > 1
    if not grens and not m['spc']:
        return 'concurrentie' if heeft_concurrent else 'onbekend'
    if grens and grens > VANDAAG.isoformat():
        return 'binnenkort' if maanden_tot(grens) <= BINNENKORT_MAANDEN else 'beschermd'
    if m['spc'] and m['spc']['klasse'] == 'aanvraag' and not m['spc'].get('einde'):
        return 'onbekend'
    return 'concurrentie' if heeft_concurrent else 'vrij'


def bouw():
    gip, voorlopig = middelen.lees_gip()
    gekozen, jaren = middelen.selectie(gip)
    ema = middelen.lees_ema()
    inns = sorted({(r['International non-proprietary name (INN) / common name'] or '').strip() for r in ema} - {''})
    gs, gs_versie = middelen.lees_gs()
    evaluatie, eval_peil = lees_evaluatie()
    pijplijn = lees_hs_pijplijn()
    rvo = lees_json('rvo.json', {})
    ctgov = lees_json('ctgov.json', {})

    pdf, pdf_fout = lees_hs_overzicht()
    pdf_url = open(os.path.join(BRON, 'hs_patent.url')).read().strip() \
        if os.path.exists(os.path.join(BRON, 'hs_patent.url')) else ''

    uit = []
    for atc in gekozen:
        g = gip[atc]
        inn = middelen.inn_voor(atc, g['naam'], inns)
        rij = {'atc': atc, 'naam': g['naam'], 'inn': inn, 'kosten': g['kosten'],
               'gebruikers': g['gebruikers'], 'groep': middelen.GROEPEN.get(atc, '')}

        # EMA: origineel en kopieën
        eigen = [r for r in ema if middelen.zelfde_stof(
            r['International non-proprietary name (INN) / common name'], inn)]
        # Alleen producten die ooit een handelsvergunning kregen; afgewezen of
        # ingetrokken aanvragen (Bosatria, Ipique) zeggen niets over het origineel.
        orig = [r for r in eigen if r['Biosimilar'] != 'Yes' and r['Generic'] != 'Yes'
                and ema_datum(r['Marketing authorisation date'])]
        kopie = [r for r in eigen if r['Biosimilar'] == 'Yes' or r['Generic'] == 'Yes']
        # Het origineel is het eerst geregistreerde product (plus wat binnen een jaar
        # volgde, zoals Eylea en Zaltrap). Latere producten zonder biosimilarvlag zijn
        # meestal oudere biosimilars of duplicaten (ABP 710, Rituximab Mabion) en
        # tellen dus als concurrent, niet als merk.
        vergunning = sorted(d for d in (ema_datum(r['Marketing authorisation date']) for r in orig) if d)
        grens = plus_jaren(vergunning[0], 1) if vergunning else ''
        eerst = [r for r in orig if ema_datum(r['Marketing authorisation date']) <= grens]
        # Latere producten van dezelfde houder (Finlee, Spexotras naast Tafinlar) zijn
        # eigen lijnextensies, geen concurrent.
        houder = lambda r: (r.get('Marketing authorisation developer / applicant / holder') or '').split()[:1]
        eigen_houders = {tuple(houder(r)) for r in eerst}
        later = [r for r in orig if r not in eerst and r['Medicine status'] == 'Authorised']
        eigen_later = [r for r in later if tuple(houder(r)) in eigen_houders]
        rij['merken'] = sorted({r['Name of medicine'] for r in eerst})
        rij['merken_later'] = sorted({r['Name of medicine'] for r in eigen_later})
        rij['ema_overig'] = sorted({f"{r['Name of medicine']} ({ema_datum(r['Marketing authorisation date'])[:4]})"
                                    for r in later if r not in eigen_later})
        rij['eerste_vergunning'] = vergunning[0] if vergunning else ''
        rij['marktbescherming'] = plus_jaren(vergunning[0], 10) if vergunning else ''
        rij['wees'] = ('ja' if any(r['Orphan medicine'] == 'Yes' for r in eerst) else
                       'deels' if any(r['Orphan medicine'] == 'Yes' for r in eigen_later) else '')
        rij['ema_url'] = next((r.get('Medicine URL') for r in orig if r.get('Medicine URL')), '')
        rij['ema_kopie'] = sorted([{
            'naam': r['Name of medicine'],
            'soort': 'biosimilar' if r['Biosimilar'] == 'Yes' else 'generiek',
            'status': r['Medicine status'],
            'datum': ema_datum(r['Marketing authorisation date']) or ema_datum(r.get('Opinion adopted date')),
            'houder': r.get('Marketing authorisation developer / applicant / holder') or '',
            'url': r.get('Medicine URL') or '',
        } for r in kopie if r['Medicine status'] in ('Authorised', 'Opinion')],
            key=lambda k: k['datum'] or '9')
        rij['ema_kopie_weg'] = len([r for r in kopie if r['Medicine status'] not in ('Authorised', 'Opinion')])
        rij['ema_eval'] = [e for e in evaluatie if e['kopie'] and middelen.zelfde_stof(e['inn'], inn)]

        # Octrooiregister
        certs = rvo.get(atc, [])
        spc = kies_spc(certs, sorted({inn, g['naam']}, key=len, reverse=True),
                       rij['merken']) if not rij['groep'] else None
        # Eerst de certificaten over de stof zelf, binnen elke groep de laatste einddatum bovenaan.
        certs = sorted(certs, key=lambda c: c.get('einde') or '', reverse=True)
        rij['certificaten'] = sorted(certs, key=lambda c: not c.get('hoofd'))
        rij['spc'] = dict(spc, bron='RVO') if spc else None

        # Horizonscan-PDF: vergelijken, en terugvallen als RVO niets heeft
        k = {middelen.sleutel(g['naam']), middelen.sleutel(inn)}
        hs = next((r for r in pdf['rijen'] if middelen.sleutel(r['naam']) in k
                   or PDF_NAAM.get(r['naam'].lower()) == atc), None)
        rij['hs'] = None
        if hs:
            rij['hs'] = {'spc': hs['spc'], 'datum': hs['datums'][0] if hs['datums'] else '',
                         'verlopen': hs['verlopen'], 'concurrentie': hs['concurrentie'],
                         'wees': hs['wees'], 'merk': hs['merk'], 'voetnoot': hs['voetnoot']}
            rij['hs']['vergelijking'] = vergelijk(rij['spc'], rij['hs'], pdf['stand'])
            if (not rij['spc'] or rij['spc']['klasse'] == 'aanvraag' and not rij['spc'].get('einde')) \
                    and not rij['groep'] and (rij['hs']['datum'] or rij['hs']['verlopen']):
                oud = rij['spc']
                rij['spc'] = {'bron': 'Horizonscan', 'einde': rij['hs']['datum'],
                              'klasse': 'verlopen' if rij['hs']['verlopen'] or rij['hs']['datum'] < VANDAAG.isoformat()
                              else 'actief', 'status': rij['hs']['spc'], 'titel': '', 'nr': '',
                              'aanvraag_rvo': oud['nr'] if oud else ''}

        # Toetreding: de laatste van SPC-einde en marktbescherming
        grenzen = [d for d in ((rij['spc'] or {}).get('einde'), rij['marktbescherming']) if d]
        rij['toetreding'] = max(grenzen) if grenzen else ''
        rij['toetreding_door'] = ('spc' if rij['spc'] and rij['toetreding'] == rij['spc'].get('einde')
                                  else 'markt' if rij['toetreding'] else '')

        rij['pijplijn'] = [p for p in pijplijn if hs_stof_past(p['stof'], inn)]
        rij['studies'] = ctgov.get(atc, [])
        nl = gs.get(atc, {'reg': {}, 'artikelen': []})
        rij['nl'] = {'n': len(nl['reg']), 'reg': nl['reg'], 'artikelen': nl['artikelen']}
        rij['fase'] = fase(rij)
        uit.append(rij)

    bronnen = {
        'gip_jaren': jaren, 'voorlopig': voorlopig, 'gs': gs_versie, 'eval': eval_peil,
        'pdf_stand': pdf['stand'], 'pdf_url': pdf_url,
        'pdf_voetnoten': list(dict.fromkeys(pdf['voetnoten'])), 'pdf_fout': pdf_fout,
    }
    return uit, bronnen


def lees_hs_overzicht():
    """Het Horizonscan-overzicht patentverloop, met een vangnet.

    Het overzicht verschijnt een paar keer per jaar; ophalen.py pakt steeds de
    nieuwste. Verandert de opmaak zo dat de tabel niet meer te lezen is, dan
    wordt de pagina gewoon gebouwd zonder vergelijking, met een melding op de
    pagina -- de maandelijkse update van al het andere gaat dus niet verloren.

    Elke gelezen editie wordt bewaard in historie/, zodat oudere edities (die de
    Horizonscan zelf niet naast elkaar laat staan) niet verloren gaan."""
    leeg = {'stand': '', 'rijen': [], 'voetnoten': []}
    pad = os.path.join(BRON, 'hs_patent.pdf')
    if not os.path.exists(pad):
        return leeg, ''
    try:
        pdf = hs_pdf.lees(pad)
    except Exception as e:                         # kapotte of andersoortige PDF
        pdf, fout = leeg, f'{type(e).__name__}: {e}'
    else:
        fout = '' if len(pdf['rijen']) >= 30 and pdf['stand'] else \
            f"{len(pdf['rijen'])} regels gelezen, stand '{pdf['stand'] or '?'}'"
    if fout:
        print(f'LET OP: het Horizonscan-overzicht kon niet goed worden gelezen ({fout}).\n'
              f'        De pagina wordt gebouwd zonder vergelijking; kijk hs_pdf.py na.')
        return leeg, fout
    naam = 'hs_patent_' + re.sub(r'\W+', '_', pdf['stand'].lower()) + '.json'
    pad_hist = os.path.join(HISTORIE, naam)
    if not os.path.exists(pad_hist):
        os.makedirs(HISTORIE, exist_ok=True)
        json.dump(pdf, open(pad_hist, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f'Horizonscan-overzicht stand {pdf["stand"]} bewaard in historie/{naam}')
    return pdf, ''


def vergelijk(spc, hs, stand):
    """Hoe verhoudt de Horizonscan-datum zich tot het register?"""
    if not spc or spc.get('bron') != 'RVO':
        return 'geen'
    if hs['verlopen']:
        return 'gelijk' if spc['klasse'] == 'verlopen' else 'verschil'
    if not hs['datum'] or not spc.get('einde'):
        return 'geen'
    dagen = (datetime.date.fromisoformat(spc['einde']) - datetime.date.fromisoformat(hs['datum'])).days
    if dagen == 0:
        return 'gelijk'
    if 175 <= dagen <= 190 and 'granted' in (spc.get('verlenging') or '').lower():
        return 'verlenging'                    # pediatrische verlenging van 6 maanden
    return f'verschil:{dagen}'


# ---------- historie ----------

def momentopname(rij):
    s = rij['spc'] or {}
    return {
        'naam': rij['naam'],
        'spc_einde': s.get('einde', ''), 'spc_klasse': s.get('klasse', ''), 'spc_bron': s.get('bron', ''),
        'verlenging': s.get('verlenging', ''),
        'kopie': sorted(k['naam'] + ' (' + k['status'] + ')' for k in rij['ema_kopie']),
        'eval': len(rij['ema_eval']),
        'studies': sorted(s['nct'] for s in rij['studies']),
        'pijplijn': sorted(f"{p['merk'] or p['stof']} ({p['fabrikant']})" for p in rij['pijplijn']),
        'nl': sorted(rij['nl']['reg']),
    }


def mutaties(oud, nieuw):
    """Verschillen tussen twee momentopnamen, in leesbare zinnen."""
    uit = []
    for atc in nieuw:
        if atc.startswith('_'):
            continue
        n = nieuw[atc]
        if atc not in oud:
            uit.append((atc, 'nieuw', 'Nieuw in het overzicht (kosten boven de drempel)'))
            continue
        o = oud[atc]
        if o['spc_einde'] != n['spc_einde'] or o['spc_klasse'] != n['spc_klasse']:
            uit.append((atc, 'spc', f"SPC: {o['spc_einde'] or '—'} ({o['spc_klasse'] or '—'}) → "
                                    f"{n['spc_einde'] or '—'} ({n['spc_klasse'] or '—'})"))
        elif o['verlenging'] != n['verlenging'] and n['verlenging']:
            uit.append((atc, 'spc', f"Pediatrische verlenging: {o['verlenging'] or '—'} → {n['verlenging']}"))
        for k in sorted(set(n['kopie']) - set(o['kopie'])):
            uit.append((atc, 'ema', f'EMA: {k}'))
        if n['eval'] != o['eval']:
            uit.append((atc, 'aanvraag', f"Aanvragen bij EMA in beoordeling: {o['eval']} → {n['eval']}"))
        for k in sorted(set(n['studies']) - set(o['studies'])):
            uit.append((atc, 'studie', f'Nieuwe biosimilarstudie {k}'))
        for k in sorted(set(n['pijplijn']) - set(o['pijplijn'])):
            uit.append((atc, 'pijplijn', f'Horizonscan: {k}'))
        if len(n['nl']) != len(o['nl']):
            uit.append((atc, 'nl', f"Handelsvergunningen op de NL add-on-lijst: {len(o['nl'])} → {len(n['nl'])}"))
    stand_oud = oud.get('_bronnen', {}).get('pdf_stand', '')
    stand_nieuw = nieuw.get('_bronnen', {}).get('pdf_stand', '')
    if stand_nieuw and stand_oud and stand_nieuw != stand_oud:
        uit.append(('', 'bron', f'Nieuw Horizonscan-overzicht patentverloop: stand {stand_oud} → {stand_nieuw}'))
    for atc in sorted(k for k in set(oud) - set(nieuw) if not k.startswith('_')):
        uit.append((atc, 'weg', 'Uit het overzicht (kosten onder de drempel)'))
    return uit


def werk_historie(rijen, bronnen, vastleggen):
    os.makedirs(HISTORIE, exist_ok=True)
    pad_moment = os.path.join(HISTORIE, 'momentopname.json')
    pad_log = os.path.join(HISTORIE, 'logboek.json')
    log = json.load(open(pad_log, encoding='utf-8')) if os.path.exists(pad_log) else \
        {'begin': VANDAAG.isoformat(), 'regels': []}
    nieuw = {r['atc']: momentopname(r) for r in rijen}
    nieuw['_bronnen'] = {'pdf_stand': bronnen['pdf_stand']}
    if os.path.exists(pad_moment):
        oud = json.load(open(pad_moment, encoding='utf-8'))
        verschil = mutaties(oud, nieuw)
    else:
        oud, verschil = None, []
    if vastleggen:
        namen = {a: o['naam'] for a, o in list((oud or {}).items()) + list(nieuw.items()) if 'naam' in o}
        namen[''] = 'Horizonscan-overzicht'
        for atc, soort, tekst in verschil:
            log['regels'].insert(0, {'datum': VANDAAG.isoformat(), 'atc': atc, 'naam': namen.get(atc, atc),
                                     'soort': soort, 'tekst': tekst})
        json.dump(nieuw, open(pad_moment, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)
        json.dump(log, open(pad_log, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'Mutaties t.o.v. vorige momentopname: {len(verschil)}'
          f'{"" if vastleggen else " (niet vastgelegd: --geen-historie)"}'
          f'{"  (eerste run: logboek begint vandaag)" if oud is None else ""}')
    return log


def main():
    rijen, bronnen = bouw()
    log = werk_historie(rijen, bronnen, '--geen-historie' not in sys.argv)

    data = {'bijgewerkt': VANDAAG.isoformat(), 'drempel': middelen.DREMPEL,
            'binnenkort': BINNENKORT_MAANDEN, 'bronnen': bronnen, 'middelen': rijen,
            'logboek': log, 'addon': ADDON_DASHBOARD, 'horizonscan': HORIZONSCAN_SITE}
    sjabloon = open(os.path.join(HIER, 'template.html'), encoding='utf-8').read()
    blob = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    if '/*DATA*/null/*DATA*/' not in sjabloon:
        sys.exit('template.html mist de plek voor de data (/*DATA*/null/*DATA*/)')
    open(UIT, 'w', encoding='utf-8').write(sjabloon.replace('/*DATA*/null/*DATA*/', blob))

    tel = {}
    for r in rijen:
        tel[r['fase']] = tel.get(r['fase'], 0) + 1
    print(f'{len(rijen)} middelen: ' + ', '.join(f'{k} {v}' for k, v in sorted(tel.items())))
    geen = [r['naam'] for r in rijen if not r['spc'] and not r['groep']]
    if geen:
        print('Zonder SPC in register of Horizonscan: ' + ', '.join(geen))
    print(f'Geschreven: {os.path.basename(UIT)} ({os.path.getsize(UIT) / 1024:.0f} kB)')


if __name__ == '__main__':
    main()
