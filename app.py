"""Streamlit demo for testing the recognizer:  streamlit run app.py"""
import tempfile
import time
from pathlib import Path

# Must be imported before pandas: on Windows, pandas/pyarrow loads an older MSVC runtime DLL
# that makes onnxruntime fail with "DLL load failed while importing onnxruntime_pybind11_state".
from src.recognizer import Recognizer, draw  # noqa: I001
from src.gate import ExcelLog, GateTracker
from src.iso6346 import format_code

import cv2
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Container Code Recognition', page_icon='🚛', layout='wide')


@st.cache_resource
def get_recognizer(max_side):
    return Recognizer(max_side=max_side)


def rgb(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def codes_table(codes):
    return pd.DataFrame([{
        'Container code': format_code(c['code']),
        'Check digit': '✅ valid' if c['valid'] else ('❔ not readable' if c['code'].endswith('?') else '⚠️ mismatch'),
        'Size/Type': c['size_type'] or '',
        'Confidence': c['score'],
    } for c in codes])


def show_result(img, out):
    left, right = st.columns([3, 2])
    left.image(rgb(draw(img.copy(), out['codes'])), use_container_width=True)
    with right:
        st.metric('OCR time', f"{out['ms']} ms")
        if out['codes']:
            st.dataframe(codes_table(out['codes']), hide_index=True, use_container_width=True)
        else:
            st.warning('No container code found.')
        with st.expander('All text the OCR read'):
            st.write(out['texts'])


with st.sidebar:
    st.title('🚛 Container codes')
    st.caption('RapidOCR (PP-OCRv4, ONNX, CPU) + ISO 6346 check-digit validation and correction.')
    max_side = st.select_slider('Max frame size (px)', [960, 1280, 1600, 1920, 2560], value=1920,
                                help='Larger reads smaller/farther codes but is slower.')
    zoom = st.toggle('Zoom re-read when check digit fails', value=True,
                     help='One extra OCR pass on the code area at 2x, only when needed.')
    vertical = st.toggle('Look for vertical (stacked) codes', value=True,
                         help='Side codes written top-to-bottom; one extra pass, only when needed.')
    st.markdown('**Legend**  \n🟩 check digit valid  \n🟧 unverified')

recognizer = get_recognizer(max_side)
tab_img, tab_vid, tab_cam, tab_log = st.tabs(['📷 Image', '🎞️ Video → gate log', '📡 Camera test', '📒 Gate log'])

with tab_img:
    files = st.file_uploader('Upload images', type=['jpg', 'jpeg', 'png', 'bmp', 'webp'],
                             accept_multiple_files=True)
    samples = sorted(str(p) for p in Path('images').iterdir()
                     if p.suffix.lower() in ('.png', '.jpg', '.jpeg')) + ['demo_input.jpg']
    sample = None if files else st.selectbox('…or try a sample', samples,
                                             index=samples.index('demo_input.jpg'))
    images = [(f.name, cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)) for f in files] \
        if files else [(sample, cv2.imread(sample))]
    for name, img in images:
        st.subheader(name)
        if img is None:
            st.error('Could not read this image.')
            continue
        show_result(img, recognizer(img, zoom=zoom, vertical=vertical))

with tab_vid:
    st.caption('Simulates a gate camera: votes across frames and writes one Excel row per truck, '
               'exactly like `cctv.py` does on a live feed.')
    video = st.file_uploader('Upload a video', type=['mp4', 'avi', 'mov', 'mkv'])
    c1, c2, c3, c4 = st.columns(4)
    fps = c1.slider('OCR passes / second', 0.5, 5.0, 2.0, 0.5)
    min_hits = c2.slider('Reads needed to confirm', 1, 5, 2)
    direction = c3.selectbox('Direction', ['IN', 'OUT'])
    location = c4.text_input('Location', 'Demo gate')
    if video and st.button('▶ Process video', type='primary'):
        work = Path(tempfile.mkdtemp())
        src = work / video.name
        src.write_bytes(video.read())
        cap = cv2.VideoCapture(str(src))
        vfps = cap.get(cv2.CAP_PROP_FPS) or 25
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        step = max(1, round(vfps / fps))
        tracker = GateTracker(min_hits=min_hits)
        log = ExcelLog(str(work / 'gate_log.xlsx'), work / 'snapshots')
        bar, preview, rows, n, t0 = st.progress(0.0), st.empty(), [], 0, time.time()
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            n += 1
            if n % step:
                continue
            out = recognizer(frame, zoom=zoom, vertical=vertical)
            for code, best in tracker.update(out['codes'], frame, now=n / vfps):
                row = log.log(code, best, 'Video demo', location, direction)
                row['Video time'] = f"{n / vfps:.1f} s"
                rows.append(row)
            preview.image(rgb(draw(frame, out['codes'])), caption=f"{n / vfps:.1f} s",
                          use_container_width=True)
            bar.progress(min(1.0, n / total))
        bar.progress(1.0, text=f'Done in {time.time() - t0:.0f} s, {len(rows)} truck(s) logged')
        if rows:
            st.dataframe(pd.DataFrame(rows).drop(columns=['Snapshot']), hide_index=True,
                         use_container_width=True)
            cols = st.columns(min(4, len(rows)))
            for i, row in enumerate(rows):
                cols[i % len(cols)].image(row['Snapshot'], caption=row['Container Code'])
            xlsx = next(work.glob('*.xlsx'))
            st.download_button('⬇ Download Excel log', xlsx.read_bytes(), 'gate_log.xlsx')
        else:
            st.info('No truck confirmed. Try more OCR passes per second or fewer reads needed.')

with tab_cam:
    st.caption('Check that a CCTV camera is reachable and its view is readable before running '
               '`cctv.py`. Accepts RTSP/HTTP URLs or a webcam index (0).')
    source = st.text_input('Camera source', placeholder='rtsp://user:password@192.168.1.64:554/Streaming/Channels/101')
    if source and st.button('📸 Grab a frame and read it'):
        cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
        frame = None
        for _ in range(5):  # skip stale buffered frames
            ok, f = cap.read()
            frame = f if ok else frame
        cap.release()
        if frame is None:
            st.error('Could not read from this source. Check the URL, credentials and network.')
        else:
            show_result(frame, recognizer(frame, zoom=zoom, vertical=vertical))

with tab_log:
    logs = sorted(Path('logs').glob('*.xlsx'), reverse=True)
    if not logs:
        st.info('No gate log yet. Run `python cctv.py --config cameras.json` to start logging.')
    else:
        path = st.selectbox('Workbook', logs, format_func=lambda p: p.name)
        df = pd.read_excel(path).drop(columns=['Snapshot'], errors='ignore')
        a, b, c = st.columns(3)
        a.metric('Events', len(df))
        b.metric('IN', int((df['Direction'] == 'IN').sum()))
        c.metric('OUT', int((df['Direction'] == 'OUT').sum()))
        st.dataframe(df.iloc[::-1], hide_index=True, use_container_width=True)
        snaps = sorted(Path('logs/snapshots').rglob('*.jpg'), key=lambda p: p.stat().st_mtime, reverse=True)[:8]
        if snaps:
            st.subheader('Latest snapshots')
            cols = st.columns(4)
            for i, p in enumerate(snaps):
                cols[i % 4].image(str(p), caption=p.stem.replace('_', ' '))
