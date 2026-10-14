"""English / Arabic text for the Excel log and the Streamlit app."""

LANGUAGES = {'en': 'English', 'ar': 'العربية'}

TEXT = {
    # Excel columns
    'date': ('Date', 'التاريخ'),
    'time': ('Time', 'الوقت'),
    'direction': ('Direction', 'الاتجاه'),
    'plate': ('Plate', 'رقم اللوحة'),
    'plate_ar': ('Plate (Arabic)', 'رقم اللوحة (عربي)'),
    'plate_check': ('Plate Check', 'تحقق اللوحة'),
    'container': ('Container Code', 'رقم الحاوية'),
    'check_digit': ('Check Digit OK', 'رقم التحقق صحيح'),
    'size_type': ('Size/Type', 'الحجم/النوع'),
    'camera': ('Camera', 'الكاميرا'),
    'location': ('Location', 'الموقع'),
    'confidence': ('Confidence', 'الدقة'),
    'snapshot': ('Snapshot', 'الصورة'),
    'plate_image': ('Plate Image', 'صورة اللوحة'),
    # Excel values
    'IN': ('IN', 'دخول'),
    'OUT': ('OUT', 'خروج'),
    'yes': ('YES', 'نعم'),
    'no': ('NO', 'لا'),
    'verified': ('Arabic + Latin match', 'مطابق عربي ولاتيني'),
    'latin_only': ('Latin only', 'لاتيني فقط'),
    'open_image': ('open image', 'فتح الصورة'),
    'sheet': ('Gate log', 'سجل البوابة'),
    # App
    'title': ('Container & plate gate OCR', 'قارئ الحاويات واللوحات'),
    'subtitle': ('Reads ISO 6346 container codes and Saudi number plates. Free, runs on CPU.',
                 'يقرأ أرقام الحاويات (ISO 6346) ولوحات السيارات السعودية. مجاني ويعمل على المعالج.'),
    'language': ('Language', 'اللغة'),
    'max_side': ('Max frame size (px)', 'أقصى حجم للصورة (بكسل)'),
    'max_side_help': ('Larger reads smaller/farther text but is slower.',
                      'الحجم الأكبر يقرأ النصوص الصغيرة والبعيدة لكنه أبطأ.'),
    'zoom': ('Zoom re-read when check digit fails', 'إعادة القراءة بالتكبير عند فشل رقم التحقق'),
    'zoom_help': ('One extra OCR pass on the code area at 2x, only when needed.',
                  'قراءة إضافية لمنطقة الرقم بتكبير مضاعف عند الحاجة فقط.'),
    'vertical': ('Look for vertical (stacked) codes', 'البحث عن الأرقام العمودية'),
    'vertical_help': ('Side codes written top-to-bottom; one extra pass, only when needed.',
                      'أرقام جانبية مكتوبة من الأعلى للأسفل؛ قراءة إضافية عند الحاجة فقط.'),
    'read_plates': ('Read Saudi number plates', 'قراءة اللوحات السعودية'),
    'legend': ('**Legend**  \n🟩 check digit valid  \n🟧 unverified  \n🟦 number plate',
               '**دليل الألوان**  \n🟩 رقم التحقق صحيح  \n🟧 غير مؤكد  \n🟦 لوحة السيارة'),
    'tab_image': ('📷 Image', '📷 صورة'),
    'tab_video': ('🎞️ Video → gate log', '🎞️ فيديو ← سجل البوابة'),
    'tab_camera': ('📡 Camera test', '📡 اختبار الكاميرا'),
    'tab_log': ('📒 Gate log', '📒 سجل البوابة'),
    'upload_images': ('Upload images', 'رفع الصور'),
    'try_sample': ('…or try a sample', '…أو جرّب صورة نموذجية'),
    'bad_image': ('Could not read this image.', 'تعذّرت قراءة هذه الصورة.'),
    'ocr_time': ('OCR time', 'وقت القراءة'),
    'ms': ('ms', 'مللي ثانية'),
    'no_code': ('No container code found.', 'لم يتم العثور على رقم حاوية.'),
    'no_plate': ('No number plate found.', 'لم يتم العثور على لوحة.'),
    'all_text': ('All text the OCR read', 'كل النصوص المقروءة'),
    'col_code': ('Container code', 'رقم الحاوية'),
    'col_check': ('Check digit', 'رقم التحقق'),
    'valid': ('✅ valid', '✅ صحيح'),
    'unreadable': ('❔ not readable', '❔ غير مقروء'),
    'mismatch': ('⚠️ mismatch', '⚠️ غير مطابق'),
    'col_plate_check': ('Plate check', 'تحقق اللوحة'),
    'video_caption': ('Simulates a gate camera: votes across frames and writes one Excel row per truck '
                      '(plate + container), exactly like `cctv.py` does on a live feed.',
                      'محاكاة لكاميرا البوابة: يتم التصويت عبر الإطارات وكتابة صف واحد لكل شاحنة '
                      '(اللوحة + الحاوية) في Excel، تماماً مثل `cctv.py` على البث المباشر.'),
    'upload_video': ('Upload a video', 'رفع فيديو'),
    'fps': ('OCR passes / second', 'عدد القراءات في الثانية'),
    'min_hits': ('Reads needed to confirm', 'عدد القراءات للتأكيد'),
    'demo_gate': ('Demo gate', 'بوابة تجريبية'),
    'process_video': ('▶ Process video', '▶ معالجة الفيديو'),
    'done': ('Done in {s} s, {n} truck(s) logged', 'تم في {s} ثانية، تم تسجيل {n} شاحنة'),
    'download_excel': ('⬇ Download Excel log', '⬇ تنزيل سجل Excel'),
    'no_truck': ('No truck confirmed. Try more OCR passes per second or fewer reads needed.',
                 'لم يتم تأكيد أي شاحنة. جرّب زيادة عدد القراءات في الثانية أو تقليل القراءات المطلوبة.'),
    'camera_caption': ('Check that a CCTV camera is reachable and its view is readable before running '
                       '`cctv.py`. Accepts RTSP/HTTP URLs or a webcam index (0). On the hosted demo only '
                       'cameras reachable from the internet work; for cameras on your local network, run '
                       'the app on a PC in that network.',
                       'تحقق من إمكانية الوصول إلى الكاميرا ووضوح الرؤية قبل تشغيل `cctv.py`. يقبل روابط '
                       'RTSP/HTTP أو رقم كاميرا الويب (0). في النسخة المستضافة تعمل فقط الكاميرات المتاحة '
                       'عبر الإنترنت؛ لكاميرات الشبكة المحلية شغّل التطبيق على جهاز في نفس الشبكة.'),
    'camera_source': ('Camera source', 'مصدر الكاميرا'),
    'grab_frame': ('📸 Grab a frame and read it', '📸 التقاط إطار وقراءته'),
    'camera_error': ('Could not read from this source. Check the URL, credentials and network.',
                     'تعذّرت القراءة من هذا المصدر. تحقق من الرابط وبيانات الدخول والشبكة.'),
    'no_log': ('No gate log yet. Run `python cctv.py --config cameras.json` to start logging.',
               'لا يوجد سجل بعد. شغّل `python cctv.py --config cameras.json` لبدء التسجيل.'),
    'workbook': ('Workbook', 'ملف Excel'),
    'events': ('Events', 'الأحداث'),
    'latest_snapshots': ('Latest snapshots', 'أحدث الصور'),
}


def t(key, lang='en', **fmt):
    """Text for `key` in `lang` ('en' or 'ar'); unknown keys are returned as-is."""
    pair = TEXT.get(key)
    text = key if pair is None else pair[1 if lang == 'ar' else 0]
    return text.format(**fmt) if fmt else text
