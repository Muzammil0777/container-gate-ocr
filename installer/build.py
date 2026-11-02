"""Build the site installer (one setup.exe): the app, Python 3.12, its packages, the models and the
built web app. On the vendor's PC, in the project folder:

    py -3.12 installer/build.py                      Site edition (no src/enterprise/)
    py -3.12 installer/build.py --edition enterprise Enterprise edition
    py -3.12 installer/build.py --control-center https://cc.example.com/v1/checkin

Needs Inno Setup 6 (ISCC.exe on PATH, in its usual folder, or set ISCC) and internet (Python and
the packages are downloaded into installer/build/). The result is in installer/dist/.

Signing: set GATE_SIGN_THUMBPRINT to the code-signing certificate's thumbprint (the certificate
sits in the Windows certificate store or on its USB token, never in this repo) and have
signtool.exe from the Windows SDK (on PATH, in Windows Kits, or set GATE_SIGNTOOL). Without
GATE_SIGN_THUMBPRINT the installer is unsigned: fine for tests, Windows then says "unknown publisher".
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / 'installer'
BUILD = HERE / 'build'
PYTHON_VERSION = '3.12.10'  # the last 3.12 release with Windows binaries
PYTHON_ZIP = f'https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip'
SHIP = ('server.py', 'cctv.py', 'requirements.txt', 'VERSION', 'cameras.example.json',
        'demo_input.jpg', 'src/', 'models/', 'web/dist/', 'images/')
NOT_ON_SITES = ('pytest',)  # requirements only the developer needs


def app_files(tracked, edition):
    """The repo files a site gets: tracked files under SHIP; a Site installer leaves out src/enterprise/."""
    folders = tuple(s for s in SHIP if s.endswith('/'))
    keep = [f for f in tracked if f in SHIP or f.startswith(folders)]
    if edition == 'site':
        keep = [f for f in keep if not f.startswith('src/enterprise/')]
    return keep


def find_tool(env, name, patterns):
    if os.environ.get(env):
        return os.environ[env]
    found = shutil.which(name) or next((p for pat in patterns for p in sorted(glob.glob(pat), reverse=True)), None)
    if not found:
        sys.exit(f'{name} not found: install it or set {env} to its full path.')
    return found


def stage(edition):
    app = BUILD / edition / 'app'
    shutil.rmtree(app, ignore_errors=True)
    tracked = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    for f in app_files(tracked, edition):
        (app / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, app / f)
    for f in ('gate_service.bat', 'autostart.ps1'):
        shutil.copy2(HERE / f, app / f)

    # Python: the embeddable zip, plus the packages as Windows wheels for 3.12.
    zip_path = BUILD / Path(PYTHON_ZIP).name
    if not zip_path.exists():
        print('Downloading', PYTHON_ZIP)
        urllib.request.urlretrieve(PYTHON_ZIP, zip_path)
    py = app / 'python'
    zipfile.ZipFile(zip_path).extractall(py)
    # The embedded Python ignores the script's folder: list the app folder (..) and site-packages here.
    # No 'import site': the build PC's own user packages must not leak in (none of ours need .pth files).
    (py / 'python312._pth').write_text('python312.zip\n.\nLib\\site-packages\n..\n', encoding='utf-8')
    reqs = [r for r in (ROOT / 'requirements.txt').read_text(encoding='utf-8').split()
            if not r.startswith(NOT_ON_SITES)]
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--target', str(py / 'Lib' / 'site-packages'),
                    '--platform', 'win_amd64', '--python-version', '3.12', '--only-binary=:all:',
                    '--no-compile', *reqs], check=True)
    return app


def main():
    ap = argparse.ArgumentParser(description='Build setup.exe for a site.')
    ap.add_argument('--edition', choices=('site', 'enterprise'), default='site')
    ap.add_argument('--control-center', default='', help='check-in address set on the site PC (GATE_CONTROL_CENTER)')
    ap.add_argument('--skip-stage', action='store_true', help='reuse installer/build/<edition>/app')
    ap.add_argument('--stage-only', action='store_true', help='stop before Inno Setup (try the app in installer/build)')
    args = ap.parse_args()
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    app = BUILD / args.edition / 'app' if args.skip_stage else stage(args.edition)
    url_file = app / 'control_center.txt'  # gate_service.bat sets GATE_CONTROL_CENTER from it
    if args.control_center:
        url_file.write_text(args.control_center, encoding='utf-8')
    else:
        url_file.unlink(missing_ok=True)
    if args.stage_only:
        return print('Staged:', app)

    iscc = find_tool('ISCC', 'ISCC', [r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
                                      os.path.expandvars(r'%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe')])
    cmd = [iscc, f'/DAppSource={app}', f'/DAppVersion={version}', f'/DEdition={args.edition}', f'/O{HERE / "dist"}']
    thumb = os.environ.get('GATE_SIGN_THUMBPRINT', '').replace(' ', '')
    if thumb:
        signtool = find_tool('GATE_SIGNTOOL', 'signtool',
                             [r'C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe'])
        cmd += ['/DSign', f'/Sgate=$q{signtool}$q sign /sha1 {thumb} /fd sha256 '
                          '/tr http://timestamp.digicert.com /td sha256 $f']
    else:
        print('GATE_SIGN_THUMBPRINT is not set: the installer will be UNSIGNED (tests only).')
    subprocess.run([*cmd, str(HERE / 'setup.iss')], check=True)


if __name__ == '__main__':
    main()
