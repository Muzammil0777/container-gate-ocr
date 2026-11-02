"""What a site installer ships (installer/build.py): Enterprise code only in the Enterprise edition,
never tests, plans, recordings or a real cameras.json."""
import importlib.util
from pathlib import Path

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
