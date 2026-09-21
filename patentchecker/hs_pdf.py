# -*- coding: utf-8 -*-
"""Leest de tabel uit het Horizonscan-overzicht 'patentverloop dure geneesmiddelen'.

Dit is een vergelijkingsbron, geen hoofdbron: de PDF verschijnt ongeveer eens per
jaar en loopt dus achter op het octrooiregister. Juist daardoor is hij nuttig
als controle -- en als terugval voor middelen waarvan het certificaat in het
register niet onder de stofnaam te vinden is.

De PDF is een tabel met vier kolommen (specialité, SPC-datum, generieken en
biosimilars, weesindicatie). Met pypdf in layout-modus staan de kolommen op
één regel, gescheiden door lange reeksen spaties; tekst die over twee regels
doorloopt komt op een vervolgregel die met spaties begint.
"""
import re

KOLOMGAT = re.compile(r'\s{4,}')
DATUM = re.compile(r'(\d{2})-(\d{2})-(\d{4})')


def lees(pad):
    from pypdf import PdfReader
    pdf = PdfReader(pad)
    tekst = '\n'.join(p.extract_text(extraction_mode='layout') for p in pdf.pages)

    stand = re.search(r'stand van zaken ([a-z]+ \d{4})', tekst, re.I)
    rijen, huidig = [], None
    for regel in tekst.splitlines():
        if not regel.strip() or regel.strip().startswith(('Specilit', 'Specialit', 'registratie)', '*')):
            continue
        delen = KOLOMGAT.split(regel.strip())
        begint_links = not regel.startswith('  ' * 10)  # vervolgregels staan ver ingesprongen
        if begint_links and ' – ' in delen[0] and len(delen) >= 2:
            naam, merk = delen[0].split(' – ', 1)
            huidig = {'naam': naam.strip(), 'merk': merk.strip(), 'spc': delen[1].strip(),
                      'concurrentie': delen[2].strip() if len(delen) > 2 else '',
                      'wees': delen[3].strip() if len(delen) > 3 else ''}
            rijen.append(huidig)
        elif huidig is not None and not begint_links:
            # Vervolgregel: het middelste stuk hoort bij de concurrentiekolom,
            # een EU/3/-nummer bij de weeskolom.
            for d in delen:
                if re.match(r'EU\s?/?3', d):
                    huidig['wees'] += ' ' + d
                else:
                    tussen = '' if huidig['concurrentie'].endswith('-') else ' '
                    huidig['concurrentie'] = (huidig['concurrentie'].rstrip('-') + tussen + d).strip()
    for r in rijen:
        r['datums'] = [f'{j}-{m}-{d}' for d, m, j in DATUM.findall(r['spc'])]
        r['verlopen'] = r['spc'].lower().startswith('verlopen')
        r['voetnoot'] = r['spc'].count('*')
        r['wees'] = ' '.join(r['wees'].split())
    return {'stand': stand.group(1) if stand else '', 'rijen': rijen,
            'voetnoten': [' '.join(v.split()) for v in re.findall(r'^\s*(\*+ een secundair.*)$', tekst, re.M)]}


if __name__ == '__main__':
    import json
    import sys
    print(json.dumps(lees(sys.argv[1]), ensure_ascii=False, indent=1))
