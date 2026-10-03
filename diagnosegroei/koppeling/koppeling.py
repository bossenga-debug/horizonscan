"""Koppeltabel tussen DBC-diagnoses (Open DIS) en add-on geneesmiddelen (ATC).

Drie handmatig beheerde bestanden, puntkomma-gescheiden (opent direct in Excel):
  clusters.csv            cluster_id, naam, soort, DIS-verstrekkingscodes
  cluster_diagnoses.csv   welke specialisme+diagnosecodes bij een cluster horen
  cluster_atc.csv         welke add-on middelen bij een cluster horen (nagekeken)
  cluster_voorfase.csv    welke extramurale middelen de voorfase vormen (eerstelijns
                          behandeling vóór een add-on), afgeleid uit de FKG-indeling

Gebruik:
  python3 koppeling.py              controle + melding van nieuwe kandidaat-middelen
  python3 koppeling.py --rv         haal de FKG- en DKG-lijsten (risicoverevening) opnieuw op
  python3 koppeling.py --neem-over <cluster_id>
                                    zet de voorgestelde middelen van één (nieuw) cluster als
                                    concept in cluster_atc.csv
  python3 koppeling.py --voorstel   schrijf cluster_atc_voorstel.csv opnieuw uit de
                                    Farmatec-indicaties (en maak cluster_atc.csv aan
                                    als die nog niet bestaat)

Het voorstel zoekt in de verkorte vergoedingsindicaties van de Farmatec add-on
GS-lijst. Dat is een hulpmiddel, geen koppeling: alles in cluster_atc.csv moet
nagekeken zijn voordat het dashboard het als zeker toont. Status per regel:
  concept      voorgesteld, nog niet bekeken
  nagekeken    bevestigd
  uitgesloten  onterechte treffer; blijft staan zodat hij niet opnieuw als nieuw wordt gemeld
"""
import csv, datetime, io, re, sys, urllib.request, zipfile
from pathlib import Path
import pandas as pd

HIER = Path(__file__).parent
DATA = HIER.parent / "data"
ADDON = Path.home() / "preferentiebeleid" / "addon"

# Zoekpatroon op de verkorte indicatie, plus patronen die een treffer weer uitsluiten.
ZOEK = {
    "ms":        (r"\bMS\b|multiple scler", r"MS, HSCT"),
    "cu":        (r"colitis ulcerosa", None),
    "crohn":     (r"crohn", None),
    "psoriasis": (r"psoriasis", r"artritis|arthritis|PsA"),
    "eczeem":    (r"atopische dermatitis|atopisch eczeem", None),
    "psa":       (r"\bPsA\b|artritis psoriatica", None),
    "ra":        (r"^RA\b|\bRA,|reumato[iï]de artritis", r"JIA"),
    "axspa":     (r"\bSpA\b|\bSpA-nr\b|spondylitis ankylo|axSpA", r"JIA"),
    "oog":       (r"\bnLMD\b|\bLMD\b|\bDME\b|\bDMO\b|macula-oedeem|maculaoedeem|\bCNV\b|BRVO|CRVO", r"ROP|premature"),
    "prostaat":  (r"\bCRPC\b|\bHSPC\b|\bmHSPC\b|prostaat", None),
    "nsclc":     (r"\bNSCLC\b|niet-kleincellig", None),
    "myeloom":   (r"\bMM\b|myeloom", r"stamcel harvest|Anemie"),
    "mamma":     (r"^BC\b|\bBC,|\bEBC\b|\bTNBC\b|mammacarcinoom|borstkanker", None),
    "melanoom":  (r"melanoom", r"uveaal|conjunctiva|PAM"),
    "crc":       (r"\bCRC\b|colorectaal", None),
    "rcc":       (r"\bRCC\b|niercel", None),
    "astma":     (r"astma|asthma", None),
    "hematologie": (r"\bAML\b|\bALL\b|\bCML\b|\bCMML\b|\bMDS\b|\bMPN\b|myeloïde leukemie|myeloide leukemie|lymfatische leukemie|"
                    r"myelofibrose|polycyt|trombocyt(h)?emie|\bET\b|mastocytose|mestcel|\bASM\b|\bSM-AHN\b|Ph\+",
                    r"\bCLL\b|chronische lymfatische|hairy|haarcel|lymfoblastair lymfoom|stamcel harvest|Anemie"),
    "lymfoom":   (r"\bCLL\b|\bDLBCL\b|\bNHL\b|\bHL\b|klassiek HL|\bMCL\b|\bFL\b|lymfoom|Waldenstr", r"intraoculair|\bALL\b|mestcel|stamcel harvest|Anemie"),
}


