"""Bouwt het diagnosegroei-dashboard uit Open DIS-data van de NZa.

Haalt 01_DBC.csv plus de referentietabellen op van opendisdata.nza.nl,
telt per jaar, specialisme en diagnose de patiënten en subtrajecten op
en schrijft dashboard.html (template.html + ingebakken data).

Daarnaast leest het uit 02_DBC_PROFIEL.csv (± 750 MB) alleen de
verstrekkingsactiviteiten voor dure geneesmiddelen, en rekent via
koppel_data.py de koppeling met add-on geneesmiddelen (GIP) uit.

Gebruik:  python3 build.py            (download opnieuw)
          python3 build.py --cache    (gebruik eerder gedownloade CSV's)
"""
import json, sys, urllib.request, datetime
import koppel_data
from pathlib import Path
import pandas as pd

HIER = Path(__file__).parent
DATA = HIER / "data"
BASIS = "https://opendisdata.nza.nl/download/csv/"
BESTANDEN = ["01_DBC.csv", "04_REF_DGN.csv", "06_REF_SPC.csv", "05_REF_ZPD.csv"]
AANTAL_JAREN = 6  # huidig jaar + 5 jaar terug


def download():
    DATA.mkdir(exist_ok=True)
    for f in BESTANDEN:
        if "--cache" in sys.argv and (DATA / f).exists():
            continue
        print("download", f)
        # De NZa-server weigert de standaard Python-user-agent (403).
        req = urllib.request.Request(BASIS + f, headers={"User-Agent": "Mozilla/5.0 (diagnosegroei-dashboard)"})
        tmp = DATA / (f + ".part")
        with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as out:
            out.write(r.read())
        tmp.replace(DATA / f)
    if not ("--cache" in sys.argv and (DATA / "02_verstrekking.csv").exists()):
        download_verstrekking()


def download_verstrekking():
    """Lees 02_DBC_PROFIEL.csv als stroom en bewaar alleen de verstrekkingsregels."""
    print("download 02_DBC_PROFIEL.csv (gefilterd op verstrekking dure geneesmiddelen)")
    codes = set(koppel_data.VERSTREKKING)
    req = urllib.request.Request(BASIS + "02_DBC_PROFIEL.csv", headers={"User-Agent": "Mozilla/5.0 (diagnosegroei-dashboard)"})
    tmp = DATA / "02_verstrekking.csv.part"
    n = 0
    with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "w", encoding="utf-8") as out:
        kop = r.readline().decode("utf-8")
        kolom = kop.strip().split(",").index("ZORGACTIVITEIT_CD")
        out.write(kop)
        for regel in r:
            velden = regel.decode("utf-8").split(",")
            if len(velden) > kolom and velden[kolom] in codes:
                out.write(regel.decode("utf-8")); n += 1
    tmp.replace(DATA / "02_verstrekking.csv")
    print(f"  {n} verstrekkingsregels bewaard")


