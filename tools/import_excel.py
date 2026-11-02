"""Import a customer's old gate log (Excel) into logs/gate.db, for the "Import old Excel logs"
service. Rows are marked as imported (no photos); container numbers are checked with the check
digit; the day and month Excel files are then rebuilt from the database as usual.

    py -3.12 tools/import_excel.py old_log.xlsx --map mapping.json

mapping.json (made once per customer; only "columns" is needed, and in it only "date"):
    {"sheet": "Sheet1", "header_row": 1, "date_format": "%d/%m/%Y",
     "columns": {"date": "Date", "time": "Time", "container": "Container No",
                 "plate": "Truck No", "direction": "In/Out"},
     "directions": {"IN": ["gate in"], "OUT": ["gate out"]}}

Re-running the same file adds nothing. Rows that can't be read (and rows added with a problem,
e.g. a wrong check digit) are listed in <file>_import_report.csv next to the file.
"""
import argparse
import csv
import json
import sys
from datetime import date, datetime, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import load_workbook  # noqa: E402

from src.i18n import t  # noqa: E402
from src.store import Store, parse_fix  # noqa: E402

DATE_FORMATS = ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y', '%Y/%m/%d')
TIME_FORMATS = ('%H:%M:%S', '%H:%M', '%I:%M:%S %p', '%I:%M %p')
DIRECTIONS = {'IN': ['in', 'entry', 'enter', 'دخول', 'داخل'], 'OUT': ['out', 'exit', 'خروج', 'خارج']}


def _parse(text, formats):
    for f in formats:
        try:
            return datetime.strptime(text, f)
        except ValueError:
            pass
    return None


def _when(d, tm, date_format=None):
    """Date and time cells -> ('YYYY-MM-DD', 'HH:MM:SS'), or None if either can't be read.
    A date cell may hold the time too; no time at all is stored as 00:00:00."""
    if isinstance(d, datetime):
        day, tm = d.date(), d.time() if tm in (None, '') else tm
    elif isinstance(d, date):
        day = d
    else:
        text = str(d or '').strip()
        if not tm and ' ' in text:  # '12/03/2024 14:30'
            text, tm = text.split(' ', 1)
        p = _parse(text, (date_format,) if date_format else DATE_FORMATS)
        if not p:
            return None
        day = p.date()
    if isinstance(tm, datetime):
        tm = tm.time()
    if isinstance(tm, float) and 0 <= tm < 1:  # an Excel time without a time format
        s = round(tm * 86400)
        tm = time(s // 3600 % 24, s // 60 % 60, s % 60)
    if not isinstance(tm, time):
        text = str(tm or '').strip().upper()
        p = _parse(text, TIME_FORMATS) if text else datetime.min
        if not p:
            return None
        tm = p.time()
    return day.isoformat(), tm.strftime('%H:%M:%S')


def read_rows(path, mapping):
    """The workbook's data rows as (sheet row number, {field: cell value}) for the mapped columns."""
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[mapping['sheet']] if mapping.get('sheet') else wb.active
        header_row = mapping.get('header_row', 1)
        rows = ws.iter_rows(min_row=header_row, values_only=True)
        headers = [str(h or '').strip().lower() for h in next(rows)]
        cols = {}
        for field, name in mapping['columns'].items():
            if name.strip().lower() not in headers:
                raise SystemExit(f"Column '{name}' (for {field}) not found. Columns in the sheet: {headers}")
            cols[field] = headers.index(name.strip().lower())
        for n, values in enumerate(rows, header_row + 1):
            if any(v not in (None, '') for v in values):
                yield n, {f: values[i] if i < len(values) else None for f, i in cols.items()}
    finally:
        wb.close()


def convert(cells, source, mapping, lang='en'):
    """One sheet row -> (row for Store.import_rows or None, problems). The row is None when it
    can't be read: no readable date/time, no container and no plate, or an unknown direction."""
    when = _when(cells.get('date'), cells.get('time'), mapping.get('date_format'))
    if not when:
        return None, [f"date/time not readable: {cells.get('date')!r} {cells.get('time')!r}"]
    words = {w.lower(): d for d, ws in DIRECTIONS.items() for w in [d, *ws]}
    words.update({w.strip().lower(): d for d, ws in mapping.get('directions', {}).items() for w in ws})
    raw_dir = str(cells.get('direction') or '').strip()
    direction = words.get(raw_dir.lower()) if raw_dir else None
    if raw_dir and not direction:
        return None, [f"direction not known: {raw_dir!r} (add it to \"directions\" in the mapping)"]
    plate, container = (str(cells.get(k) or '').strip() for k in ('plate', 'container'))
    if not plate and not container:
        return None, ['no container and no plate']
    fix, errors = parse_fix(plate, container, direction)
    problems = []
    if 'bad_plate' in errors:  # kept as typed (e.g. Arabic letters), not confirmed
        fix.update(plate=plate.upper(), plate_ar=None, plate_verified=0)
        problems.append(f'plate not in the usual form, kept as typed: {plate!r}')
    if 'bad_container' in errors:
        fix.update(container=container.upper(), check_digit_ok=0, size_type=None)
        problems.append(f'not a container number, kept as typed: {container!r}')
    elif fix['container'] and not fix['check_digit_ok']:
        problems.append(f"check digit wrong: {fix['container']}")
    return {**fix, 'date': when[0], 'time': when[1], 'camera': t('imported', lang), 'imported': source}, problems


def import_file(path, mapping, store, lang='en'):
    """Import one workbook. Returns (added, already there, problems as [(sheet row, text,
    row added?)], days touched)."""
    rows, problems = [], []
    for n, cells in read_rows(path, mapping):
        row, probs = convert(cells, Path(path).name, mapping, lang)
        problems += [(n, p, row is not None) for p in probs]
        if row:
            rows.append(row)
    added = store.import_rows(rows)
    return added, len(rows) - added, problems, sorted({r['date'] for r in rows})


def write_report(path, problems):
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:  # utf-8-sig: Excel shows Arabic right
        w = csv.writer(f)
        w.writerow(['sheet row', 'result', 'problem'])
        w.writerows((n, 'added' if ok else 'NOT ADDED', p) for n, p, ok in problems)


def main(argv=None):
    from src.config import DEFAULTS, ROOT, load_config  # loads the detection code: only when run
    from src.gate import GateLog
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('file')
    ap.add_argument('--map', required=True, help="the customer's column mapping (JSON)")
    ap.add_argument('--db', default=str(ROOT / DEFAULTS['db']))
    ap.add_argument('--excel-dir', default=str(ROOT / DEFAULTS['excel_dir']))
    ap.add_argument('--lang', default=load_config().get('language', 'en'), help='language of the Excel files')
    args = ap.parse_args(argv)
    mapping = json.loads(Path(args.map).read_text(encoding='utf-8'))
    store = Store(args.db)
    added, skipped, problems, days = import_file(args.file, mapping, store, args.lang)
    report = Path(args.file).with_name(Path(args.file).stem + '_import_report.csv')
    write_report(report, problems)
    # ponytail: rewrites the month file once per day in it; fine for a one-off import
    log = GateLog(store, excel_dir=args.excel_dir, language=args.lang)
    for d in days:
        log.changed(d)
    pending = log.flush()
    print(f'{added} rows added, {skipped} already there, {sum(not ok for _, _, ok in problems)} not readable '
          f'({len(problems)} problems listed in {report})')
    if pending:
        print(f'Excel files open in another program, not rewritten: {sorted(pending)}')
    return added, skipped, problems


if __name__ == '__main__':
    main()