# ---------- officiële groeperingen uit de risicoverevening ----------
# FKG_C: ATC-code -> farmaciekostengroep (o.a. add-on-klassen AUT, CAN, MAC, COZ, IMM).
# DKG_C: specialisme + DBC-diagnose -> klinische DX-groep -> diagnosekostengroep.
# Ze staan als .ods-bijlage bij de Regeling risicoverevening; de URL bevat de
# publicatiedatum, dus we lezen de jaarpagina uit in plaats van een vaste link.
ZIN = "https://www.zorginstituutnederland.nl"
RV_PAGINA = ZIN + "/financiering/informatie-voor-zorginstanties-verzekeraars-en-zorgkantoren/risicoverevening-zvw/zvw-{jaar}"
RV = DATA / "rv"
UA = {"User-Agent": "Mozilla/5.0 (diagnosegroei-dashboard)"}


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def haal_rv():
    """Download de nieuwste FKG_C- en DKG_C-referentiebestanden naar data/rv/."""
    RV.mkdir(parents=True, exist_ok=True)
    nu = datetime.date.today().year
    for jaar in (nu + 1, nu):
        try:
            html = _get(RV_PAGINA.format(jaar=jaar)).decode("utf-8", "replace")
        except Exception:
            continue
        gevonden = 0
        for soort in ("fkg_c", "dkg_c"):
            m = re.search(r'href="(/documenten/[^"]*referentiebestand-%s[^"]*)"' % soort, html)
            if not m:
                continue
            doc = _get(ZIN + m.group(1)).decode("utf-8", "replace")
            ods = re.search(r'href="([^"]+\.ods)"', doc)
            if ods:
                (RV / f"{soort}_{jaar}.ods").write_bytes(_get(ods.group(1)))
                print(f"opgehaald: {soort}_{jaar}.ods")
                gevonden += 1
        if gevonden == 2:
            return jaar
    sys.exit("FKG/DKG-referentiebestanden niet gevonden op de site van het Zorginstituut")


def rv_lijsten():
    """(fkg, dkg, modeljaar): fkg per ATC, dkg per (specialisme, diagnose zonder voorloopnullen)."""
    fk = sorted(RV.glob("fkg_c_*.ods"))
    dk = sorted(RV.glob("dkg_c_*.ods"))
    if not fk or not dk:
        return None, None, None
    f = pd.read_excel(fk[-1], engine="odf", sheet_name=None, dtype=str)
    ind = f["Indeling_geneesmiddelen_in_FKG"].iloc[:, :4]
    ind.columns = ["fkg", "fkg_oms", "atc", "stof"]
    addon = f["fkg_codes"].set_index("fkg_code")["fkg_code_addon"].to_dict()
    ind["addon"] = ind["fkg"].map(addon).eq("1")
    d = pd.read_excel(dk[-1], engine="odf", sheet_name=None, dtype=str)
    dx = d["diagnose_dxg"]
    dx = dx.assign(sleutel=list(zip(dx["spec_code"], dx["diag_code"].str.lstrip("0"))))
    dx = dx.merge(d["dxg_naar_DKG"], on="dxg", how="left")
    jaar = re.search(r"(\d{4})", fk[-1].name).group(1)
    return ind, dx, jaar


def verrijk(ind, dx, jaar):
    """Zet de officiële FKG/DKG-indeling als kolom in de handmatige tabellen (overige kolommen blijven)."""
    ca = lees("cluster_atc.csv")
    fk = {}
    for r in ind.itertuples():
        fk[r.atc] = (fk[r.atc] + " / " if r.atc in fk else "") + f"{r.fkg} {r.fkg_oms}"
    ca[f"fkg_{jaar}"] = ca["atc"].map(fk).fillna("")
    ca = ca[[c for c in ca.columns if not (c.startswith("fkg_") and c != f"fkg_{jaar}")]]
    ca.to_csv(HIER / "cluster_atc.csv", sep=";", index=False, encoding="utf-8-sig")
    cd = lees("cluster_diagnoses.csv")
    dg = {r.sleutel: f"{r.dxg} {r.omschrijving}" for r in dx.itertuples()}
    cd[f"dkg_{jaar}"] = [dg.get((s, d.lstrip("0")), "") for s, d in zip(cd["specialisme_cd"], cd["diagnose_cd"])]
    cd = cd[[c for c in cd.columns if not (c.startswith("dkg_") and c != f"dkg_{jaar}")]]
    cd.to_csv(HIER / "cluster_diagnoses.csv", sep=";", index=False, encoding="utf-8-sig")


