#!/usr/bin/env python3
"""
Fara'id-Kern (exakt, fractions.Fraction). Unterstuetzte Erben:
  Ehemann, Ehefrauen, Vater, Mutter, Grossvater (vaeterl.), Grossmutter (muetterl./vaeterl.),
  Soehne, Toechter, volle Brueder, volle Schwestern.
NICHT unterstuetzt (-> Unsupported statt stiller Falschrechnung): Enkel, Halbgeschwister,
  Akdariyya-/Mukhtasira-Familie (Grossvater+Geschwister mit Rest < 1/6), Dhawu al-Arham.

Regeln sind PARAMETER, keine Schulen-Etiketten:
  grandfather_rule = "muqasama"  (Zayd ibn Thabit: bester von 1/6 | 1/3 des Rests | Teilen wie ein Bruder)
                   | "blocks"    (Abu Bakr: Grossvater wie Vater, sperrt Geschwister)
  radd             = True  (Rest geht per Radd an die Erben mit Fard) | False (Rest geht an den Bayt al-Mal, kein Radd)
  radd_spouses     = False (Radd nur an Blutsverwandte) | True (Radd auch an Ehepartner); nur relevant bei radd=True
Welche Schule/welcher Gelehrte welche Einstellung vertritt, ist HIER NICHT belegt und wird nicht behauptet.
Faelle, deren Ergebnis von den Parametern abhaengt, werden von classify() als 'disputed' markiert.
Konsens-Kern (alle Parameter gleich): Hajb, Awl, Umariyyatain, Asaba, Asaba ma'a al-Ghayr.
ACHTUNG (Korrektur 25.10.2026): Radd ist NICHT Konsens. v1 des Datensatzes hat es faelschlich als Konsens behandelt; das ist die Ursache fuer die Zusatzvariante radd=False.
"""
from dataclasses import dataclass
from fractions import Fraction as F

SPOUSES = ("husband", "wives")


class Unsupported(Exception):
    pass


@dataclass(frozen=True)
class Heirs:
    deceased: str = "male"          # "male" | "female"
    husband: bool = False
    wives: int = 0
    father: bool = False
    mother: bool = False
    grandfather: bool = False
    maternal_grandmother: bool = False
    paternal_grandmother: bool = False
    sons: int = 0
    daughters: int = 0
    full_brothers: int = 0
    full_sisters: int = 0


def _validate(h: Heirs):
    if h.deceased not in ("male", "female"):
        raise ValueError("deceased muss 'male' oder 'female' sein")
    if h.deceased == "male" and h.husband:
        raise ValueError("Verstorbener Mann kann keinen Ehemann haben")
    if h.deceased == "female" and h.wives:
        raise ValueError("Verstorbene Frau kann keine Ehefrauen haben")
    if not (0 <= h.wives <= 4):
        raise ValueError("wives muss 0..4 sein")
    for n in ("sons", "daughters", "full_brothers", "full_sisters"):
        if getattr(h, n) < 0:
            raise ValueError(n + " negativ")
    if not any([h.husband, h.wives, h.father, h.mother, h.grandfather, h.maternal_grandmother,
                h.paternal_grandmother, h.sons, h.daughters, h.full_brothers, h.full_sisters]):
        raise ValueError("keine Erben")


