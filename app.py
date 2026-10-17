"""Gate OCR app:  streamlit run app.py

Live (cameras + today's trucks), Records (review, fix, download), Cameras (setup) and Test.
Detection itself runs in the gate service (cctv.py), which this app starts if needed and
configures through cameras.json; records come from the database the service writes.
"""
import tempfile
import time
from datetime import date
from pathlib import Path

# Must be imported before pandas: on Windows, pandas/pyarrow loads an older MSVC runtime DLL
# that makes onnxruntime fail with "DLL load failed while importing onnxruntime_pybind11_state".
from src.recognizer import Recognizer, draw  # noqa: I001
from src.camera import hikvision_url, port_open
from cctv import DEFAULTS, _safe
from src.config import LIVE, ROOT, grab_frame, load_config, save_config, save_fix, service_status, start_service
from src.gate import GateLog, GateTracker
from src.i18n import LANGUAGES, t
from src.iso6346 import format_code
from src.store import COLUMNS, LINKS, Store, display, needs_review, parse_fix, to_excel, to_zip

import cv2
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Container & Plate Gate OCR', page_icon='🚛', layout='wide')

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


# ---------- shared helpers ----------

@st.cache_resource(max_entries=2)  # each model copy is ~100 MB; free hosting has ~1 GB
def get_recognizer(max_side):
    return Recognizer(max_side=max_side)


@st.cache_resource
def get_store():
    return Store(str(ROOT / DEFAULTS['db']))


