"""Gate lanes from cameras.json: which cameras read the same truck, and what each one reads."""
from src.lanes import lane_problems, lanes


def test_todays_settings_give_one_lane_per_camera():
    cfg = {'cameras': [{'name': 'Gate 1 Entry', 'channel': 1, 'direction': 'IN', 'location': 'Main gate'},
                       {'name': 'Gate 1 Exit', 'channel': 2, 'direction': 'OUT'},
                       {'name': 'Old', 'channel': 3, 'enabled': False}]}
    got = lanes(cfg)
    assert [(ln['name'], ln['direction'], ln['location'], [c['name'] for c in ln['cameras']]) for ln in got] == [
        ('Gate 1 Entry', 'IN', 'Main gate', ['Gate 1 Entry']),
        ('Gate 1 Exit', 'OUT', '', ['Gate 1 Exit'])]
    assert [c['role'] for ln in got for c in ln['cameras']] == ['both', 'both']
    assert [ln['cams_expected'] for ln in got] == [1, 1]
    assert lane_problems(cfg) == []
    assert lanes({}) == []


def test_a_lane_with_two_container_cameras_and_a_plate_camera():
    cfg = {'lanes': [{'name': 'Entry', 'direction': 'IN', 'location': 'Main gate'}],
           'cameras': [{'name': 'Entry rear left', 'channel': 1, 'lane': 'Entry', 'role': 'container'},
                       {'name': 'Entry rear right', 'channel': 2, 'lane': 'Entry', 'role': 'container'},
                       {'name': 'Entry ANPR', 'channel': 3, 'lane': 'Entry', 'role': 'plate'},
                       {'name': 'Exit', 'channel': 4, 'direction': 'OUT'}]}
    entry, exit_ = lanes(cfg)
    assert (entry['name'], entry['direction'], entry['location'], entry['cams_expected']) == ('Entry', 'IN', 'Main gate', 2)
    assert [(c['name'], c['role']) for c in entry['cameras']] == [
        ('Entry rear left', 'container'), ('Entry rear right', 'container'), ('Entry ANPR', 'plate')]
    assert (exit_['name'], exit_['cams_expected']) == ('Exit', 1)
    assert lane_problems(cfg) == []


def test_switched_off_cameras_leave_the_lane():
    cfg = {'lanes': [{'name': 'Entry', 'direction': 'IN'}],
           'cameras': [{'name': 'A', 'lane': 'Entry', 'role': 'container'},
                       {'name': 'B', 'lane': 'Entry', 'role': 'container', 'enabled': False},
                       {'name': 'P', 'lane': 'Entry', 'role': 'plate'}]}
    [entry] = lanes(cfg)
    assert [c['name'] for c in entry['cameras']] == ['A', 'P'] and entry['cams_expected'] == 1


def test_problems_are_reported_as_text_keys():
    cfg = {'lanes': [{'name': 'Entry', 'direction': 'IN'}, {'name': 'Exit', 'direction': 'OUT'},
                     {'name': 'Empty', 'direction': 'IN'}],
           'cameras': [{'name': 'A', 'lane': 'Entry', 'role': 'container'},
                       {'name': 'B', 'lane': 'Exit', 'role': 'plate'},
                       {'name': 'C', 'lane': 'Nowhere', 'role': 'both'},
                       {'name': 'D', 'lane': 'Exit', 'role': 'sideways'}]}
    assert lane_problems(cfg) == [
        ('lane_no_plate_camera', {'lane': 'Entry'}),
        ('lane_no_container_camera', {'lane': 'Exit'}),
        ('unknown_lane', {'camera': 'C', 'lane': 'Nowhere'}),
        ('bad_role', {'camera': 'D'}),
    ]
    assert [ln['name'] for ln in lanes(cfg)] == ['Entry', 'Exit', 'C']  # C still runs, as its own lane
