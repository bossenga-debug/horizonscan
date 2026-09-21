#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Haalt de Horizonscan-data op en herbouwt de pagina bij wijziging.

    python3 bijwerken.py            # ophalen, en bij wijziging herbouwen
    python3 bijwerken.py --altijd   # ook herbouwen als er niets veranderd is
    python3 bijwerken.py --ci       # voor GitHub Actions: altijd bouwen, hard stoppen
    python3 bijwerken.py --geen-historie   # bouwen zonder mutaties vast te leggen

In GitHub Actions staat `bron/` er nooit (die map zit niet in de repo), dus daar
is elke run per definitie een wijziging. --ci is er voor het andere deel: bij de
kleinste twijfel stoppen, zodat er nooit een halve pagina online komt.
"""
import os
import subprocess
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
CI = '--ci' in sys.argv
PAGINA = os.path.join(HIER, 'horizonscan.html')

# Een geslaagde bouw zit rond de 2,8 MB. Ver daaronder betekent dat er data
# ontbreekt, ook al is er geen foutmelding gekomen.
ONDERGRENS = 1_500_000


def draai(script, *args):
    r = subprocess.run([sys.executable, os.path.join(HIER, script), *args],
                       capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode:
        sys.stderr.write(r.stderr)
        sys.exit(f'{script} is gestopt met code {r.returncode}.')
    return r.stdout


def main():
    print('Ophalen:')
    uit = draai('ophalen.py', *(['--ci'] if CI else []))
    if 'Geen wijzigingen' in uit and not CI and '--altijd' not in sys.argv:
        print('De pagina is niet herbouwd; er was geen nieuwe data.')
        print('Toch herbouwen kan met: python3 bijwerken.py --altijd')
        return 0

    print('\nBouwen:')
    # --geen-historie gaat door naar bouw_site.py: de pagina wordt dan vers
    # gebouwd, maar er komt geen meetpunt in het mutatielogboek bij.
    draai('bouw_site.py', *(['--geen-historie'] if '--geen-historie' in sys.argv else []))

    if CI:
        grootte = os.path.getsize(PAGINA) if os.path.exists(PAGINA) else 0
        if grootte < ONDERGRENS:
            sys.exit(f'\nGESTOPT: de pagina is maar {grootte / 1024:.0f} kB '
                     f'(verwacht ruim {ONDERGRENS / 1024 / 1024:.1f} MB). '
                     f'De bouw wordt niet vertrouwd, er is niets gepubliceerd.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