def rgb(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def records_table(rows, L):
    """Stored rows as a display table (newest first), with a review marker column."""
    df = pd.DataFrame([{**display(r, L), 'review': '⚠️' if needs_review(r) else ('✏️' if r.get('corrected') else '')}
                       for r in rows])
    if df.empty:
        return df
    return df[['review'] + [c for c in COLUMNS if c not in LINKS]].rename(columns=lambda c: t(c, L))


def counts(rows, L):
    a, b, c, d = st.columns(4)
    a.metric(t('events', L), len(rows))
    b.metric(t('IN', L), sum(r.get('direction') == 'IN' for r in rows))
    c.metric(t('OUT', L), sum(r.get('direction') == 'OUT' for r in rows))
    d.metric(t('needs_review', L), sum(needs_review(r) for r in rows))


def zip_button(rows, name, L, key):
    """ZIPs hold every photo, so they're built only when asked for."""
    if st.button(t('prepare_zip', L), key=f'prep_{key}', disabled=not rows):
        st.session_state[f'zip_{key}'] = to_zip(rows, L, name)
    if st.session_state.get(f'zip_{key}'):
        st.download_button(t('download_zip', L), st.session_state[f'zip_{key}'], f'{name}.zip', 'application/zip',
                           key=f'dl_{key}')


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
        else:
            st.info(t('no_plate', L))
        with st.expander(t('all_text', L)):
            st.write(out['texts'])


# ---------- layout ----------

with st.sidebar:
    L = st.radio('🌐', list(LANGUAGES), format_func=LANGUAGES.get, horizontal=True,
                 label_visibility='collapsed')
    st.title('🚛 ' + t('title', L))
    st.caption(t('subtitle', L))

if L == 'ar':  # right-to-left layout for Arabic
    st.markdown('<style>[data-testid="stAppViewContainer"], [data-testid="stSidebar"] '
                '{direction: rtl; text-align: right;}</style>', unsafe_allow_html=True)

store = get_store()
tab_live, tab_rec, tab_cams, tab_test = st.tabs([t(k, L) for k in ('tab_live', 'tab_records', 'tab_cameras', 'tab_test')])

# ---------- Live ----------
with tab_live:
    @st.fragment(run_every=2)
    def live_view():
        cams_cfg = [c for c in load_config().get('cameras', []) if c.get('enabled', True)]
        running, status = service_status()
        if not cams_cfg:
            st.info(t('no_cameras', L))
        elif not running:
            st.error(t('service_down', L))
            if time.time() - st.session_state.get('started_at', 0) < 30:
                st.success(t('service_starting', L))
            elif st.button(t('start_service', L), type='primary'):
                start_service()
                st.session_state['started_at'] = time.time()
                st.success(t('service_starting', L))
        if cams_cfg:
            cols = st.columns(min(2, len(cams_cfg)))
            for i, cam in enumerate(cams_cfg):
                with cols[i % len(cols)]:
                    name, s = cam['name'], status.get(cam['name'])
                    frame = LIVE / f"{_safe(name)}.jpg"
                    if not running:
                        st.caption(f"⚪ **{name}** · {t('stopped', L)}")
                    elif not s:
                        st.caption(f"⏳ **{name}** · {t('connecting', L, name='')}")
                    else:
                        age = int(time.time() - (s.get('last_frame_at') or 0))
                        if not s.get('last_frame_at') or age > 15:
                            st.error(f"🔴 **{name}** · {t('offline', L, s=age if s.get('last_frame_at') else '?')}")
                        else:
                            st.caption(f"🟢 **{name}** · {t(cam.get('direction', 'IN'), L)} · "
                                       f"{cam.get('location', '')} · OCR {s.get('last_ocr_ms') or '-'} {t('ms', L)}")
                    if running and frame.exists():
                        st.image(frame.read_bytes(), use_container_width=True)
        today = date.today().isoformat()
        rows = store.day(today)[::-1]
        st.subheader(t('today_trucks', L, n=len(rows)))
        counts(rows, L)
        if rows:
            st.dataframe(records_table(rows, L), hide_index=True, use_container_width=True)
            st.download_button(t('download_day', L, day=today), to_excel(rows[::-1], L), f'gate_log_{today}.xlsx',
                               XLSX, type='primary', key='dl_live_day')
            st.caption(t('review_hint', L))

    live_view()

# ---------- Records ----------
with tab_rec:
    @st.fragment(run_every=15)  # tabs are not redrawn when opened, so refresh new trucks
    def records_view():
        a, b = st.columns([1, 2])
        day = a.date_input(t('pick_day', L), value=date.today(), format='YYYY-MM-DD').isoformat()
        only_review = b.toggle(t('needs_review_only', L))
        rows = store.day(day)
        counts(rows, L)
        shown = [r for r in rows if not only_review or needs_review(r)]  # oldest first: rows keep their place
        if not shown:
            st.info(t('no_rows_day', L, day=day))
        else:
            event = st.dataframe(records_table(shown, L), hide_index=True, use_container_width=True,
                                 on_select='rerun', selection_mode='single-row', key=f'tbl_{day}_{only_review}')
            picked = event.selection.rows
            if not picked:
                st.caption(t('click_row', L))
            else:
                row = shown[picked[0]]
                st.subheader(f"{row['time']} · {display(row, L)['direction']} · {row.get('camera') or ''}")
                left, right = st.columns([3, 2])
                with left:
                    if row.get('snapshot') and Path(row['snapshot']).is_file():
                        st.image(row['snapshot'], caption=t('snapshot', L), use_container_width=True)
                    else:
                        st.warning(t('photo_missing', L))
                with right:
                    if row.get('plate_image') and Path(row['plate_image']).is_file():
                        st.image(row['plate_image'], caption=t('plate_image', L), use_container_width=True)
                    d = display(row, L)
                    st.markdown(f"**{t('plate', L)}:** {d['plate'] or '—'}  \n**{t('plate_ar', L)}:** {d['plate_ar'] or '—'}"
                                f"  \n**{t('plate_check', L)}:** {d['plate_check'] or '—'}"
                                f"  \n**{t('container', L)}:** {d['container'] or '—'}"
                                f"  \n**{t('check_digit', L)}:** {d['check_digit'] or '—'}")
                    with st.form(f"fix_{row['id']}"):
                        st.markdown(f"**{t('fix_reading', L)}**")
                        new_plate = st.text_input(t('plate', L), row.get('plate') or '', placeholder='3231 UTA')
                        new_code = st.text_input(t('container', L), row.get('container') or '', placeholder='MRSU 786939 5')
                        new_dir = st.selectbox(t('direction', L), ['IN', 'OUT'], format_func=lambda x: t(x, L),
                                               index=['IN', 'OUT'].index(row.get('direction') or 'IN'))
                        if st.form_submit_button(t('save_fix', L), type='primary'):
                            fix, errors = parse_fix(new_plate, new_code, new_dir)
                            if errors:
                                for e in errors:
                                    st.error(t(e, L))
                            else:
                                save_fix(store, row, fix)
                                if fix['check_digit_ok'] == 0:
                                    st.warning(t('check_digit_wrong', L))
                                st.success(t('fix_saved', L))
                                st.rerun()
        st.divider()
        month = day[:7]
        a, b, c = st.columns(3)
        with a:
            st.download_button(t('download_day', L, day=day), to_excel(rows, L), f'gate_log_{day}.xlsx', XLSX,
                               type='primary', disabled=not rows, key='dl_rec_day')
        with b:
            zip_button(rows, f'gate_log_{day}', L, f'zip_{day}')
        with c:
            month_rows = store.month(month)
            st.download_button(t('download_month', L, month=month), to_excel(month_rows, L), f'gate_log_{month}.xlsx',
                               XLSX, disabled=not month_rows, key='dl_rec_month')

    records_view()

# ---------- Cameras ----------
with tab_cams:
    cfg = load_config()
    nvr = cfg.get('nvr', {})
    st.subheader(t('nvr_settings', L))
    with st.form('nvr'):
        a, b, c, d = st.columns([3, 2, 2, 1.4])
        ip = a.text_input(t('nvr_ip', L), nvr.get('ip', ''), placeholder='192.168.1.64')
        user = b.text_input(t('nvr_user', L), nvr.get('user', 'admin'))
        password = c.text_input(t('nvr_password', L), nvr.get('password', ''), type='password')
        port = d.number_input(t('port', L), 1, 65535, int(nvr.get('port', 554)))
        langs = list(LANGUAGES)
        excel_lang = st.selectbox(t('excel_language', L), langs, format_func=LANGUAGES.get,
                                  index=langs.index(cfg.get('language', 'en')))
        if st.form_submit_button(t('save', L), type='primary'):
            if ip.strip() and not port_open(ip.strip(), port):
                st.error(t('unreachable', L, ip=ip))
            else:
                cfg.update(nvr={'ip': ip.strip(), 'user': user.strip(), 'password': password, 'port': int(port)},
                           language=excel_lang)
                save_config(cfg)
                st.success(t('saved', L))
    st.caption(t('password_note', L))

    st.subheader(t('cameras', L))
    cams = cfg.get('cameras', [])
    for i, cam in enumerate(cams):
        a, b, c = st.columns([5, 1.3, 1])
        area = f" · {t('roi_short', L)} {', '.join(f'{v:.0%}' for v in cam['roi'])}" if cam.get('roi') else ''
        a.markdown(f"**{cam['name']}** · {t('nvr_channel', L)} {cam.get('channel', '-')} · "
                   f"{t(cam.get('direction', 'IN'), L)} · {cam.get('location', '')}{area}")
        on = b.toggle(t('enabled', L), cam.get('enabled', True), key=f"en_{cam['name']}")
        if on != cam.get('enabled', True):
            cam['enabled'] = on
            save_config(cfg)
            st.rerun()
        if c.button('🗑', key=f"del_{cam['name']}", help=t('delete', L)):
            cfg['cameras'] = [x for x in cams if x['name'] != cam['name']]
            save_config(cfg)
            st.rerun()
    with st.expander(t('add_camera', L), expanded=not cams):
        with st.form('add_cam'):
            e, f, g, h = st.columns([2, 1, 1.4, 3])
            name = e.text_input(t('camera_name', L), 'Gate 1 Entry')
            channel = f.number_input(t('nvr_channel', L), 1, 64, 1)
            direction = g.selectbox(t('direction', L), ['IN', 'OUT'], format_func=lambda x: t(x, L))
            location = h.text_input(t('location', L), '')
            st.caption(t('roi_help', L))
            r1, r2 = st.columns(2)
            lr = r1.slider(t('roi_x', L), 0, 100, (0, 100), 5)
            tb = r2.slider(t('roi_y', L), 0, 100, (0, 100), 5)
            if st.form_submit_button(t('save_camera', L), type='primary'):
                cam = {'name': name.strip() or 'Gate 1', 'channel': int(channel), 'direction': direction,
                       'location': location.strip(), 'enabled': True}
                if (lr, tb) != ((0, 100), (0, 100)):
                    cam['roi'] = [lr[0] / 100, tb[0] / 100, lr[1] / 100, tb[1] / 100]
                cfg['cameras'] = [x for x in cams if x['name'] != cam['name']] + [cam]
                cfg.setdefault('autostart', True)
                save_config(cfg)
                st.success(t('camera_saved', L, name=cam['name']))
                st.rerun()

    if cams and nvr.get('ip'):
        st.subheader(t('test_camera', L))
        a, b = st.columns([3, 1])
        which = a.selectbox(t('camera_name', L), [c['name'] for c in cams], label_visibility='collapsed')
        if b.button(t('grab_frame', L)):
            cam = next(c for c in cams if c['name'] == which)
            if not port_open(nvr['ip'], nvr.get('port', 554)):
                st.error(t('unreachable', L, ip=nvr['ip']))
            else:
                frame = grab_frame(hikvision_url(nvr['ip'], nvr['user'], nvr['password'], cam['channel'],
                                                 port=nvr.get('port', 554)))
                if frame is None:
                    st.error(t('no_video', L))
                else:
                    st.success(t('camera_ok', L, w=frame.shape[1], h=frame.shape[0]))
                    if cam.get('roi'):  # read only the camera's reading area, like the service does
                        H, W = frame.shape[:2]
                        x0, y0, x1, y1 = cam['roi']
                        frame = frame[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
                    show_result(frame, get_recognizer(1920)(frame), L)

# ---------- Test ----------
with tab_test:
    with st.expander(t('ocr_settings', L)):
        a, b, c, d = st.columns(4)
        max_side = a.select_slider(t('max_side', L), [960, 1280, 1600, 1920, 2560], value=1920,
                                   help=t('max_side_help', L))
        zoom = b.toggle(t('zoom', L), value=True, help=t('zoom_help', L))
        vertical = c.toggle(t('vertical', L), value=True, help=t('vertical_help', L))
        read_plates = d.toggle(t('read_plates', L), value=True)
        st.markdown(t('legend', L))
    recognizer = get_recognizer(max_side)
    opts = dict(zoom=zoom, vertical=vertical, plates=read_plates)
    mode = st.radio(t('test_mode', L), ['image', 'video', 'stream'], horizontal=True,
                    format_func=lambda m: t(f'test_{m}', L))

    if mode == 'image':
        files = st.file_uploader(t('upload_images', L), type=['jpg', 'jpeg', 'png', 'bmp', 'webp'],
                                 accept_multiple_files=True)
        samples = sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'images').iterdir()
                         if p.suffix.lower() in ('.png', '.jpg', '.jpeg')) + ['demo_input.jpg']
        default = next((s for s in samples if 'ksa_' in s), 'demo_input.jpg')
        sample = None if files else st.selectbox(t('try_sample', L), samples, index=samples.index(default))
        images = [(f.name, cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)) for f in files] \
            if files else [(sample, cv2.imread(str(ROOT / sample)))]
        for name, img in images:
            st.subheader(name)
            if img is None:
                st.error(t('bad_image', L))
                continue
            show_result(img, recognizer(img, **opts), L)

    elif mode == 'video':
        st.caption(t('video_caption', L))
        video = st.file_uploader(t('upload_video', L), type=['mp4', 'avi', 'mov', 'mkv'])
        a, b, c, d = st.columns(4)
        fps = a.slider(t('fps', L), 0.5, 5.0, 2.0, 0.5)
        min_hits = b.slider(t('min_hits', L), 1, 5, 2)
        direction = c.selectbox(t('direction', L), ['IN', 'OUT'], format_func=lambda x: t(x, L))
        location = d.text_input(t('location', L), t('demo_gate', L))
        if video and st.button(t('process_video', L), type='primary'):
            work = Path(tempfile.mkdtemp())
            src = work / video.name
            src.write_bytes(video.read())
            cap = cv2.VideoCapture(str(src))
            vfps = cap.get(cv2.CAP_PROP_FPS) or 25
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
            step = max(1, round(vfps / fps))
            tracker = GateTracker(min_hits=min_hits)
            log = GateLog(Store(str(work / 'gate.db')), work / 'snapshots', work / 'excel', L)
            bar, preview, rows, n, t0 = st.progress(0.0), st.empty(), [], 0, time.time()

            def add(events):
                for e in events:
                    r = log.log(e, 'Video demo', location, direction)
                    if r['status'] == 'added':
                        rows.append(r['id'])

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
            found = [log.store.get(i) for i in rows]
            bar.progress(1.0, text=t('done', L, s=f'{time.time() - t0:.0f}', n=len(found)))
            if found:
                st.dataframe(records_table(found, L), hide_index=True, use_container_width=True)
                cols = st.columns(min(4, len(found)))
                for i, r in enumerate(found):
                    cols[i % len(cols)].image(r['snapshot'], caption=' · '.join(x for x in (r['plate'], r['container']) if x))
                st.download_button(t('download_excel', L), to_excel(found, L), 'gate_log.xlsx', XLSX)
            else:
                st.info(t('no_truck', L))

    else:
        st.caption(t('camera_caption', L))
        source = st.text_input(t('camera_source', L),
                               placeholder='rtsp://user:password@192.168.1.64:554/Streaming/Channels/101')
        if source and st.button(t('grab_frame', L)):
            frame = grab_frame(source)
            if frame is None:
                st.error(t('camera_error', L))
            else:
                st.success(t('camera_ok', L, w=frame.shape[1], h=frame.shape[0]))
                show_result(frame, recognizer(frame, **opts), L)
