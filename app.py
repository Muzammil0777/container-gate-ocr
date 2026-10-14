"""Streamlit demo for testing the recognizer:  streamlit run app.py"""
import tempfile
import time
from pathlib import Path

# Must be imported before pandas: on Windows, pandas/pyarrow loads an older MSVC runtime DLL
# that makes onnxruntime fail with "DLL load failed while importing onnxruntime_pybind11_state".
from src.recognizer import Recognizer, draw  # noqa: I001
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
tab_img, tab_vid, tab_cam, tab_log = st.tabs([t(k, L) for k in ('tab_image', 'tab_video', 'tab_camera', 'tab_log')])

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
    source = st.text_input(t('camera_source', L),
                           placeholder='rtsp://user:password@192.168.1.64:554/Streaming/Channels/101')
    if source and st.button(t('grab_frame', L)):
        cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
        frame = None
        for _ in range(5):  # skip stale buffered frames
            ok, f = cap.read()
            frame = f if ok else frame
        cap.release()
        if frame is None:
            st.error(t('camera_error', L))
        else:
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
