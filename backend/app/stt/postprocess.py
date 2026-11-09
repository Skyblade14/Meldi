"""Nachbearbeitung der Whisper-Ausgabe: Halluzinationen filtern, Schreibweisen korrigieren, Empfänger zuordnen."""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.stt.base import Segment
from app.stt.vocabulary import ABKUERZUNGEN

# Whisper wurde u.a. auf Untertiteln trainiert und „erfindet" bei Stille/Rauschen gern solche Sätze.
HALLUZINATIONEN = [
    r"untertitel(ung)?( im auftrag)? (des|der|von) .*",
    r"untertitel von .*",
    r"(vielen )?dank (für|fürs) (das )?zuschauen.*",
    r"bis zum nächsten mal.*",
    r"tschüss.*",
    r"amara\.org.*",
    r"copyright .*",
    r"swr \d+.*",
    r"\.+",
]
_HALLUZINATION_RE = re.compile(r"^\s*(" + "|".join(HALLUZINATIONEN) + r")\s*[.!]?\s*$", re.IGNORECASE)
_ABK_RE = re.compile(r"\b(" + "|".join(re.escape(a) for a in ABKUERZUNGEN) + r")\b", re.IGNORECASE)
_ABK_MAP = {a.lower(): a for a in ABKUERZUNGEN}


def is_hallucinated_segment(seg: Segment) -> bool:
    if not seg.text or _HALLUZINATION_RE.match(seg.text):
        return True
    # Whisper ist sich selbst unsicher, dass überhaupt gesprochen wurde.
    return seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return _ABK_RE.sub(lambda m: _ABK_MAP[m.group(0).lower()], text)


def entferne_wiederholungen(text: str) -> str:
    """Nur für das Feld „An“: Whisper (v.a. large-v3-turbo) wiederholt kurze Eingaben gern in einer Schleife
    („Einsatzabschnitt, Brand, Einsatzabschnitt, Brand.“). Direkt aufeinanderfolgende gleiche Wortfolgen
    werden auf eine reduziert. Im Inhalt nicht anwenden, dort können Wiederholungen gewollt sein."""
    words = text.split()
    key = [re.sub(r"[^\wäöüß]", "", w.lower()) for w in words]
    changed = True
    while changed:
        changed = False
        for n in range(len(words) // 2, 0, -1):
            for i in range(len(words) - 2 * n + 1):
                if key[i:i + n] == key[i + n:i + 2 * n]:
                    del words[i + n:i + 2 * n], key[i + n:i + 2 * n]
                    changed = True
                    break
            if changed:
                break
    result = " ".join(words)
    # Satzzeichen am Ende der verbliebenen Folge vereinheitlichen („Brand,“ → „Brand.“)
    return re.sub(r"[,;]$", ".", result) if result != text else result


# --- Empfänger-Zuordnung -------------------------------------------------------------------

_FUELLWOERTER = re.compile(r"^(an|zu|für|nach)\s+(die|den|das|der)?\s*", re.IGNORECASE)


def _normalize(text: str) -> str:
    text = text.lower().replace("-", " ")
    text = re.sub(r"[^\wäöüß ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _FUELLWOERTER.sub("", text).strip()


def expand_aliases(name: str, aliases: list[str]) -> list[str]:
    """Erzeugt gesprochene Varianten: „EA Brand" → „Einsatzabschnitt Brand", „Abschnitt Brand"."""
    variants = [name, *aliases]
    m = re.match(r"^EA\s+(.+)$", name, re.IGNORECASE)
    if m:
        variants += [f"Einsatzabschnitt {m.group(1)}", f"Abschnitt {m.group(1)}"]
    return variants


@dataclass
class FunktionMatch:
    funktion_id: int
    name: str
    score: float


def match_funktion(spoken: str, funktionen: list[tuple[int, str, list[str]]], limit: int = 3) -> list[FunktionMatch]:
    """Ordnet einen gesprochenen Empfänger den bekannten Funktionen zu (bestes Ergebnis zuerst)."""
    query = _normalize(spoken)
    if not query:
        return []
    matches = []
    for fid, name, aliases in funktionen:
        score = max(fuzz.ratio(query, _normalize(v)) for v in expand_aliases(name, aliases))
        matches.append(FunktionMatch(fid, name, round(score, 1)))
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:limit]
