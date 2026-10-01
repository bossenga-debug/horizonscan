"""Rekent de koppeling diagnoses ↔ add-on geneesmiddelen uit voor het dashboard.

Bronnen:
  data/01_DBC.csv, data/02_verstrekking.csv   Open DIS (NZa)
  gip_addon_zvw_*.csv, gip_farmacie_zvw_*.csv  GIP (Zorginstituut), add-on en extramuraal
  koppeling/*.csv                              handmatige koppeltabel

Per cluster komen er vier reeksen uit:
  diagnose   patiënten met een van de clusterdiagnoses (DIS)
  behandeld  patiënten die dure geneesmiddelen kregen (DIS), volgens één van twee bronnen,
             vast per cluster (kolom behandeld_bron in clusters.csv):
               activiteit   een verstrekkingsactiviteit van het cluster (02_DBC_PROFIEL)
               zorgproduct  een geneesmiddel-zorgproduct, zoals 028999017 "Toediening
                            immunotherapie via infuus/injectie" (01_DBC + 05_REF_ZPD).
                            Telt ook begeleiding van orale therapie; bij oncologie en
                            hematologie sluit dat veel beter aan op de add-on gebruikers.
  voorfase   gebruikers van de extramurale eerstelijnsmiddelen (GIP farmacie)
  addon      gebruikers en kosten van de gekoppelde add-ons (GIP add-on)

Gedeelde middelen (bij meer clusters gekoppeld) worden twee keer gerapporteerd:
volledig, en geschat verdeeld naar rato van de behandelde patiënten per
cluster in DIS dat jaar. Die verdeling is een benadering: onderhuidse middelen
worden in DIS nauwelijks als verstrekking geregistreerd.
"""
from pathlib import Path
import re
import pandas as pd

HIER = Path(__file__).parent
DATA = HIER / "data"
KOP = HIER / "koppeling"
ADDON = Path.home() / "preferentiebeleid" / "addon"

# Alle verstrekkingsactiviteiten voor dure geneesmiddelen die we uit 02_DBC_PROFIEL bewaren.
VERSTREKKING = [
    "039135", "039136", "039137", "039138", "039139", "039140",          # biologicals / immuunmodulatie
    "039141", "039142", "039143", "039144", "039145", "039146",          # chemo, chemo-immuno, immuno
    "039147", "039148", "039149", "039150", "039151", "039173",          # hormoon, TIL, desensibilisatie, gentherapie, DC
    "039810", "039888", "191014", "120415",                              # intravitreaal, intravesicaal, CAR-T, PSMA
    "190051", "190052", "190053",                                        # verstrekking oncolytica (oud)
]


# Geneesmiddel-zorgproducten: een onderdeel van de omschrijving (LATIJN_OMS, gescheiden
# door " | ") gaat over toediening, begeleiding of verstrekking van (dure) geneesmiddelen.
ZPD_GENEESMIDDEL = re.compile(
    r"toediening (chemo|immuno|biolog)|toediening .*(chemo|immuno|hormoon)therapie|"
    r"intraveneuze/ ?intrathecale toediening|begeleiden behandeling met|begeleiding immunotherapie|"
    r"behandeling met (chemo|immuno)|dure medicijnen|chronische verstrekking geneesmiddelen|"
    r"intravitreale injectie|immuun effectorcel|verstrekking chemo|^immunotherapie$", re.I)


def geneesmiddel_zorgproducten():
    """{zorgproductcode: (onderdeel dat het geneesmiddel noemt, consumentenomschrijving)}"""
    pad = DATA / "05_REF_ZPD.csv"
    if not pad.exists():
        return {}
    z = pd.read_csv(pad, dtype=str).fillna("")
    uit = {}
    for r in z.itertuples():
        for deel in r.LATIJN_OMS.split(" | "):
            if ZPD_GENEESMIDDEL.search(deel.strip()):
                uit[r.ZORGPRODUCT_CD] = (deel.strip(), r.CONSUMENT_OMS)
                break
    return uit


def lees_kop(naam):
    pad = KOP / naam
    if not pad.exists():
        return pd.DataFrame()
    return pd.read_csv(pad, sep=";", dtype=str, encoding="utf-8-sig").fillna("")


def bronbestand(patroon):
    """GIP-bestanden: eerst data/gip/, anders de map van het add-on-dashboard."""
    for map_ in (DATA / "gip", ADDON):
        f = sorted(map_.glob(patroon))
        if f:
            return f[-1]
    return None


def lees_gip(patroon):
    f = bronbestand(patroon)
    if f is None:
        return None, []
    g = pd.read_csv(f, sep="#", dtype=str)
    g.columns = [c.strip() for c in g.columns]
    g = g.apply(lambda s: s.str.strip())
    voorlopig = sorted({int(j[:4]) for j in g["jaar"] if j.endswith("*")})
    g["jaar"] = g["jaar"].str[:4].astype(int)
    g["atc"] = g["atclaatst"].str.replace("_", "", regex=False)
    for c in ("vergoeding", "gebruikers"):
        g[c] = pd.to_numeric(g[c], errors="coerce").fillna(0)
    return g, voorlopig


