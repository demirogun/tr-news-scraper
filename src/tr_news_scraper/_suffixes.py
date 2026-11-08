"""Stem mode: a Turkish root plus inflectional suffixes, in their fixed order.

    root + plural? + possessive? + case? + (ki | copula)?

The order is what keeps look-alikes out: "selam" would be sel + dative "a" + 1st-person "m", but
nothing may follow a case ending except -ki or the copula. Right after the root, the suffix set
depends on whether the root ends in a vowel; after a plural or possessive, any case ending is
accepted. Vowel harmony isn't enforced, because wrong-harmony forms don't occur in real text.

A root ending in p, ç, t or k may soften to b, c, d or ğ (g after n) before a suffix that starts
with a vowel: obruk → obruğu, ağaç → ağacı, renk → rengi.

Every pattern is built from alternations of fixed strings with no nested quantifiers, so matching
time is linear in the length of the text.
"""

from __future__ import annotations

import re

VOWELS = "aeıioöuüâîû"
VOWEL_CLASS = f"[{VOWELS}]"

PLURAL = ("ler", "lar")
POSSESSIVE_AFTER_CONSONANT = (
    *("im", "ım", "um", "üm", "in", "ın", "un", "ün", "i", "ı", "u", "ü"),
    *("imiz", "ımız", "umuz", "ümüz", "iniz", "ınız", "unuz", "ünüz", "leri", "ları"),
)
POSSESSIVE_AFTER_VOWEL = (
    *("m", "n", "si", "sı", "su", "sü"),
    *("miz", "mız", "muz", "müz", "niz", "nız", "nuz", "nüz", "leri", "ları"),
)
CASE_AFTER_CONSONANT = (
    *("i", "ı", "u", "ü", "e", "a", "de", "da", "te", "ta"),
    *("den", "dan", "ten", "tan", "in", "ın", "un", "ün", "le", "la"),
)
CASE_AFTER_VOWEL = (
    *("yi", "yı", "yu", "yü", "ye", "ya", "de", "da", "den", "dan"),
    *("nin", "nın", "nun", "nün", "yle", "yla"),
)
CASE_AFTER_POSSESSIVE = (
    *("ni", "nı", "nu", "nü", "ne", "na", "nde", "nda", "nden", "ndan"),
    *("nin", "nın", "nun", "nün", "yle", "yla", "de", "da", "den", "dan"),
)
LAST = ("ki", "dir", "dır", "dur", "dür", "tir", "tır", "tur", "tür")
_SOFTENING = {"p": "b", "ç": "c", "t": "d", "k": "ğ"}


def softened(root: str) -> str | None:
    """The root with its final p, ç, t or k softened (``renk`` → ``reng``), or ``None``."""
    last = root[-1]
    if last not in _SOFTENING:
        return None
    replacement = "g" if root.endswith("nk") else _SOFTENING[last]
    return root[:-1] + replacement


def stem_pattern(root: str) -> str:
    """Regex source (without word boundaries) for ``root`` plus inflectional suffixes."""
    pattern = re.escape(root) + _suffixes(ends_in_vowel=root[-1] in VOWELS)
    soft = softened(root)
    if soft is None:
        return pattern
    return f"(?:{pattern}|{re.escape(soft)}(?={VOWEL_CLASS}){_suffixes(ends_in_vowel=False)})"


def prefix_pattern(root: str) -> str:
    """Regex source for any word starting with ``root`` or, before a vowel, its softened form."""
    soft = softened(root)
    start = (
        re.escape(root)
        if soft is None
        else f"(?:{re.escape(root)}|{re.escape(soft)}(?={VOWEL_CLASS}))"
    )
    return start + r"[^\W_]*"


def _suffixes(*, ends_in_vowel: bool) -> str:
    possessive = POSSESSIVE_AFTER_VOWEL if ends_in_vowel else POSSESSIVE_AFTER_CONSONANT
    case = CASE_AFTER_VOWEL if ends_in_vowel else CASE_AFTER_CONSONANT
    any_case = (*CASE_AFTER_CONSONANT, *CASE_AFTER_VOWEL, *CASE_AFTER_POSSESSIVE)
    after_plural = f"{_any(PLURAL)}{_any(POSSESSIVE_AFTER_CONSONANT)}?{_any(any_case)}?"
    after_possessive = f"{_any(possessive)}{_any(any_case)}?"
    return f"(?:{after_plural}|{after_possessive}|{_any(case)})?{_any(LAST)}?"


def _any(options: tuple[str, ...]) -> str:
    """A non-capturing alternation, longest option first."""
    unique = sorted(set(options), key=lambda option: (-len(option), option))
    return "(?:" + "|".join(re.escape(option) for option in unique) + ")"
