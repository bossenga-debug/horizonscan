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

import middelen

HIER = os.path.dirname(os.path.abspath(__file__))
CI = '--ci' in sys.argv

# Een geslaagde bouw zit rond de 200 kB per pagina. Ver daaronder, of veel
# minder middelen met een register-datum, betekent dat er data ontbreekt ook al
# is er geen foutmelding gekomen (bijv. een register dat leeg antwoordt).
# Per set, want de GVS-set kent meer oude middelen zonder SPC.
EISEN = {
    'addon': {'kB': 150_000, 'middelen': 40, 'met_spc': 30},
    # De GVS-set is gezeefd op bescherming en schommelt daardoor in omvang;
    # een middel valt af zodra zijn bescherming verloopt.
    'gvs':   {'kB': 80_000, 'middelen': 30, 'met_spc': 20},
}


def draai(script, *args):
    r = subprocess.run([sys.executable, os.path.join(HIER, script), *args],
                       capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode:
        sys.stderr.write(r.stderr)
        sys.exit(f'{script} is gestopt met code {r.returncode}.')
    return r.stdout


def controleer():
    for naam, set_ in middelen.SETS.items():
        eis = EISEN[naam]
        pagina = os.path.join(HIER, set_['pagina'])
        grootte = os.path.getsize(pagina) if os.path.exists(pagina) else 0
        if grootte < eis['kB']:
            sys.exit(f"\nGESTOPT: {set_['pagina']} is maar {grootte / 1024:.0f} kB (verwacht ruim "
                     f"{eis['kB'] / 1024:.0f} kB). Er is niets gepubliceerd.")
        m = re.search(r'const DATA = (.*?);\nconst M', open(pagina, encoding='utf-8').read(), re.S)
        data = json.loads(m.group(1).replace('<\\/', '</'))
        rijen = data['middelen']
        met_spc = sum(1 for r in rijen if r['spc'] and r['spc'].get('bron') == 'RVO')
        if len(rijen) < eis['middelen'] or met_spc < eis['met_spc']:
            sys.exit(f"\nGESTOPT: set {naam}: {len(rijen)} middelen, waarvan {met_spc} met een SPC "
                     f"uit het register (verwacht minstens {eis['middelen']} en {eis['met_spc']}). "
                     f'Er is niets gepubliceerd.')
        print(f"  {set_['pagina']:24s} {grootte / 1024:5.0f} kB, {len(rijen)} middelen, "
              f'{met_spc} met SPC uit het register')


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
        print('\nControle:')
        controleer()
    return 0


if __name__ == '__main__':
    sys.exit(main())
