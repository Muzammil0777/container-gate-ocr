"""What a site installer ships (installer/build.py): Enterprise code only in the Enterprise edition,
never tests, plans, recordings or a real cameras.json."""
import ctypes
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('build', Path(__file__).resolve().parent.parent / 'installer' / 'build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

TRACKED = ['server.py', 'cctv.py', 'VERSION', 'src/store.py', 'src/enterprise/hq.py', 'web/dist/index.html',
           'web/src/App.tsx', 'models/a.onnx', 'tests/test_store.py', 'tasks/plan.md', 'videos/readme.txt',
           'cameras.json', 'CLAUDE.md', 'bench.py', 'serverless.py', 'installer/build.py']


def test_site_installer_has_no_enterprise_code():
    files = build.app_files(TRACKED, 'site')
    assert files == ['server.py', 'cctv.py', 'VERSION', 'src/store.py', 'web/dist/index.html', 'models/a.onnx']


def test_enterprise_installer_has_it():
    assert 'src/enterprise/hq.py' in build.app_files(TRACKED, 'enterprise')


NORMAL_WINDOWS_ACCOUNT = sys.platform == 'win32' and not ctypes.windll.shell32.IsUserAnAdmin()


@pytest.mark.skipif(not NORMAL_WINDOWS_ACCOUNT, reason='Windows folder permissions, seen by a non-administrator')
def test_install_locks_the_app_folder_but_not_the_shortcut(tmp_path):
    """Other Windows accounts can't read gate.db (password hashes) or cameras.json (NVR password)."""
    app = tmp_path / 'app'
    (app / 'logs').mkdir(parents=True)
    for f in ('logs/gate.db', 'cameras.json', 'Gate app.url'):
        (app / f).write_text('x')
    script = build.HERE / 'autostart.ps1'
    try:
        subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command',
                        f". '{script}'; Lock-Folder '{app}'"], check=True, capture_output=True)
        for f in ('logs/gate.db', 'cameras.json'):
            with pytest.raises(PermissionError):
                (app / f).read_text()
        assert (app / 'Gate app.url').read_text() == 'x'
    finally:  # the owner may still change permissions: undo, so tmp_path can be removed
        subprocess.run(['icacls', str(app), '/reset', '/Q'], capture_output=True)
        subprocess.run(['icacls', str(app), '/reset', '/T', '/C', '/Q'], capture_output=True)
