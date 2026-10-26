"""Arabische Normalisierung - NUR fuer Vergleiche, nie fuer gespeicherte Ground Truth."""
import re, unicodedata
_TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ​-‏‪-‮⁦-⁩﻿]")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = _TASHKEEL.sub("", s).translate(_DIGITS)
    s = s.translate(str.maketrans({"أ":"ا","إ":"ا","آ":"ا","ٱ":"ا","ى":"ي","ة":"ه","ؤ":"و","ئ":"ي"}))
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()