def solve(h: Heirs, grandfather_rule: str = "muqasama", radd_spouses: bool = False, radd: bool = True) -> dict:
    assert grandfather_rule in ("muqasama", "blocks")
    _validate(h)
    sh: dict = {}
    st: dict = {}
    flags = {"awl": False, "radd": False, "umariyyatain": False, "hajb": False,
             "asaba_maa_ghayr": False, "bayt_al_mal": False}

    children = h.sons + h.daughters
    sibs = h.full_brothers + h.full_sisters
    gf = h.grandfather and not h.father
    sib_hard_blocked = h.sons > 0 or h.father
    sib_active = sibs > 0 and not sib_hard_blocked and not (gf and grandfather_rule == "blocks")
    mixed = gf and sib_active                       # Grossvater teilt mit Geschwistern (Muqasama-Regime)

    blocked = []
    if h.grandfather and h.father: blocked.append("grandfather")
    if sibs > 0 and not sib_active:
        if h.full_brothers: blocked.append("full_brothers")
        if h.full_sisters: blocked.append("full_sisters")
    gm_mat = h.maternal_grandmother and not h.mother
    gm_pat = h.paternal_grandmother and not h.mother and not h.father
    if h.maternal_grandmother and not gm_mat: blocked.append("maternal_grandmother")
    if h.paternal_grandmother and not gm_pat: blocked.append("paternal_grandmother")
    flags["hajb"] = bool(blocked)

    # ---- Furud ----
    spouse_share = F(0)
    if h.husband:
        spouse_share = F(1, 4) if children else F(1, 2)
        sh["husband"], st["husband"] = spouse_share, "Fard"
    elif h.wives:
        spouse_share = F(1, 8) if children else F(1, 4)
        sh["wives"], st["wives"] = spouse_share, "Fard"

    if h.mother:
        umar = h.father and (h.husband or h.wives > 0) and not children and sibs < 2
        if umar:
            sh["mother"] = F(1, 3) * (1 - spouse_share)
            flags["umariyyatain"] = True
        else:
            sh["mother"] = F(1, 6) if (children or sibs >= 2) else F(1, 3)
        st["mother"] = "Fard"

    gms = [k for k, ok in (("maternal_grandmother", gm_mat), ("paternal_grandmother", gm_pat)) if ok]
    for k in gms:
        sh[k], st[k] = F(1, 6) / len(gms), "Fard"

    if h.daughters and not h.sons:
        sh["daughters"] = F(1, 2) if h.daughters == 1 else F(2, 3)
        st["daughters"] = "Fard"

    if h.father:
        if children:
            sh["father"], st["father"] = F(1, 6), "Fard"
    elif gf and not mixed:
        if children:
            sh["grandfather"], st["grandfather"] = F(1, 6), "Fard"

    if sib_active and not mixed and h.full_sisters and not h.full_brothers and not h.daughters:
        sh["full_sisters"] = F(1, 2) if h.full_sisters == 1 else F(2, 3)
        st["full_sisters"] = "Fard"

    # ---- Grossvater teilt mit Geschwistern (Zayd) ----
    if mixed:
        S = sum(sh.values(), F(0))
        R = 1 - S
        if R < F(1, 6) or (R == F(1, 6) and h.full_sisters and not h.full_brothers):
            raise Unsupported("Grossvater+Geschwister mit Rest <= 1/6 und nur Schwestern (Akdariyya/Mukhtasira-Familie)")
        parts = 2 * (1 + h.full_brothers) + h.full_sisters
        options = {"sudus": F(1, 6), "thuluth_al_baqi": R / 3, "muqasama": R * 2 / parts}
        label, g = max(options.items(), key=lambda kv: kv[1])
        sh["grandfather"], st["grandfather"] = g, "Asaba (" + label + ")"
        rest = R - g
        wb, ws = 2 * h.full_brothers, h.full_sisters
        if rest > 0:
            if h.full_brothers:
                sh["full_brothers"], st["full_brothers"] = rest * wb / (wb + ws), "Asaba"
            if h.full_sisters:
                sh["full_sisters"], st["full_sisters"] = rest * ws / (wb + ws), "Asaba"
        else:
            if h.full_brothers: sh["full_brothers"], st["full_brothers"] = F(0), "Mahjub (Rest 0)"
            if h.full_sisters: sh["full_sisters"], st["full_sisters"] = F(0), "Mahjub (Rest 0)"
        return _finish(h, sh, st, flags, blocked, F(0))

    # ---- Awl ----
    total = sum(sh.values(), F(0))
    if total > 1:
        flags["awl"] = True
        for k in sh:
            sh[k] = sh[k] / total
        return _finish(h, sh, st, flags, blocked, F(0))

    # ---- Asaba ----
    R = 1 - total
    if R > 0:
        if h.sons:
            u = R / (2 * h.sons + h.daughters)
            sh["sons"], st["sons"] = u * 2 * h.sons, "Asaba"
            if h.daughters:
                sh["daughters"], st["daughters"] = u * h.daughters, "Asaba bi-Ghayriha"
            R = F(0)
        elif h.father:
            sh["father"] = sh.get("father", F(0)) + R
            st["father"] = "Fard+Asaba" if children else "Asaba"
            R = F(0)
        elif gf:   # nicht mixed -> kein aktives Geschwister
            sh["grandfather"] = sh.get("grandfather", F(0)) + R
            st["grandfather"] = "Fard+Asaba" if children else "Asaba"
            R = F(0)
        elif sib_active and h.full_brothers:
            u = R / (2 * h.full_brothers + h.full_sisters)
            sh["full_brothers"], st["full_brothers"] = u * 2 * h.full_brothers, "Asaba"
            if h.full_sisters:
                sh["full_sisters"], st["full_sisters"] = u * h.full_sisters, "Asaba bi-Ghayriha"
            R = F(0)
        elif sib_active and h.full_sisters and h.daughters:
            sh["full_sisters"], st["full_sisters"] = R, "Asaba ma'a al-Ghayr"
            flags["asaba_maa_ghayr"] = True
            R = F(0)

    # ---- Radd / Bayt al-Mal ----
    bayt = F(0)
    if R > 0:
        pool = {k: v for k, v in sh.items() if radd and v > 0 and (radd_spouses or k not in SPOUSES)}
        if pool:
            s = sum(pool.values(), F(0))
            for k, v in pool.items():
                sh[k] = v + R * v / s
                st[k] += "+Radd"
            flags["radd"] = True
        else:
            bayt = R
            flags["bayt_al_mal"] = True
    return _finish(h, sh, st, flags, blocked, bayt)