def bouw():
    dbc = pd.read_csv(DATA / "01_DBC.csv", dtype=str)
    dgn = pd.read_csv(DATA / "04_REF_DGN.csv", dtype=str)
    spc = pd.read_csv(DATA / "06_REF_SPC.csv", dtype=str)
    for c in ["AANTAL_PAT_PER_DIAG", "AANTAL_SUBTRAJECT_PER_DIAG",
              "AANTAL_PAT_PER_SPC", "AANTAL_SUBTRAJECT_PER_SPC"]:
        dbc[c] = pd.to_numeric(dbc[c]).fillna(0).astype(int)
    dbc["JAAR"] = dbc["JAAR"].astype(int)
    # Kosten = subtrajecten × landelijk gemiddelde verkoopprijs van het zorgproduct (dat jaar).
    # Zorgproducten zonder vastgestelde prijs tellen niet mee (< 1% van de subtrajecten).
    dbc["KOSTEN"] = (pd.to_numeric(dbc["AANTAL_SUBTRAJECT_PER_ZPD"]).fillna(0)
                     * pd.to_numeric(dbc["GEMIDDELDE_VERKOOPPRIJS"]).fillna(0))

    peildatum = dbc["PEILDATUM"].iloc[0]
    laatste = int(peildatum[:4])
    jaren = list(range(laatste - AANTAL_JAREN + 1, laatste + 1))
    dbc = dbc[dbc["JAAR"].isin(jaren)]

    kosten_dgn = dbc.groupby(["BEHANDELEND_SPECIALISME_CD", "TYPERENDE_DIAGNOSE_CD", "JAAR"])["KOSTEN"].sum()
    kosten_spc = dbc.groupby(["BEHANDELEND_SPECIALISME_CD", "JAAR"])["KOSTEN"].sum()

    spc_naam = spc.set_index("SPECIALISME_CD")["OMSCHRIJVING"].to_dict()
    dgn_naam = {(r.SPECIALISME_CD, r.DIAGNOSE_CD): r.DIAGNOSE_OMSCHRIJVING
                for r in dgn.itertuples()}

    # Totalen per specialisme staan op elke regel herhaald: één regel per jaar/specialisme.
    s = dbc.drop_duplicates(["JAAR", "BEHANDELEND_SPECIALISME_CD"])
    specialismen = []
    for code, g in s.groupby("BEHANDELEND_SPECIALISME_CD"):
        g = g.set_index("JAAR")
        specialismen.append({
            "c": code,
            "n": spc_naam.get(code, code).replace("Medisch specialisten, ", ""),
            "p": [int(g["AANTAL_PAT_PER_SPC"].get(j, 0)) for j in jaren],
            "t": [int(g["AANTAL_SUBTRAJECT_PER_SPC"].get(j, 0)) for j in jaren],
            "k": [int(round(kosten_spc.get((code, j), 0))) for j in jaren],
        })

    d = dbc.drop_duplicates(["JAAR", "BEHANDELEND_SPECIALISME_CD", "TYPERENDE_DIAGNOSE_CD"])
    diagnoses = []
    for (sc, dc), g in d.groupby(["BEHANDELEND_SPECIALISME_CD", "TYPERENDE_DIAGNOSE_CD"]):
        g = g.set_index("JAAR")
        diagnoses.append({
            "s": sc, "c": dc, "n": dgn_naam.get((sc, dc), dc),
            "p": [int(g["AANTAL_PAT_PER_DIAG"].get(j, 0)) for j in jaren],
            "t": [int(g["AANTAL_SUBTRAJECT_PER_DIAG"].get(j, 0)) for j in jaren],
            "k": [int(round(kosten_dgn.get((sc, dc, j), 0))) for j in jaren],
        })

    koppeling, behandeld = koppel_data.bereken(
        jaren, d[["JAAR", "BEHANDELEND_SPECIALISME_CD", "TYPERENDE_DIAGNOSE_CD", "AANTAL_PAT_PER_DIAG"]],
        dbc[["JAAR", "BEHANDELEND_SPECIALISME_CD", "TYPERENDE_DIAGNOSE_CD", "ZORGPRODUCT_CD", "AANTAL_PAT_PER_ZPD"]])
    for x in diagnoses:
        b = behandeld.get((x["s"], x["c"]))
        if b:
            x["b"], x["bb"] = b      # reeks en bron: "a" = toedieningsactiviteit, "z" = geneesmiddel-zorgproduct

    data = {
        "peildatum": peildatum,
        "bestandsdatum": dbc["DATUM_BESTAND"].iloc[0],
        "gebouwd": datetime.date.today().isoformat(),
        "jaren": jaren,
        "specialismen": specialismen,
        "diagnoses": diagnoses,
        "koppeling": koppeling,
    }
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    html = (HIER / "template.html").read_text(encoding="utf-8")
    (HIER / "dashboard.html").write_text(html.replace("/*__DATA__*/null", blob), encoding="utf-8")
    print(f"dashboard.html: {len(specialismen)} specialismen, {len(diagnoses)} diagnoses, "
          f"jaren {jaren[0]}-{jaren[-1]}, peildatum {peildatum}"
          + (f", {len(koppeling['clusters'])} clusters" if koppeling else ", zonder add-on-koppeling"))


if __name__ == "__main__":
    download()
    bouw()
