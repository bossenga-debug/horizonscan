#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Haalt alle bronnen op en herbouwt de patentchecker bij wijziging.

    python3 bijwerken.py            # ophalen, en bij wijziging herbouwen
    python3 bijwerken.py --altijd   # ook herbouwen als er niets veranderd is
    python3 bijwerken.py --ci       # voor GitHub Actions: altijd bouwen, hard stoppen
    python3 bijwerken.py --geen-historie   # bouwen zonder wijzigingen vast te leggen

In GitHub Actions staat `bron/` er nooit (die map zit niet in de repo), dus daar
is elke run per definitie een wijziging. --ci is er voor het andere deel: bij de
kleinste twijfel stoppen, zodat er nooit een halve pagina online komt.
"""
import json
import os
import re
import subprocess
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
CI = '--ci' in sys.argv
PAGINA = os.path.join(HIER, 'patentchecker.html')

# Een geslaagde bouw zit rond de 225 kB met ~70 middelen. Ver daaronder, of
# veel minder middelen met een register-datum, betekent dat er data ontbreekt
# ook al is er geen foutmelding gekomen (bijv. een register dat leeg antwoordt).
ONDERGRENS = 150_000
MIN_MIDDELEN = 40
MIN_MET_SPC = 30


def draai(script, *args):
    r = subprocess.run([sys.executable, os.path.join(HIER, script), *args],
                       capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode:
        sys.stderr.write(r.stderr)
        sys.exit(f'{script} is gestopt met code {r.returncode}.')
    return r.stdout


def controleer():
    grootte = os.path.getsize(PAGINA) if os.path.exists(PAGINA) else 0
    if grootte < ONDERGRENS:
        sys.exit(f'\nGESTOPT: de pagina is maar {grootte / 1024:.0f} kB (verwacht ruim '
                 f'{ONDERGRENS / 1024:.0f} kB). Er is niets gepubliceerd.')
    tekst = open(PAGINA, encoding='utf-8').read()
    m = re.search(r'const DATA = (.*?);\nconst M', tekst, re.S)
    data = json.loads(m.group(1).replace('<\\/', '</'))
    middelen = data['middelen']
    met_spc = sum(1 for r in middelen if r['spc'] and r['spc'].get('bron') == 'RVO')
    if len(middelen) < MIN_MIDDELEN or met_spc < MIN_MET_SPC:
        sys.exit(f'\nGESTOPT: {len(middelen)} middelen, waarvan {met_spc} met een SPC uit het '
                 f'register (verwacht minstens {MIN_MIDDELEN} en {MIN_MET_SPC}). '
                 f'Er is niets gepubliceerd.')


def main():
    print('Ophalen:')
    uit = draai('ophalen.py', *(['--ci'] if CI else []))
    if 'Geen wijzigingen' in uit and not CI and '--altijd' not in sys.argv:
        print('De pagina is niet herbouwd; er was geen nieuwe data.')
        print('Toch herbouwen kan met: python3 bijwerken.py --altijd')
        return 0

    print('\nBouwen:')
    draai('bouw_site.py', *(['--geen-historie'] if '--geen-historie' in sys.argv else []))
    if CI:
        controleer()
    return 0


if __name__ == '__main__':
    sys.exit(main())