def behandeld_per_diagnose(jaren):
    """{(spc, diag): [patiënten met een dure-geneesmiddelverstrekking per jaar]} en per cluster-code."""
    pad = DATA / "02_verstrekking.csv"
    if not pad.exists():
        return None
    v = pd.read_csv(pad, dtype=str)
    v["p"] = pd.to_numeric(v["AANTAL_PAT"], errors="coerce").fillna(0)
    v["JAAR"] = v["JAAR"].astype(int)
    return v[v["JAAR"].isin(jaren)]


def bereken(jaren, dbc_diag, dbc_zpd=None):
    """dbc_diag: JAAR, BEHANDELEND_SPECIALISME_CD, TYPERENDE_DIAGNOSE_CD, AANTAL_PAT_PER_DIAG (uniek per diagnose).
    dbc_zpd: dezelfde regels per zorgproduct, met ZORGPRODUCT_CD en AANTAL_PAT_PER_ZPD."""
    v = behandeld_per_diagnose(jaren)
    cl, cd, ca, cv = (lees_kop(n) for n in ("clusters.csv", "cluster_diagnoses.csv", "cluster_atc.csv", "cluster_voorfase.csv"))
    addon, addon_voorl = lees_gip("gip_addon_zvw_*.csv")
    farm, farm_voorl = lees_gip("gip_farmacie_zvw_*.csv")
    if v is None or cl.empty or addon is None:
        return None, {}

    pat = dbc_diag.set_index(["BEHANDELEND_SPECIALISME_CD", "TYPERENDE_DIAGNOSE_CD", "JAAR"])["AANTAL_PAT_PER_DIAG"].astype(int)

    # behandeld per diagnose (alle verstrekkingscodes), begrensd op het aantal diagnosepatiënten
    def reeksen(groep):
        uit = {}
        for (s, d, j), n in groep.items():
            uit.setdefault((s, d), [0] * len(jaren))[jaren.index(j)] = int(min(n, pat.get((s, d, j), n)))
        return uit

    act_diag = reeksen(v.groupby(["BEHANDELEND_SPECIALISME_CD", "TYPERENDE_DIAGNOSE_CD", "JAAR"])["p"].sum())
    zpd_naam = geneesmiddel_zorgproducten()
    zp = pd.DataFrame(columns=["BEHANDELEND_SPECIALISME_CD", "TYPERENDE_DIAGNOSE_CD", "ZORGPRODUCT_CD", "JAAR", "p"])
    if dbc_zpd is not None and zpd_naam:
        zp = dbc_zpd[dbc_zpd["ZORGPRODUCT_CD"].isin(zpd_naam)].copy()
        zp["p"] = pd.to_numeric(zp["AANTAL_PAT_PER_ZPD"], errors="coerce").fillna(0)
        zp["JAAR"] = zp["JAAR"].astype(int)
    zpd_diag = reeksen(zp.groupby(["BEHANDELEND_SPECIALISME_CD", "TYPERENDE_DIAGNOSE_CD", "JAAR"])["p"].sum())
    # per diagnose één vaste bron: die met de meeste patiënten over de volledige jaren
    vol = slice(0, len(jaren) - 2)
    behandeld_diag = {}
    for k in set(act_diag) | set(zpd_diag):
        a, z = act_diag.get(k, [0] * len(jaren)), zpd_diag.get(k, [0] * len(jaren))
        behandeld_diag[k] = (z, "z") if sum(z[vol]) > sum(a[vol]) else (a, "a")

    gip_jaren = sorted(set(addon["jaar"]))
    ca = ca[ca["status"] != "uitgesloten"]
    cv = cv[cv["status"] != "uitgesloten"] if not cv.empty else cv
    a_k = addon.groupby(["atc", "jaar"])["vergoeding"].sum()
    a_g = addon.groupby(["atc", "jaar"])["gebruikers"].sum()
    naam = addon.drop_duplicates("atc").set_index("atc")["atclaatst_naam_tekst"].to_dict()
    fkg_kol = next((c for c in ca.columns if c.startswith("fkg_")), None)

    clusters = []
    for c in cl.itertuples():
        diag = cd[cd["cluster_id"] == c.cluster_id]
        sleutels = list(zip(diag["specialisme_cd"], diag["diagnose_cd"]))
        codes = c.verstrekkingscodes.split()
        vs = v[v["ZORGACTIVITEIT_CD"].isin(codes) & pd.Series(
            list(zip(v["BEHANDELEND_SPECIALISME_CD"], v["TYPERENDE_DIAGNOSE_CD"])), index=v.index).isin(sleutels)]
        zs = zp[pd.Series(list(zip(zp["BEHANDELEND_SPECIALISME_CD"], zp["TYPERENDE_DIAGNOSE_CD"])), index=zp.index).isin(sleutels)]
        # Per diagnose begrensd op het aantal diagnosepatiënten: een patiënt met meer
        # geneesmiddel-zorgproducten of -activiteiten in een jaar telt anders meer keer.
        beh_act = pd.Series({j: sum(act_diag.get(k, [0] * len(jaren))[jaren.index(j)] for k in sleutels) for j in jaren})
        beh_zpd = pd.Series({j: sum(zpd_diag.get(k, [0] * len(jaren))[jaren.index(j)] for k in sleutels) for j in jaren})
        bron = getattr(c, "behandeld_bron", "") or "activiteit"
        beh = beh_zpd if bron == "zorgproduct" else beh_act
        top = zs.groupby(["ZORGPRODUCT_CD", "JAAR"])["p"].sum().unstack(fill_value=0)
        laatste_vol = jaren[-3]
        if not top.empty:
            top = top.sort_values(laatste_vol if laatste_vol in top.columns else top.columns[-1], ascending=False).head(15)
        clusters.append({
            "bron": bron,
            "ba": [int(beh_act.get(j, 0)) for j in jaren],
            "bz": [int(beh_zpd.get(j, 0)) for j in jaren],
            "zpd": [{"c": code, "o": zpd_naam[code][0], "co": zpd_naam[code][1],
                     "p": [int(r.get(j, 0)) for j in jaren]} for code, r in top.iterrows()],
            "id": c.cluster_id, "n": c.cluster, "soort": c.soort,
            "diag": [[s, d] for s, d in sleutels],
            "p": [int(sum(pat.get((s, d, j), 0) for s, d in sleutels)) for j in jaren],
            "b": [int(beh.get(j, 0)) for j in jaren],
            "atc": sorted(set(ca.loc[ca["cluster_id"] == c.cluster_id, "atc"])),
            "vf": sorted(set(cv.loc[cv["cluster_id"] == c.cluster_id, "atc"])) if not cv.empty else [],
        })

    # verdeelsleutel per gedeeld middel en jaar: behandelde patiënten (DIS) per cluster
    beh_jaar = {c["id"]: dict(zip(jaren, c["b"])) for c in clusters}
    bij = ca.groupby("atc")["cluster_id"].apply(lambda s: sorted(set(s))).to_dict()

    def aandeel(atc, cid, j):
        cs = bij.get(atc, [cid])
        if len(cs) == 1:
            return 1.0
        # GIP-jaren na het laatste DIS-jaar krijgen de sleutel van het laatste DIS-jaar
        jj = min(j, max(jaren))
        tot = sum(beh_jaar[x].get(jj, 0) for x in cs)
        return beh_jaar[cid].get(jj, 0) / tot if tot else 1 / len(cs)

    for c in clusters:
        k_vol, k_sch, g_vol, g_sch, k_eig = [], [], [], [], []
        for j in gip_jaren:
            kv = ks = gv = gs = ke = 0.0
            for a in c["atc"]:
                k, g = a_k.get((a, j), 0), a_g.get((a, j), 0)
                f = aandeel(a, c["id"], j)
                kv += k; gv += g; ks += k * f; gs += g * f
                if len(bij.get(a, [])) == 1:
                    ke += k
            k_vol.append(round(kv)); k_sch.append(round(ks)); g_vol.append(round(gv)); g_sch.append(round(gs)); k_eig.append(round(ke))
        c.update(kv=k_vol, ks=k_sch, gv=g_vol, gs=g_sch, ke=k_eig)
        if farm is not None and c["vf"]:
            f = farm[farm["atc"].isin(c["vf"])].groupby("jaar")
            c["vfg"] = [int(f["gebruikers"].sum().get(j, 0)) for j in gip_jaren]
            c["vfk"] = [int(f["vergoeding"].sum().get(j, 0)) for j in gip_jaren]

    # middelentabel voor de weergave
    middelen = {}
    for r in ca.drop_duplicates("atc").itertuples():
        middelen[r.atc] = {
            "n": (naam.get(r.atc) or r.stof).capitalize(),
            "k": [int(a_k.get((r.atc, j), 0)) for j in gip_jaren],
            "g": [int(a_g.get((r.atc, j), 0)) for j in gip_jaren],
            "c": bij.get(r.atc, []),
            "f": getattr(r, fkg_kol) if fkg_kol else "",
            "st": r.status,
        }
    vf_middelen = {}
    if farm is not None and not cv.empty:
        fn = farm.drop_duplicates("atc").set_index("atc")["atclaatst_naam_tekst"].to_dict()
        fk = farm.groupby(["atc", "jaar"])
        fg, fv = fk["gebruikers"].sum(), fk["vergoeding"].sum()
        for r in cv.drop_duplicates("atc").itertuples():
            vf_middelen[r.atc] = {"n": fn.get(r.atc, r.stof).capitalize(), "f": r.fkg,
                                  "g": [int(fg.get((r.atc, j), 0)) for j in gip_jaren],
                                  "k": [int(fv.get((r.atc, j), 0)) for j in gip_jaren]}

    return {
        "gip_jaren": gip_jaren, "addon_voorlopig": addon_voorl, "farm_voorlopig": farm_voorl,
        "clusters": clusters, "middelen": middelen, "vf_middelen": vf_middelen,
        "rv_jaar": (fkg_kol or "fkg_")[4:],
    }, behandeld_diag