# Voorfase: per cluster de extramurale FKG-klasse(n), eventueel beperkt tot ATC-prefixen.
VOORFASE = {
    "ra":        (["REU"], None),
    "psa":       (["REU"], None),
    "cu":        (["CRO"], None),
    "crohn":     (["CRO"], None),
    "psoriasis": (["PSO"], None),
    "eczeem":    (["PSO"], ("D07", "D11AH01", "D11AH02", "D11AH04")),   # corticosteroïden, tacrolimus, pimecrolimus, alitretinoïne
    "ms":        (["RMS"], None),
    "astma":     (["AST"], None),
    "prostaat":  (["HOR"], ("L02AE", "L02BB", "L02BX", "H01CC")),        # GnRH, anti-androgenen, degarelix, relugolix
    "mamma":     (["HOR"], ("L02BA", "L02BG", "L02AB")),                 # tamoxifen/fulvestrant, aromataseremmers, megestrol
}


def voorstel_voorfase(ind):
    """Schrijf cluster_voorfase.csv uit de FKG-indeling als die nog niet bestaat."""
    pad = HIER / "cluster_voorfase.csv"
    if pad.exists():
        return
    rijen = []
    for cid, (klassen, prefix) in VOORFASE.items():
        s = ind[ind["fkg"].isin(klassen)]
        if prefix:
            s = s[s["atc"].str.startswith(prefix)]
        for r in s.itertuples():
            rijen.append({"cluster_id": cid, "atc": r.atc, "stof": r.stof.lower(), "fkg": r.fkg,
                          "status": "concept", "opmerking": ""})
    pd.DataFrame(rijen).to_csv(pad, sep=";", index=False, encoding="utf-8-sig")
    print(f"cluster_voorfase.csv aangemaakt: {len(rijen)} regels")


def lees(naam):
    return pd.read_csv(HIER / naam, sep=";", dtype=str, encoding="utf-8-sig").fillna("")


def farmatec():
    zips = sorted(ADDON.glob("addon-gs-*.zip"))
    if not zips:
        sys.exit(f"Geen Farmatec add-on GS-lijst gevonden in {ADDON}")
    z = zipfile.ZipFile(zips[-1])
    df = pd.read_excel(io.BytesIO(z.read(z.namelist()[0])), dtype=str).fillna("")
    return df, zips[-1].name


def gip():
    f = sorted(ADDON.glob("gip_addon_zvw_*.csv"))[-1]
    g = pd.read_csv(f, sep="#", dtype=str)
    g.columns = [c.strip() for c in g.columns]
    g = g.apply(lambda s: s.str.strip())
    g["atc"] = g["atclaatst"].str.replace("_", "", regex=False)
    g["jaar"] = g["jaar"].str[:4].astype(int)
    g["vergoeding"] = pd.to_numeric(g["vergoeding"], errors="coerce").fillna(0)
    return g