def _finish(h, sh, st, flags, blocked, bayt):
    for b in blocked:
        sh.setdefault(b, F(0))
        st.setdefault(b, "Mahjub")
    total = sum(sh.values(), F(0)) + bayt
    assert total == 1, f"Summe != 1: {total} {sh}"
    return {"shares": sh, "statuses": st, "bayt_al_mal": bayt, "flags": flags}


# Regelvarianten (Grossvater-Regel x Radd-Modus). Radd-Modus: (radd, radd_spouses)
RADD_MODES = [(True, False), (True, True), (False, False)]
VARIANTS = [(g, rs, rd) for g in ("muqasama", "blocks") for (rd, rs) in RADD_MODES]
LEGACY_VARIANTS = [(g, r) for g in ("muqasama", "blocks") for r in (False, True)]   # v1 des Datensatzes (Radd faelschlich als Konsens)


def vname(key):
    if len(key) == 2:
        return f"{key[0]}|radd_spouses={key[1]}"
    g, rs, rd = key
    return f"{g}|radd={'none' if not rd else ('all' if rs else 'blood')}"


def _key(res):
    return (tuple(sorted((k, v) for k, v in res["shares"].items())), res["bayt_al_mal"])


def classify(h: Heirs, legacy: bool = False):
    """-> ('undisputed', res) | ('disputed', {variant: res}) | ('unsupported', grund). legacy=True: nur v1-Varianten (zur Item-Auswahl)."""
    out = {}
    for key in (LEGACY_VARIANTS if legacy else VARIANTS):
        try:
            out[key] = solve(h, key[0], key[1], True if len(key) == 2 else key[2])
        except Unsupported as e:
            return "unsupported", str(e)
    first = (LEGACY_VARIANTS if legacy else VARIANTS)[0]
    if len({_key(v) for v in out.values()}) == 1:
        return "undisputed", out[first]
    return "disputed", out


def to_gold(res) -> dict:
    """JSON-faehige Gold-Form: {schluessel: 'a/b'} inkl. gesperrter Erben ('0'), plus bayt_al_mal falls > 0."""
    g = {k: str(v) for k, v in sorted(res["shares"].items())}
    if res["bayt_al_mal"] > 0:
        g["bayt_al_mal"] = str(res["bayt_al_mal"])
    return g
