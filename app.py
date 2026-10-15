"""Streamlit demo for testing the recognizer:  streamlit run app.py"""
import json
import tempfile
import time
from pathlib import Path

# Must be imported before pandas: on Windows, pandas/pyarrow loads an older MSVC runtime DLL
# that makes onnxruntime fail with "DLL load failed while importing onnxruntime_pybind11_state".
from src.recognizer import Recognizer, draw  # noqa: I001
from src.camera import hikvision_url, open_capture, port_open
from cctv import LiveManager, _safe
from src.gate import COLUMNS, LINKS, ExcelLog, GateTracker
from src.i18n import LANGUAGES, t
from src.iso6346 import format_code

import cv2
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Container & Plate Gate OCR', page_icon='🚛', layout='wide')


@st.cache_resource(max_entries=2)  # each model copy is ~100 MB; free hosting has ~1 GB
def get_recognizer(max_side):
    return Recognizer(max_side=max_side)


def rgb(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def codes_table(codes, L):
    return pd.DataFrame([{
        t('col_code', L): format_code(c['code']),
        t('col_check', L): t('valid', L) if c['valid'] else t('unreadable' if c['code'].endswith('?') else 'mismatch', L),
        t('size_type', L): c['size_type'] or '',
        t('confidence', L): c['score'],
    } for c in codes])


def plates_table(plates, L):
    return pd.DataFrame([{
        t('plate', L): p['plate'],
        t('plate_ar', L): p['arabic'],
        t('col_plate_check', L): t('verified' if p['verified'] else 'latin_only', L),
        t('confidence', L): p['score'],
    } for p in plates])


def show_result(img, out, L):
    left, right = st.columns([3, 2])
    left.image(rgb(draw(img.copy(), out['codes'], out['plates'])), use_container_width=True)
    with right:
        st.metric(t('ocr_time', L), f"{out['ms']} {t('ms', L)}")
        if out['codes']:
            st.dataframe(codes_table(out['codes'], L), hide_index=True, use_container_width=True)
        else:
            st.warning(t('no_code', L))
        if out['plates']:
            st.dataframe(plates_table(out['plates'], L), hide_index=True, use_container_width=True)
        elif read_plates:
            st.info(t('no_plate', L))
        with st.expander(t('all_text', L)):
            st.write(out['texts'])


with st.sidebar:
    L = st.radio('🌐', list(LANGUAGES), format_func=LANGUAGES.get, horizontal=True,
                 label_visibility='collapsed')
    st.title('🚛 ' + t('title', L))
    st.caption(t('subtitle', L))
    max_side = st.select_slider(t('max_side', L), [960, 1280, 1600, 1920, 2560], value=1920,
                                help=t('max_side_help', L))
    zoom = st.toggle(t('zoom', L), value=True, help=t('zoom_help', L))
    vertical = st.toggle(t('vertical', L), value=True, help=t('vertical_help', L))
    read_plates = st.toggle(t('read_plates', L), value=True)
    st.markdown(t('legend', L))

if L == 'ar':  # right-to-left layout for Arabic
    st.markdown('<style>[data-testid="stAppViewContainer"], [data-testid="stSidebar"] '
                '{direction: rtl; text-align: right;}</style>', unsafe_allow_html=True)

recognizer = get_recognizer(max_side)
opts = dict(zoom=zoom, vertical=vertical, plates=read_plates)
tab_live, tab_img, tab_vid, tab_cam, tab_log = st.tabs(
    [t(k, L) for k in ('tab_live', 'tab_image', 'tab_video', 'tab_camera', 'tab_log')])


def latest_rows(n=10):
    """Newest rows of the most recently written gate log (None if there is none yet)."""
    logs = sorted(Path('logs').glob('*.xlsx'), key=lambda p: p.stat().st_mtime)
    if not logs:
        return None
    try:
        df = pd.read_excel(logs[-1])
    except Exception:  # being written by cctv.py right now; next refresh will get it
        return None
    links = {t(k, x) for k in LINKS for x in LANGUAGES}
    return df.drop(columns=[c for c in df.columns if c in links]).tail(n).iloc[::-1]


CONFIG = Path('cameras.json')


def load_config():
    try:
        return json.loads(CONFIG.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_config(nvr, cam, language):
    """Remember the NVR and this camera in cameras.json (also used by cctv.py) and start it
    automatically next time the app opens."""
    cfg = load_config()
    cfg.update(nvr=nvr, language=language, autostart=True)
    cfg['cameras'] = [c for c in cfg.get('cameras', []) if c.get('name') != cam['name']] + [cam]
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


@st.cache_resource
def live_manager():
    """One camera runner for the whole app process: it survives page reloads and keeps
    detecting with the browser closed. Saved cameras start automatically."""
    cfg = load_config()
    manager = LiveManager(cfg)
    if cfg.get('autostart'):
        for cam in cfg.get('cameras', []):
            try:
                manager.start(cam)
            except Exception as e:  # one bad camera entry shouldn't stop the others
                print(f"[app] could not start {cam.get('name')}: {e}")
    return manager


with tab_live:
    manager = live_manager()
    saved = load_config()
    nvr, cams = saved.get('nvr', {}), saved.get('cameras') or [{}]
    running = manager.running()
    with st.expander(t('add_camera', L), expanded=not running):
        with st.form('start_camera'):
            a, b, c, d = st.columns([3, 2, 2, 1.4])
            ip = a.text_input(t('nvr_ip', L), nvr.get('ip', ''), placeholder='192.168.1.64')
            user = b.text_input(t('nvr_user', L), nvr.get('user', 'admin'))
            password = c.text_input(t('nvr_password', L), nvr.get('password', ''), type='password')
            channel = d.number_input(t('nvr_channel', L), 1, 64, int(cams[0].get('channel', 1)))
            e, f, g = st.columns([2, 1.4, 3])
            name = e.text_input(t('camera_name', L), cams[0].get('name', 'Gate 1'))
            direction = f.selectbox(t('direction', L), ['IN', 'OUT'], format_func=lambda x: t(x, L),
                                    index=['IN', 'OUT'].index(cams[0].get('direction', 'IN')))
            location = g.text_input(t('location', L), cams[0].get('location', ''))
            h, k = st.columns(2)
            langs = list(LANGUAGES)
            excel_lang = h.selectbox(t('excel_language', L), langs, format_func=LANGUAGES.get,
                                     index=langs.index(saved.get('language', L)))
            remember = k.checkbox(t('remember', L), True, help=t('remember_help', L))
            go = st.form_submit_button(t('start_camera', L), type='primary')
    if go:
        nvr = {'ip': ip.strip(), 'user': user.strip(), 'password': password, 'port': nvr.get('port', 554)}
        cam = {'name': name.strip() or 'Gate 1', 'channel': int(channel), 'direction': direction,
               'location': location.strip()}
        if not nvr['ip'] or not password:
            st.error(t('no_video', L))
        elif not port_open(nvr['ip'], nvr['port']):
            st.error(t('unreachable', L, ip=nvr['ip']))
        else:
            manager.start(cam, nvr, excel_lang)
            if remember:
                save_config(nvr, cam, excel_lang)
            st.success(t('started', L, name=cam['name']))
            running = manager.running()
    if running:
        st.caption(t('live_hint', L))
        for cam_name, cam in running.items():
            a, b = st.columns([6, 1])
            where = [t(cam.get('direction', 'IN'), L), cam.get('location', '')]
            if 'channel' in cam:
                where.append(f"{t('nvr_channel', L)} {cam['channel']}")
            a.markdown(f"🟢 **{cam_name}** · " + ' · '.join(x for x in where if x))
            if b.button(t('stop', L), key=f'stop_{cam_name}'):
                manager.stop(cam_name)
                st.rerun()

    @st.fragment(run_every=2)
    def live_view():
        frames = sorted(Path('logs/live').glob('*.jpg'))
        waiting = [n for n in manager.running() if not (Path('logs/live') / f"{_safe(n)}.jpg").exists()]
        for n in waiting:
            st.info(t('connecting', L, name=n))
        if not frames:
            if not waiting:
                st.info(t('no_live', L))
            return
        cols = st.columns(min(2, len(frames)))
        for i, p in enumerate(frames):
            age = int(time.time() - p.stat().st_mtime)
            with cols[i % len(cols)]:
                st.image(p.read_bytes(), caption=f"{p.stem.replace('_', ' ')} · {t('updated', L, s=age)}",
                         use_container_width=True)
                if age > 30:
                    st.warning(t('stale', L, s=age))
        rows = latest_rows()
        if rows is not None:
            st.subheader(t('latest_rows', L))
            st.dataframe(rows, hide_index=True, use_container_width=True)

    live_view()

with tab_img:
    files = st.file_uploader(t('upload_images', L), type=['jpg', 'jpeg', 'png', 'bmp', 'webp'],
                             accept_multiple_files=True)
    samples = sorted(str(p) for p in Path('images').iterdir()
                     if p.suffix.lower() in ('.png', '.jpg', '.jpeg')) + ['demo_input.jpg']
    default = next((s for s in samples if 'ksa_' in s), 'demo_input.jpg')
    sample = None if files else st.selectbox(t('try_sample', L), samples, index=samples.index(default))
    images = [(f.name, cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)) for f in files] \
        if files else [(sample, cv2.imread(sample))]
    for name, img in images:
        st.subheader(name)
        if img is None:
            st.error(t('bad_image', L))
            continue
        show_result(img, recognizer(img, **opts), L)

with tab_vid:
    st.caption(t('video_caption', L))
    video = st.file_uploader(t('upload_video', L), type=['mp4', 'avi', 'mov', 'mkv'])
    c1, c2, c3, c4 = st.columns(4)
    fps = c1.slider(t('fps', L), 0.5, 5.0, 2.0, 0.5)
    min_hits = c2.slider(t('min_hits', L), 1, 5, 2)
    direction = c3.selectbox(t('direction', L), ['IN', 'OUT'], format_func=lambda d: t(d, L))
    location = c4.text_input(t('location', L), t('demo_gate', L))
    if video and st.button(t('process_video', L), type='primary'):
        work = Path(tempfile.mkdtemp())
        src = work / video.name
        src.write_bytes(video.read())
        cap = cv2.VideoCapture(str(src))
        vfps = cap.get(cv2.CAP_PROP_FPS) or 25
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        step = max(1, round(vfps / fps))
        tracker = GateTracker(min_hits=min_hits)
        log = ExcelLog(str(work / 'gate_log.xlsx'), work / 'snapshots', L)
        bar, preview, rows, n, t0 = st.progress(0.0), st.empty(), [], 0, time.time()

        def add(events):
            for e in events:
                rows.append(log.log(e, 'Video demo', location, direction))

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            n += 1
            if n % step:
                continue
            out = recognizer(frame, **opts)
            add(tracker.update(out['codes'], frame, n / vfps, out['plates']))
            preview.image(rgb(draw(frame, out['codes'], out['plates'])), caption=f"{n / vfps:.1f} s",
                          use_container_width=True)
            bar.progress(min(1.0, n / total))
        add(tracker.flush(n / vfps))
        bar.progress(1.0, text=t('done', L, s=f'{time.time() - t0:.0f}', n=len(rows)))
        if rows:
            df = pd.DataFrame(rows)[[c for c in COLUMNS if c not in LINKS]]
            st.dataframe(df.rename(columns=lambda c: t(c, L)), hide_index=True, use_container_width=True)
            cols = st.columns(min(4, len(rows)))
            for i, row in enumerate(rows):
                cols[i % len(cols)].image(row['snapshot'], caption=' · '.join(
                    x for x in (row['plate'], row['container']) if x))
            xlsx = next(work.glob('*.xlsx'))
            st.download_button(t('download_excel', L), xlsx.read_bytes(), 'gate_log.xlsx')
        else:
            st.info(t('no_truck', L))

with tab_cam:
    st.caption(t('camera_caption', L))
    mode = st.radio(t('conn_mode', L), ['nvr', 'url'], horizontal=True,
                    format_func=lambda m: t(f'{m}_mode', L))
    if mode == 'nvr':
        a, b, c, d = st.columns([3, 2, 2, 1])
        ip = a.text_input(t('nvr_ip', L), placeholder='192.168.1.64')
        user = b.text_input(t('nvr_user', L), 'admin')
        password = c.text_input(t('nvr_password', L), type='password')
        channel = d.number_input(t('nvr_channel', L), 1, 64, 1)
        source = hikvision_url(ip.strip(), user, password, channel) if ip and password else ''
    else:
        source = st.text_input(t('camera_source', L),
                               placeholder='rtsp://user:password@192.168.1.64:554/Streaming/Channels/101')
    if source and st.button(t('grab_frame', L)):
        if mode == 'nvr' and not port_open(ip.strip(), 554):
            st.error(t('unreachable', L, ip=ip))
            st.stop()
        cap = open_capture(int(source) if source.isdigit() else source)
        frame = None
        for _ in range(5):  # skip stale buffered frames
            ok, f = cap.read()
            frame = f if ok else frame
        cap.release()
        if frame is None:
            st.error(t('no_video' if mode == 'nvr' else 'camera_error', L))
        else:
            st.success(t('camera_ok', L, w=frame.shape[1], h=frame.shape[0]))
            show_result(frame, recognizer(frame, **opts), L)

with tab_log:
    logs = sorted(Path('logs').glob('*.xlsx'), reverse=True)
    if not logs:
        st.info(t('no_log', L))
    else:
        path = st.selectbox(t('workbook', L), logs, format_func=lambda p: p.name)
        df = pd.read_excel(path)
        df = df.drop(columns=[c for c in df.columns if c in {t(k, x) for k in LINKS for x in LANGUAGES}])
        dir_col = next((c for c in df.columns if c in {t('direction', x) for x in LANGUAGES}), None)
        a, b, c = st.columns(3)
        a.metric(t('events', L), len(df))
        if dir_col:
            b.metric(t('IN', L), int(df[dir_col].isin([t('IN', x) for x in LANGUAGES]).sum()))
            c.metric(t('OUT', L), int(df[dir_col].isin([t('OUT', x) for x in LANGUAGES]).sum()))
        st.dataframe(df.iloc[::-1], hide_index=True, use_container_width=True)
        snaps = sorted((p for p in Path('logs/snapshots').rglob('*.jpg') if not p.stem.endswith('_plate')),
                       key=lambda p: p.stat().st_mtime, reverse=True)[:8]
        if snaps:
            st.subheader(t('latest_snapshots', L))
            cols = st.columns(4)
            for i, p in enumerate(snaps):
                cols[i % 4].image(str(p), caption=p.stem.replace('_', ' '))
