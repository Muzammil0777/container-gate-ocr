from src.iso6346 import check_digit, find_codes, find_size_type, format_code


def test_check_digit():
    assert check_digit('CSQU305438') == 3
    assert check_digit('TRLU668957') == 4
    assert check_digit('BCHU297024') == 9


def test_split_and_out_of_order_tokens():
    # Real RapidOCR outputs from images/
    assert find_codes(['6689574', 'TRLU', '45G1']) == {'TRLU6689574': True}
    assert find_codes(['YMMU', '6124942', '45G1']) == {'YMMU6124942': True}
    assert find_codes(['200841', '2', 'COLU', '22G1']) == {'COLU2008412': True}


def test_confusions_fixed_by_check_digit():
    # Vertical code read with U -> 0
    assert find_codes(['BB002040344']) == {'BBUU2040344': True}
    # 4th letter can only be U/J/Z
    assert find_codes(['TCNO', '6345807']) == {'TCNU6345807': True}
    # Full-width / circled digits
    assert find_codes(['ＴＣＮＵ６３４５８０７']) == {'TCNU6345807': True}


def test_bad_check_digit_is_unverified():
    assert find_codes(['TRLU6689575']) == {'TRLU6689575': False}


def test_missing_check_digit():
    assert find_codes(['YMMU', '612494', '45G1']) == {'YMMU612494?': False}


def test_no_code():
    assert find_codes(['MAX GROSS', '32.500KGS', 'CAUTION']) == {}
    assert find_codes([], []) == {}   # empty frame


def test_far_apart_boxes_not_combined():
    near = [(0, 0, 80, 30), (90, 0, 140, 30)]
    far = [(0, 0, 80, 30), (900, 600, 140, 30)]
    assert find_codes(['TRLU', '6689574'], near) == {'TRLU6689574': True}
    assert find_codes(['TRLU', '6689574'], far) == {}


def test_size_type_and_format():
    assert find_size_type(['TRLU', '4561']) == '45G1'
    assert find_size_type(['２２６１']) == '22G1'
    assert format_code('TRLU6689574') == 'TRLU 668957 4'
