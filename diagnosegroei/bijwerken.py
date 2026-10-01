#!/usr/bin/env python3
"""Haalt nieuwe brondata op en bouwt het diagnosegroei-dashboard opnieuw.

    python3 bijwerken.py              ophalen en bouwen als er iets nieuw is
    python3 bijwerken.py --check      alleen kijken wat er nieuw is, niets schrijven
    python3 bijwerken.py --forceer    altijd bouwen (bijv. na een wijziging aan de koppeltabel)
    python3 bijwerken.py --ci         als --forceer-bij-nieuw, maar hard stoppen bij elke fout

Bronnen:
  Open DIS (NZa)      maandelijks ververst; de peildatum in 01_DBC.csv is het signaal
  GIP add-on/farmacie ongeveer jaarlijks; de naam van het meerjarenbestand is het signaal

Wat de vorige bouw gebruikte staat in stand.json (wél in git). Is alles gelijk,
dan wordt er niets gedownload of gebouwd. Zo kan de workflow vaker draaien dan
de NZa publiceert, zonder elke keer 750 MB binnen te halen.

Na het bouwen volgen controles; faalt er één, dan wordt er niets gepubliceerd.
"""
import json, os, re, subprocess, sys, urllib.request
from pathlib import Path

HIER = Path(__file__).parent
DATA = HIER / "data"
GIP = DATA / "gip"
STAND = HIER / "stand.json"
CHECK = "--check" in sys.argv
CI = "--ci" in sys.argv
FORCEER = "--forceer" in sys.argv
UA = {"User-Agent": "Mozilla/5.0 (diagnosegroei-dashboard)"}

NZA = "https://opendisdata.nza.nl/download/csv/01_DBC.csv"
GIP_PAGINA = "https://www.zorgcijfersdatabank.nl/algemeen/open-data-gip"


def fout(boodschap):
    if CI:
        sys.exit(boodschap + " Niets gepubliceerd.")
    print(boodschap)


def haal(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def peildatum_online():
    """Leest alleen de eerste dataregel van 01_DBC.csv (37 MB) voor de peildatum."""
    with urllib.request.urlopen(urllib.request.Request(NZA, headers=UA), timeout=120) as r:
        kop = r.readline().decode().strip().split(",")
        regel = r.readline().decode().strip().split(",")
    return dict(zip(kop, regel)).get("PEILDATUM")


def gip_links():
    """Zelfde aanpak als het add-on-dashboard: de downloadsleutel wisselt per bezoek."""
    pag = haal(GIP_PAGINA).decode("utf-8", "replace")
    gevonden = {}
    for m in re.finditer(r'<a[^>]*href="(/services/file/get\?key=[^"]+)"[^>]*>(.*?)</a>', pag, re.S):
        label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
        label = re.split(r"\s+CSV\b", label)[0]          # "… 2021-2025_12062026 CSV file 76.5 KB …" → bestandsnaam
        for soort, patroon in (("addon", r"GIP\s+Addon\s+Zvw\s+meerjaren"), ("farmacie", r"GIP\s+Farmacie\s+Zvw\s+meerjaren")):
            if soort not in gevonden and re.search(patroon, label, re.I):
                jaren = re.search(r"(\d{4})-(\d{4})", label)
                naam = f"gip_{soort}_zvw_{jaren.group(1)}_{jaren.group(2)}.csv" if jaren else f"gip_{soort}_zvw.csv"
                gevonden[soort] = ("https://www.zorgcijfersdatabank.nl" + m.group(1), naam, label)
    return gevonden


def haal_gip(links):
    GIP.mkdir(parents=True, exist_ok=True)
    for soort, (url, naam, label) in links.items():
        doel = GIP / naam
        if doel.exists():
            continue
        print(f"download {label}")
        data = haal(url)
        if b"#" not in data[:200]:
            fout(f"GIP {soort}: het bestand heeft niet de verwachte indeling (#-gescheiden).")
            continue
        for oud in GIP.glob(f"gip_{soort}_zvw_*.csv"):
            oud.unlink()
        doel.write_bytes(data)


def controles():
    """Hard falen als de pagina half of leeg zou worden."""
    html = (HIER / "dashboard.html").read_text(encoding="utf-8")
    m = re.search(r"const DATA = (\{.*?\});\n", html)
    if not m:
        return "geen data in dashboard.html"
    d = json.loads(m.group(1))
    if len(d["diagnoses"]) < 2000:
        return f"slechts {len(d['diagnoses'])} diagnoses"
    if len(d["specialismen"]) < 20:
        return f"slechts {len(d['specialismen'])} specialismen"
    k = d.get("koppeling")
    if not k or len(k["clusters"]) < 10:
        return "de add-on-koppeling ontbreekt of is onvolledig"
    if not any(sum(c["b"]) for c in k["clusters"]):
        return "geen behandelde patiënten: is 02_verstrekking.csv leeg?"
    # syntaxcontrole van het paginascript, als node beschikbaar is
    begin = html.index("<script>\nconst DATA") + 8
    script = html[begin: html.index("</script>", begin)]
    try:
        r = subprocess.run(["node", "-e", "new Function(require('fs').readFileSync(0,'utf8'))"],
                           input=script, text=True, capture_output=True, timeout=60)
        if r.returncode:
            return "syntaxfout in het paginascript:\n" + r.stderr[-800:]
    except FileNotFoundError:
        print("  (node niet gevonden; syntaxcontrole overgeslagen)")
    return None


def main():
    oud = json.loads(STAND.read_text()) if STAND.exists() else {}
    try:
        peil = peildatum_online()
    except Exception as e:
        return fout(f"Open DIS niet bereikbaar: {e}.")
    try:
        links = gip_links()
    except Exception as e:
        links = {}
        fout(f"GIP-pagina niet bereikbaar: {e}.")
    if CI and set(links) != {"addon", "farmacie"}:
        sys.exit("GIP: niet beide meerjarenbestanden gevonden op de overzichtspagina — indeling gewijzigd? Niets gepubliceerd.")

    nieuw = {"peildatum": peil, **{f"gip_{s}": v[2] for s, v in links.items()}}
    verschil = {k: (oud.get(k), v) for k, v in nieuw.items() if oud.get(k) != v}
    for k, (a, b) in verschil.items():
        print(f"  nieuw: {k}: {a} → {b}")
    if not verschil:
        print(f"  niets nieuw (peildatum {peil})")
    if CHECK:
        return
    if not verschil and not FORCEER:
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write("gebouwd=nee\n")
        return

    haal_gip(links)
    # NZa altijd vers als de peildatum veranderde; anders mag de cache gebruikt worden
    args = [sys.executable, str(HIER / "build.py")]
    if "peildatum" not in verschil and (DATA / "01_DBC.csv").exists():
        args.append("--cache")
    subprocess.run(args, check=True)

    probleem = controles()
    if probleem:
        sys.exit(f"Controle mislukt: {probleem}. Niets gepubliceerd.")
    nieuw["gebouwd"] = __import__("datetime").date.today().isoformat()
    STAND.write_text(json.dumps(nieuw, ensure_ascii=False, indent=2) + "\n")
    print("  controles in orde; stand.json bijgewerkt")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write("gebouwd=ja\n")


if __name__ == "__main__":
    main()