def voorstel(clusters):
    fm, bron = farmatec()
    g = gip()
    laatste_vol = g["jaar"].max() - 1       # laatste jaar in GIP is voorlopig
    uitgaven = g[g["jaar"] == laatste_vol].groupby("atc")["vergoeding"].sum()
    rijen = []
    for cid in clusters["cluster_id"]:
        if cid not in ZOEK:        # clusters zonder zoekpatroon (bijv. rond één middel) worden met de hand gevuld
            continue
        zoek, uit = ZOEK[cid]
        m = fm[fm["VerkorteIndicatie"].str.contains(zoek, case=False, regex=True)]
        if uit:
            m = m[~m["VerkorteIndicatie"].str.contains(uit, case=False, regex=True)]
        for atc, grp in m.groupby("ATC_Code"):
            ind = sorted(set(grp["VerkorteIndicatie"]))
            rijen.append({
                "cluster_id": cid, "atc": atc, "stof": grp["WerkzameStof"].iloc[0].lower(),
                f"vergoeding_{laatste_vol}": int(uitgaven.get(atc, 0)),
                "farmatec_indicaties": " | ".join(ind[:6]) + (f" | … (+{len(ind) - 6})" if len(ind) > 6 else ""),
                "status": "concept", "opmerking": ""})
    v = pd.DataFrame(rijen)
    # middelen die bij meer clusters horen: hun GIP-kosten zijn niet per indicatie te splitsen
    n = v.groupby("atc")["cluster_id"].transform("nunique")
    v.insert(4, "gedeeld_met", [
        ", ".join(sorted(set(v.loc[v["atc"] == a, "cluster_id"]) - {c})) for a, c in zip(v["atc"], v["cluster_id"])])
    v.loc[n == 1, "gedeeld_met"] = ""
    v = v.sort_values(["cluster_id", f"vergoeding_{laatste_vol}"], ascending=[True, False])
    v.to_csv(HIER / "cluster_atc_voorstel.csv", sep=";", index=False, encoding="utf-8-sig")
    print(f"cluster_atc_voorstel.csv: {len(v)} regels, {v['atc'].nunique()} middelen (bron {bron})")
    if not (HIER / "cluster_atc.csv").exists():
        v.to_csv(HIER / "cluster_atc.csv", sep=";", index=False, encoding="utf-8-sig")
        print("cluster_atc.csv aangemaakt als kopie van het voorstel — nakijken en status op 'nagekeken' zetten")


def neem_over(cid):
    """Voeg de voorstelregels van één cluster toe aan cluster_atc.csv (status concept)."""
    vs, ca = lees("cluster_atc_voorstel.csv"), lees("cluster_atc.csv")
    nieuw = vs[(vs["cluster_id"] == cid) & ~vs["atc"].isin(ca.loc[ca["cluster_id"] == cid, "atc"])]
    if nieuw.empty:
        print(f"{cid}: niets over te nemen"); return
    ca = pd.concat([ca, nieuw.reindex(columns=ca.columns).fillna("")], ignore_index=True)
    # gedeeld_met opnieuw uitrekenen over de hele tabel (actieve regels)
    act = ca[ca["status"] != "uitgesloten"]
    bij = act.groupby("atc")["cluster_id"].apply(set).to_dict()
    ca["gedeeld_met"] = [", ".join(sorted(bij.get(a, set()) - {c})) for a, c in zip(ca["atc"], ca["cluster_id"])]
    ca = ca.sort_values(["cluster_id", ca.columns[3]], ascending=[True, False], key=lambda s: pd.to_numeric(s, errors="coerce") if s.name == ca.columns[3] else s)
    ca.to_csv(HIER / "cluster_atc.csv", sep=";", index=False, encoding="utf-8-sig")
    print(f"{cid}: {len(nieuw)} middelen als concept toegevoegd aan cluster_atc.csv")


