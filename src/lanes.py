"""Gate lanes: the cameras that see the same truck, from cameras.json.

    "lanes":   [{"name": "Entry", "direction": "IN", "location": "Main gate"}],
    "cameras": [{"name": "Entry rear left", "channel": 1, "lane": "Entry", "role": "container"},
                {"name": "Entry ANPR", "channel": 3, "lane": "Entry", "role": "plate"}, ...]

A camera's role says what it reads: "container", "plate" or "both". A camera without a lane
(today's settings) is a lane of its own that reads both, with its own direction and location.
"""
ROLES = ('container', 'plate', 'both')


def lanes(cfg):
    """The lanes to run: [{name, direction, location, cameras: [camera entries with 'role'],
    cams_expected: number of container cameras}]. Switched-off cameras and cameras with an
    unknown role are left out; a camera naming an unknown lane runs as a lane of its own.
    Lanes without any camera are left out."""
    defined = {ln['name']: ln for ln in cfg.get('lanes', []) if ln.get('name')}
    out = {name: {'name': name, 'direction': ln.get('direction', ''), 'location': ln.get('location', ''), 'cameras': []}
           for name, ln in defined.items()}
    for cam in cfg.get('cameras', []):
        if not cam.get('name') or not cam.get('enabled', True):
            continue
        role = cam.get('role', 'both')
        if role not in ROLES:
            continue
        lane = cam.get('lane')
        if lane not in defined:  # today's settings (or a lane that was deleted): the camera alone
            lane = cam['name']
            out.setdefault(lane, {'name': lane, 'direction': cam.get('direction', ''),
                                  'location': cam.get('location', ''), 'cameras': []})
        out[lane]['cameras'].append({**cam, 'role': role})
    result = [ln for ln in out.values() if ln['cameras']]
    for ln in result:
        ln['cams_expected'] = sum(c['role'] in ('container', 'both') for c in ln['cameras'])
    return result


def lane_problems(cfg):
    """Settings that won't work as meant, as (text key, values) for the app to explain."""
    problems = []
    for ln in lanes(cfg):
        roles = {c['role'] for c in ln['cameras']}
        if not roles & {'plate', 'both'}:
            problems.append(('lane_no_plate_camera', {'lane': ln['name']}))
        if not roles & {'container', 'both'}:
            problems.append(('lane_no_container_camera', {'lane': ln['name']}))
    defined = {ln.get('name') for ln in cfg.get('lanes', [])}
    for cam in cfg.get('cameras', []):
        if not cam.get('name') or not cam.get('enabled', True):
            continue
        if 'lane' in cam and cam['lane'] not in defined:
            problems.append(('unknown_lane', {'camera': cam['name'], 'lane': cam['lane']}))
        if cam.get('role', 'both') not in ROLES:
            problems.append(('bad_role', {'camera': cam['name']}))
    return problems
