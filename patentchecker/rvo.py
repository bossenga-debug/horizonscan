# -*- coding: utf-8 -*-
"""Leest aanvullende beschermingscertificaten (SPC's) uit het octrooiregister
van RVO / Octrooicentrum Nederland.

Er is geen gedocumenteerde API, maar de zoekpagina van het register praat zelf
JSON met de server, en die route werkt ook voor ons:

  1. GET  /fo-eregister-view/               -> sessiecookie + _csrf-token
  2. POST /fo-eregister-view/search         -> JSON met max. 10 treffers
  3. GET  /fo-eregister-view/search/details/<id>/0/<positie>/1/10/0/1/0/null_en_null/<query>
                                           -> HTML met de einddatum

Twee dingen die niet vanzelf spreken:
- In stap 3 staat de positie van de treffer op de DERDE plek. Op de zesde
  plek (waar hij logisch lijkt te horen) werken alleen de eerste twee treffers
  en krijg je daarna een lege detailpagina, met status 200.
- Het register zoekt op hele woorden in de titel van het certificaat. Een
  titel als 'Osimertinib (Tagrisso)' of een chemische naam vind je dus alleen
  met precies die term; zie RVO_EXTRA in middelen.py.

"Download XML file" werkt niet buiten de browser (geeft een leeg bestand).
"""
import html
import re
import time

import requests

BASIS = 'https://mijnoctrooi.rvo.nl/fo-eregister-view'
KOP = {'User-Agent': 'Mozilla/5.0 (patentchecker medicatieadvies.nl)'}
PAUZE = 0.4  # seconden tussen verzoeken; het register is een publieke dienst

# Status zonder einddatum die ertoe doet: voor deze certificaten halen we de
# detailpagina niet op. Dat scheelt ongeveer de helft van de verzoeken.
ZONDER_DETAIL = ('Withdrawn', 'Refused')


class Register:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(KOP)
        pagina = self.s.get(BASIS + '/', timeout=60).text
        m = re.search(r'name="_csrf"[^>]*?(?:value|content)="([^"]+)"', pagina)
        if not m:
            raise RuntimeError('RVO-register: geen _csrf-token op de startpagina. '
                               'Is de zoekpagina van indeling veranderd?')
        self.csrf = m.group(1)

    def zoek(self, term):
        r = self.s.post(BASIS + '/search', timeout=60, data={
            '_csrf': self.csrf, 'rightType[0]': 'SPC', '_rightType[0]': 'on',
            'title': term, 'advancedSearch': 'true'})
        r.raise_for_status()
        j = r.json()
        treffers = j['patents']['content']
        if j.get('total', 0) > len(treffers):
            print(f'    let op: "{term}" geeft {j["total"]} treffers, alleen de eerste '
                  f'{len(treffers)} zijn gelezen')
        uit = []
        for i, p in enumerate(treffers):
            rec = {
                'nr': p.get('publicationNumber') or p.get('applicationNumber'),
                'id': p['id'],
                'titel': ' '.join(html.unescape(p.get('title') or '').split()),
                'houder': ' '.join(html.unescape(p.get('applicantHolder') or '').split()),
                'status': ' '.join((p.get('status') or '').split()),
            }
            if not rec['status'].startswith(ZONDER_DETAIL):
                time.sleep(PAUZE)
                rec.update(self.detail(p['id'], i, j['queryExecuted']))
            uit.append(rec)
        return uit

    def detail(self, id_, positie, query):
        url = f'{BASIS}/search/details/{id_}/0/{positie}/1/10/0/1/0/null_en_null/{query}'
        t = self.s.get(url, timeout=60).text
        uit = {
            'basis': veld(t, 'Basic Patent Number:'),
            'einde': datum(veld(t, 'SPC/SPC Extension Expiration Date:')
                           or veld(t, 'Expiration date:')),
            'verlenging': veld(t, 'SPC Extension Status:'),
            'vergunning': datum(veld(t, 'First Marketing Authorization date:')),
            'vervallen': datum(veld(t, 'Lapsed By Non Payment Annual Fee Date:')),
        }
        if not veld(t, 'Publication number:'):
            # Lege sjabloonpagina: zie de uitleg bovenin over de positie.
            raise RuntimeError(f'RVO-register: lege detailpagina voor {id_}')
        return uit


def veld(pagina, label):
    m = re.search(re.escape(label) + r'\s*</[^>]+>\s*(?:<[^>]+>\s*)*([^<]*)', pagina)
    waarde = ' '.join(html.unescape(m.group(1)).split()) if m else ''
    return '' if waarde.endswith(':') else waarde


def datum(tekst):
    """dd/mm/jjjj -> jjjj-mm-dd (sorteerbaar); anders leeg."""
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})', tekst or '')
    return f'{m.group(3)}-{m.group(2)}-{m.group(1)}' if m else ''
