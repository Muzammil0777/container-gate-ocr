"""Saudi Arabia number plates: 1-4 digits + 3 letters, printed twice on the plate
(Arabic on the top row, Latin on the bottom row). Only 17 letters are used, each with a
fixed Arabic <-> Latin pair, so the two rows can confirm each other.
"""
import re
import unicodedata

LATIN_TO_ARABIC = {'A': 'ا', 'B': 'ب', 'J': 'ح', 'D': 'د', 'R': 'ر', 'S': 'س', 'X': 'ص', 'T': 'ط',
                   'E': 'ع', 'G': 'ق', 'K': 'ك', 'L': 'ل', 'Z': 'م', 'N': 'ن', 'H': 'ه', 'U': 'و',
                   'V': 'ى'}
ARABIC_DIGITS = '٠١٢٣٤٥٦٧٨٩'
# Look-alikes the OCR produces, mapped to what can actually be on a plate
# Only letter-for-letter fixes: turning digits into letters ('5' -> 'S') builds fake plates out
# of container numbers ('69395' + 'SU' -> '6939 SSU'); several reads of a real plate fix that instead.
LETTER_FIX = {'O': 'D', 'Q': 'G', 'C': 'G', 'Y': 'V', 'F': 'E'}
DIGIT_FIX = {'O': '0', 'D': '0', 'Q': '0', 'I': '1', 'L': '1', 'S': '5', 'B': '8', 'Z': '2',
             'G': '6', 'T': '7', 'A': '4'}
# Arabic model confusions on plate letters: alef/1, waw/9, heh/5, ain/4
ARABIC_LETTER_FIX = {'١': 'ا', '٩': 'و', '٥': 'ه', '٤': 'ع', 'ي': 'ى', 'ی': 'ى', 'أ': 'ا', 'إ': 'ا',
                     'ة': 'ه', 'ھ': 'ه'}


def parse_latin(text):
    """'5188VDA', '5188 VOA' -> ('5188', 'VDA'); None if it can't be a Saudi plate.
    Expects one OCR box (or two adjacent boxes joined), not free text."""
    if re.search(r'[.,:/]', text):  # weights/volumes like '8.160 LBS' are not plates
        return None
    s = ''.join(c for c in unicodedata.normalize('NFKC', text).upper() if c.isalnum())
    digits, letters = s[:-3], s[-3:]  # Latin row: digits on the left, letters on the right
    if not 1 <= len(digits) <= 4:
        return None
    if sum(c.isdigit() for c in digits) < max(1, len(digits) - 1) or sum(c.isalpha() for c in letters) < 2:
        return None  # mostly-wrong-type characters: noise, not a plate
    d = ''.join(c if c.isdigit() else DIGIT_FIX.get(c, '?') for c in digits)
    l = ''.join(c if c in LATIN_TO_ARABIC else LETTER_FIX.get(c, '?') for c in letters)
    return None if '?' in d + l else (d, l)


def to_arabic(digits, letters):
    """('5188', 'VDA') -> 'ى د ا ٥١٨٨' (logical order; displays like the plate in RTL text)."""
    ar_digits = ''.join(ARABIC_DIGITS[int(d)] for d in digits)
    return ' '.join(LATIN_TO_ARABIC[c] for c in letters) + ' ' + ar_digits


def arabic_matches(texts, digits, letters):
    """True if the Arabic-row OCR texts confirm the Latin reading: the digits appear in
    Arabic numerals and the 3 letters' Arabic forms appear in order (junk in between is
    tolerated). Texts may be the whole top row and/or its halves."""
    want_digits = ''.join(ARABIC_DIGITS[int(d)] for d in digits)
    want_letters = [LATIN_TO_ARABIC[c] for c in letters]
    digits_ok = letters_ok = False
    for t in texts:
        t = ''.join(t.split())
        rest = t
        if want_digits in t:
            digits_ok = True
            rest = t.replace(want_digits, '', 1)
        found = [ARABIC_LETTER_FIX.get(c, c) for c in rest]
        letters_ok = letters_ok or _subsequence(want_letters, found) or _subsequence(want_letters, found[::-1])
    return digits_ok and letters_ok


def _subsequence(want, seq):
    it = iter(seq)
    return all(c in it for c in want)


def format_plate(digits, letters):
    return f"{digits} {letters}"
