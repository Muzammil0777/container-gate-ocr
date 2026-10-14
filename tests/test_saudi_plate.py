from src.saudi_plate import arabic_matches, parse_latin, to_arabic


def test_parse_latin_real_reads():
    assert parse_latin('5489EXA') == ('5489', 'EXA')
    assert parse_latin('3231 UTA') == ('3231', 'UTA')
    assert parse_latin('5188VOA') == ('5188', 'VDA')    # O is not a plate letter -> D
    assert parse_latin('12 ABJ') == ('12', 'ABJ')


def test_parse_latin_rejects_noise():
    for text in ['8.160 LBS', '63.490 LBS', 'CU.M', '52:200', 'LBJ', '45G1', 'Naqleen C',
                 'TRLU6689574', '2012', 'ECMO', '12345ABC', 'MAX', 'TARE', 'CUBE', 'ABCD', 'BBU4', 'EXA5489']:
        assert parse_latin(text) is None, text


def test_to_arabic():
    assert to_arabic('5188', 'VDA') == 'ى د ا ٥١٨٨'
    assert to_arabic('3231', 'UTA') == 'و ط ا ٣٢٣١'


def test_arabic_cross_check_with_real_model_output():
    # PP-OCRv5 Arabic reads of the real plates' top rows (alef read as ١, waw as ٩)
    assert arabic_matches(['٣٢٣١٩٥ط١'], '3231', 'UTA')
    assert arabic_matches(['٥٤٨٩ ٤م ١', 'ع ص١'], '5489', 'EXA')   # digits from row, letters from half
    assert not arabic_matches(['٥٤٨٩ ٤م ١'], '5489', 'EXA')       # letters not confirmed
    assert not arabic_matches(['٣٢٣١٩٥ط١'], '3231', 'UTB')        # wrong letter
    assert not arabic_matches(['٣٢٣٩٥ط١'], '3231', 'UTA')         # wrong digits
