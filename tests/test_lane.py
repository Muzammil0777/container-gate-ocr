"""LaneTracker: one truck read by several cameras of the same gate lane becomes one event."""
import threading

import numpy as np

from src.gate import LaneTracker

FRAME = np.zeros((100, 200, 3), np.uint8)
LEFT, RIGHT, ANPR = (np.full((100, 200, 3), v, np.uint8) for v in (1, 2, 3))  # tell the photos apart
GOOD = 'MRSU4425761'   # check digit valid
MISREAD = 'MRSU4425161'  # one digit wrong, check digit fails
LANE = [('left', 'container'), ('right', 'container'), ('anpr', 'plate')]


def code(c=GOOD, valid=True, score=0.9):
    return {'code': c, 'valid': valid, 'size_type': '45G1', 'score': score, 'box': (10, 10, 50, 20)}


def plate(digits='3231', letters='UTA', verified=True, score=0.9):
    return {'plate': f'{digits} {letters}', 'digits': digits, 'letters': letters, 'arabic': 'و ط ا ٣٢٣١',
            'verified': verified, 'score': score, 'box': (20, 60, 40, 20)}


FRAMES = {'left': LEFT, 'right': RIGHT, 'anpr': ANPR}


def run(lane, reads):
    """reads: [(now, camera, codes, plates)] -> [(now, event)]"""
    return [(now, e) for now, cam, cs, ps in reads for e in lane.update(cam, cs, FRAMES.get(cam, FRAME), now, ps)]


def quiet(times):
    """Cameras keep sending frames with nothing on them, so a visit can end."""
    return [(s, 'left', [], []) for s in times]


def test_both_container_cameras_read_it_one_verified_event():
    lane = LaneTracker(LANE, min_hits=2)
    events = run(lane, [(0, 'left', [code()], []), (0.2, 'right', [code()], []), (0.5, 'anpr', [], [plate()]),
                        (1, 'left', [code()], []), (1.2, 'right', [code()], []), (1.5, 'anpr', [], [plate()])])
    assert len(events) == 1
    now, e = events[0]
    assert now == 1.5 and e['code']['code'] == GOOD and e['plate']['plate'] == '3231 UTA'
    assert (e['cams_agree'], e['cams_expected']) == (2, 2)
    assert {int(e['frame'][0, 0, 0]), int(e['frame2'][0, 0, 0])} == {1, 2}  # one photo from each angle
    assert int(e['plate_frame'][0, 0, 0]) == 3                               # plate photo from the ANPR camera


def test_one_camera_misreads_a_digit_row_is_right_but_only_one_camera_agreed():
    lane = LaneTracker(LANE, min_hits=2, max_wait_s=10)
    events = run(lane, [(0, 'left', [code()], []), (0, 'right', [code(MISREAD, valid=False)], []),
                        (0, 'anpr', [], [plate()]), (1, 'left', [code()], []),
                        (1, 'right', [code(MISREAD, valid=False)], []), (1, 'anpr', [], [plate()])]
                 + quiet([5, 10]))
    # waited for camera 2 until the lane went quiet (gap_s), then wrote what it had
    assert [(now, e['code']['code'], e['cams_agree']) for now, e in events] == [(10, GOOD, 1)]


def test_second_camera_confirming_late_still_verifies():
    lane = LaneTracker(LANE, min_hits=2, max_wait_s=10)
    events = run(lane, [(0, 'left', [code()], []), (0, 'anpr', [], [plate()]),
                        (1, 'left', [code()], []), (1, 'anpr', [], [plate()]),
                        (4, 'right', [code(MISREAD, valid=False)], []), (6, 'right', [code()], [])])
    assert [(now, e['code']['code'], e['cams_agree']) for now, e in events] == [(6, GOOD, 2)]


def test_plate_first_container_twenty_seconds_later_is_one_truck():
    lane = LaneTracker(LANE, min_hits=2, gap_s=5, pair_window_s=30)
    events = run(lane, [(0, 'anpr', [], [plate()]), (1, 'anpr', [], [plate()])] + quiet([5, 10, 15])
                 + [(20, 'left', [code()], []), (20, 'right', [code()], []),
                    (21, 'left', [code()], []), (21, 'right', [code()], [])])
    assert [(now, e['plate']['plate'], e['code']['code'], e['cams_agree']) for now, e in events] == [(20, '3231 UTA', GOOD, 2)]


def test_container_only_truck_waits_for_the_pair_window():
    lane = LaneTracker(LANE, min_hits=2, gap_s=5, pair_window_s=30)
    events = run(lane, [(0, 'left', [code()], []), (0, 'right', [code()], []),
                        (1, 'left', [code()], []), (1, 'right', [code()], [])] + quiet([10, 20, 29, 30, 31]))
    assert [(now, e['plate'], e['code']['code']) for now, e in events] == [(30, None, GOOD)]


def test_plate_only_truck_waits_for_the_pair_window():
    lane = LaneTracker(LANE, min_hits=2, gap_s=5, pair_window_s=30)
    events = run(lane, [(0, 'anpr', [], [plate('5188', 'VDA')]), (1, 'anpr', [], [plate('5188', 'VDA')])]
                 + quiet([10, 20, 30]))
    assert [(now, e['plate']['plate'], e['code']) for now, e in events] == [(30, '5188 VDA', None)]


def test_next_trucks_plate_closes_the_previous_truck():
    lane = LaneTracker(LANE, min_hits=2, gap_s=5, pair_window_s=30)
    events = run(lane, [(0, 'anpr', [], [plate()]), (1, 'anpr', [], [plate()]),
                        (6, 'anpr', [], [plate('5188', 'VDA')]),  # one read: maybe a far truck, not yet
                        (7, 'anpr', [], [plate('5188', 'VDA')]),  # confirmed: the next truck is here
                        (9, 'left', [code('ECMU5468326')], []), (9, 'right', [code('ECMU5468326')], []),
                        (10, 'left', [code('ECMU5468326')], []), (10, 'right', [code('ECMU5468326')], [])])
    assert [(now, e['plate']['plate'], e['code'] and e['code']['code']) for now, e in events] == [
        (7, '3231 UTA', None), (9, '5188 VDA', 'ECMU5468326')]  # both cameras read it at 9: confirmed


def test_cameras_only_count_what_they_are_meant_to_read():
    lane = LaneTracker(LANE, min_hits=2)
    events = run(lane, [(0, 'left', [code()], [plate('9999', 'XXX')]), (0, 'right', [code()], []),
                        (0, 'anpr', [code('TCNU6345807')], [plate()]),
                        (1, 'left', [code()], [plate('9999', 'XXX')]), (1, 'right', [code()], []),
                        (1, 'anpr', [code('TCNU6345807')], [plate()])])
    assert [(e['plate']['plate'], e['code']['code']) for _, e in events] == [('3231 UTA', GOOD)]


def test_cameras_in_their_own_threads_give_one_event():
    lane = LaneTracker(LANE, min_hits=2, max_wait_s=100, gap_s=100)
    events, lock = [], threading.Lock()

    def camera(name, codes, plates):
        for i in range(50):
            got = lane.update(name, codes, FRAMES[name], i * 0.1, plates)
            with lock:
                events.extend(got)

    threads = [threading.Thread(target=camera, args=a) for a in
               (('left', [code()], []), ('right', [code()], []), ('anpr', [], [plate()]))]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(events) + len(lane.flush(10)) == 1
