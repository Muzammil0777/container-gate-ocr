"""ISO 6346 container code parsing: owner(3) + category(U/J/Z) + serial(6) + check digit(1).

https://en.wikipedia.org/wiki/ISO_6346
"""
import itertools
import re
import string
import unicodedata

# Letter values skip multiples of 11 (A=10, B=12, ... K=21, L=23 ...)
_VALUES, _v = {}, 10
for _ch in string.ascii_uppercase:
    if _v % 11 == 0:
        _v += 1
    _VALUES[_ch], _v = _v, _v + 1
_VALUES.update({str(d): d for d in range(10)})

# Common OCR confusions, applied by position (letters vs digits)
TO_LETTER = {'0': 'OUDQ', '1': 'I', '2': 'Z', '4': 'A', '5': 'S', '6': 'G', '7': 'T', '8': 'B'}
TO_DIGIT = {'O': '0', 'Q': '0', 'D': '0', 'U': '0', 'I': '1', 'L': '1', 'T': '7', 'Z': '2',
            'A': '4', 'S': '5', 'G': '6', 'B': '8'}
# The 4th letter is always U, J or Z, so look-alikes there are safe to map
CATEGORY = {'U': 'U', 'J': 'J', 'Z': 'Z', 'O': 'U', 'D': 'U', 'Q': 'U', '0': 'U', 'V': 'U',
            'I': 'J', '1': 'J', 'T': 'J', '2': 'Z', '7': 'Z'}
SIZE_TYPE = re.compile(r'[0-9LM][0-9][A-Z][0-9]')


def check_digit(code10):
    """Check digit for the first 10 characters (owner + category + serial)."""
    return sum(_VALUES[c] << i for i, c in enumerate(code10)) % 11 % 10


def normalize(text):
    """Uppercase alphanumerics only; folds full-width/circled digits ('２', '④') to ASCII."""
    text = unicodedata.normalize('NFKC', text).upper()
    return ''.join(c for c in text if c in _VALUES)


def _letter_options(c):
    return c if c.isalpha() else TO_LETTER.get(c, '')


def _digit_options(c):
    return c if c.isdigit() else TO_DIGIT.get(c, '')


def parse_window(w):
    """Parse an 11-char window into (code, valid) or None. OCR confusions (0->U, 8->B ...)
    are only applied when the corrected spelling passes the check digit; an unverified
    result must read literally as 4 letters + 7 digits."""
    owner = [_letter_options(c) for c in w[:3]]
    category = CATEGORY.get(w[3], '')
    digits = [_digit_options(c)[:1] for c in w[4:]]
    if not all(owner) or not category or not all(digits):
        return None
    if sum(c.isalpha() for c in w[:4]) < 2:  # digits posing as an owner code -> noise
        return None
    serial = ''.join(digits)
    # ponytail: brute force over confusion combos, tiny (<= 4^4) per window
    for combo in itertools.product(*owner, category):
        code = ''.join(combo) + serial
        if check_digit(code[:10]) == int(code[10]):
            return code, True
    if w[:4].isalpha() and w[3] in 'UJZ' and w[4:].isdigit():
        return w, False
    return None


def _near(a, b):
    """Boxes (x, y, w, h) within ~2 character sizes of each other."""
    size = max(min(a[2], a[3]), min(b[2], b[3]))
    dx = max(0, b[0] - a[0] - a[2], a[0] - b[0] - b[2])
    dy = max(0, b[1] - a[1] - a[3], a[1] - b[1] - b[3])
    return dx <= 2 * size and dy <= 2 * size


def find_codes(texts, boxes=None):
    """Find container codes in OCR'd text pieces (any order). Returns {code: valid}.
    A code whose check digit was not read is returned as e.g. 'YMMU612494?' (not valid).
    With boxes, pieces are only combined when they sit next to each other in the image."""
    near = (lambda a, b: True) if boxes is None else (lambda a, b: _near(a[1], b[1]))
    boxes = boxes if boxes is not None else [None] * len(texts)
    pieces = [(n, b) for n, b in ((normalize(t), b) for t, b in zip(texts, boxes)) if n]
    # Owner and serial are often split into separate boxes in arbitrary order, so also try
    # ordered pairs, plus pairs followed by a lone digit (the boxed check digit).
    singles = [p for p in pieces if len(p[0]) == 1]
    groups = {(p[0],) for p in pieces}
    for a, b in itertools.permutations(pieces, 2):
        if near(a, b):
            groups.add((a[0], b[0]))
            groups.update((a[0], b[0], s[0]) for s in singles if s is not a and near(b, s))
    found = {}
    for g in groups:
        s = ''.join(g)
        edges = set(itertools.accumulate(map(len, g), initial=0))
        for i in range(len(s) - 9):
            # Unverified reads must line up with OCR box edges, or noise from a
            # neighbouring box (e.g. '45G1') gets glued on as a fake check digit.
            aligned = i in edges
            parsed = parse_window(s[i:i + 11]) if i + 11 <= len(s) else None
            if parsed and (parsed[1] or (aligned and i + 11 in edges)):
                found[parsed[0]] = found.get(parsed[0], False) or parsed[1]
            elif aligned and i + 10 in edges and s[i:i + 4].isalpha() and s[i + 3] in 'UJZ' \
                    and s[i + 4:i + 10].isdigit():
                found.setdefault(s[i:i + 10] + '?', False)
    # Prefer the best reading per serial: valid > unverified > missing check digit
    best = {}
    for code, ok in found.items():
        key = code[4:10]
        rank = (ok, not code.endswith('?'))
        if key not in best or rank > best[key][1]:
            best[key] = (code, rank)
    return {code: rank[0] for code, rank in best.values()}


def find_size_type(texts):
    """Find a size/type code like 45G1 / 22G1 (third char 6 is usually OCR'd G)."""
    for t in texts:
        p = normalize(t)
        if len(p) == 4 and p[2] == '6':
            p = p[:2] + 'G' + p[3]
        if SIZE_TYPE.fullmatch(p):
            return p
    return None


def format_code(code):
    """'TRLU6689574' -> 'TRLU 668957 4'"""
    return f"{code[:4]} {code[4:10]} {code[10]}"