def controle(clusters):
    fout = 0
    dgn = pd.read_csv(DATA / "04_REF_DGN.csv", dtype=str)
    namen = {(r.SPECIALISME_CD, r.DIAGNOSE_CD): r.DIAGNOSE_OMSCHRIJVING for r in dgn.itertuples()}
    dbc = pd.read_csv(DATA / "01_DBC.csv", dtype=str, usecols=["JAAR", "BEHANDELEND_SPECIALISME_CD", "TYPERENDE_DIAGNOSE_CD", "AANTAL_PAT_PER_DIAG"])
    laatste = str(int(dbc["JAAR"].max()) - 2)
    vol = (dbc[dbc["JAAR"] == laatste].drop_duplicates(["BEHANDELEND_SPECIALISME_CD", "TYPERENDE_DIAGNOSE_CD"])
           .set_index(["BEHANDELEND_SPECIALISME_CD", "TYPERENDE_DIAGNOSE_CD"])["AANTAL_PAT_PER_DIAG"].astype(int))

    cd = lees("cluster_diagnoses.csv")
    print(f"\nDiagnoses per cluster (patiënten {laatste}):")
    for cid, grp in cd.groupby("cluster_id", sort=False):
        if cid not in set(clusters["cluster_id"]):
            print(f"  ! onbekend cluster_id '{cid}' in cluster_diagnoses.csv"); fout += 1
        for r in grp.itertuples():
            k = (r.specialisme_cd, r.diagnose_cd)
            if k not in namen:
                print(f"  ! {cid}: {k} bestaat niet in de NZa-referentietabel"); fout += 1
            elif k not in vol:
                print(f"  ! {cid}: {k} {namen[k]} heeft geen patiënten in {laatste}"); fout += 1
        tot = sum(vol.get((r.specialisme_cd, r.diagnose_cd), 0) for r in grp.itertuples())
        print(f"  {cid:10} {len(grp):2} diagnoses  {tot:>9,} patiënten".replace(",", "."))

    pad = HIER / "cluster_atc.csv"
    if not pad.exists():
        print("\ncluster_atc.csv ontbreekt — draai eerst met --voorstel"); return fout
    ca = lees("cluster_atc.csv")
    g = gip()
    jr = g["jaar"].max() - 1
    uitg = g[g["jaar"] == jr].groupby("atc")["vergoeding"].sum()
    bekend = set(g["atc"])
    for a in sorted(set(ca["atc"]) - bekend):
        print(f"  ! {a} komt niet voor in GIP (nog geen declaraties of typefout)")
    gekoppeld = set(ca.loc[ca["status"] != "uitgesloten", "atc"])
    dekking = uitg[uitg.index.isin(gekoppeld)].sum() / uitg.sum()
    status = ca["status"].value_counts().to_dict()
    print(f"\nMiddelen: {len(gekoppeld)} ATC-codes, {len(ca)} cluster-middel-paren; status {status}")
    print(f"Dekking: {dekking:.0%} van de add-on-uitgaven {jr} (€ {uitg.sum() / 1e6:,.0f} mln)".replace(",", "."))
    top = uitg.sort_values(ascending=False).head(60)
    mis = [(a, v) for a, v in top.items() if a not in gekoppeld]
    if mis:
        print("Grootste niet-gekoppelde middelen (top 60 op uitgaven):")
        naam = g.drop_duplicates("atc").set_index("atc")["atclaatst_naam_tekst"]
        for a, v in mis[:15]:
            print(f"  {a:8} {naam.get(a, '')[:30]:30} € {v / 1e6:6.1f} mln")

    ind, dx, jaar = rv_lijsten()
    if ind is not None:
        print(f"\nVergelijking met de FKG-indeling risicoverevening {jaar} (add-on-klassen):")
        naar_fkg = ind[ind["addon"]]
        for fkg, grp in naar_fkg.groupby("fkg"):
            atcs = set(grp["atc"])
            mis = atcs - gekoppeld
            bedrag = uitg[uitg.index.isin(mis)].sum() / 1e6
            regel = f"  {fkg:4} {grp['fkg_oms'].iloc[0][:38]:38} {len(atcs) - len(mis):3}/{len(atcs):<3} gekoppeld"
            if mis:
                stoffen = ", ".join(sorted(grp.loc[grp["atc"].isin(mis), "stof"].str.lower()))
                regel += f"; niet: € {bedrag:.1f}".replace(".", ",") + f" mln ({stoffen[:90]})"
            print(regel)
        cdx = lees("cluster_diagnoses.csv")
        buiten = sum(1 for s, d in zip(cdx["specialisme_cd"], cdx["diagnose_cd"]) if (s, d.lstrip("0")) not in set(dx["sleutel"]))
        print(f"Diagnoses: {len(cdx) - buiten} van {len(cdx)} vallen in een DKG-groep; de rest is niet kostenvoorspellend genoeg voor de risicoverevening, wat niet betekent dat ze fout zijn.")

    vp = HIER / "cluster_atc_voorstel.csv"
    if vp.exists():
        vs = lees("cluster_atc_voorstel.csv")
        nieuw = set(zip(vs["cluster_id"], vs["atc"])) - set(zip(ca["cluster_id"], ca["atc"]))
        if nieuw:
            print(f"\nNieuw in het voorstel, nog niet in cluster_atc.csv ({len(nieuw)}):")
            for c, a in sorted(nieuw):
                print(f"  {c:10} {a}")
    return fout


if __name__ == "__main__":
    cl = lees("clusters.csv")
    if "--rv" in sys.argv or not list(RV.glob("fkg_c_*.ods")):
        haal_rv()
    if "--voorstel" in sys.argv or "--neem-over" in sys.argv:
        voorstel(cl)
    if "--neem-over" in sys.argv:
        neem_over(sys.argv[sys.argv.index("--neem-over") + 1])
    ind, dx, jaar = rv_lijsten()
    if ind is not None:
        verrijk(ind, dx, jaar)
        voorstel_voorfase(ind)
    sys.exit(1 if controle(cl) else 0)
