"""Repeatable package checks; all test records stay in a temporary directory."""
import ast
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app'
sys.path.insert(0, str(APP))
results = []
def check(name, detail):
    results.append({'check': name, 'status': 'PASS', 'detail': detail})
    print('PASS:', name, '-', detail, flush=True)

with tempfile.TemporaryDirectory(prefix='cat-monitor-audit-') as scratch:
    scratch = Path(scratch)
    os.environ['CAT_MONITOR_DATA_DIR'] = str(scratch / 'persistent data')
    os.environ.pop('CENSUS_API_KEY', None)
    files = sorted(APP.rglob('*.py')) + sorted((ROOT / 'scripts').glob('*.py'))
    for i, path in enumerate(files):
        py_compile.compile(str(path), cfile=str(scratch / f'{i}.pyc'), doraise=True)
    check('Python syntax', f'{len(files)} Python files compiled')
    imports = set()
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Import):
                imports.update(x.name for x in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.module != '__future__':
                imports.add(node.module)
    for name in sorted(imports):
        importlib.import_module(name)
    for name in ('geopandas', 'pyogrio', 'docx', 'openpyxl', 'shapely', 'pyproj', 'pandas', 'pydeck', 'streamlit'):
        importlib.import_module(name)
    for path in sorted(APP.rglob('*.py')):
        if path.name not in ('app.py', '__init__.py'):
            importlib.import_module('.'.join(path.relative_to(APP).with_suffix('').parts))
    check('Imports', f'{len(imports)} static imports and all non-entry app modules imported')
    subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True)
    pins = dict(line.split('==', 1) for line in (ROOT / 'requirements.txt').read_text().splitlines() if '==' in line)
    for name, version in pins.items():
        assert importlib.metadata.version(name) == version, name
    check('Requirements', f'{len(pins)} exact installed versions verified; pip check passed')

    from local_paths import DIRECTORIES, ensure_directories, SNAP_DIR, REVIEW_DIR, MAP_DIR
    import snapshots, reviews, baseline
    from geo import census, zipmaster, analysis, net
    ensure_directories()
    for folder in DIRECTORIES:
        assert not folder.is_relative_to(APP)
        marker = folder / 'audit-marker.txt'
        marker.write_text('persist', encoding='utf-8')
        ensure_directories()
        assert marker.read_text() == 'persist'
    assert snapshots.SNAP_DIR == analysis.SNAP_DIR == SNAP_DIR
    assert reviews.REVIEW_FILE.parent == REVIEW_DIR
    assert reviews.MAP_DIR == MAP_DIR
    check('Persistent folders', f'{len(DIRECTORIES)} external-to-code folders writable; repeated initialization preserved markers')
    assert not census.api_key()
    assert census.population_for_zctas(['00000']) == {'00000': None}
    assert census.population_for_places(['0000000']) == {'0000000': None}
    assert 'Not verified' in census.population_status()
    assert not zipmaster.available() and zipmaster.lookup('00000') is None
    assert baseline.find_workbooks() == []
    check('Missing references and key', 'Absent ZIP table, baseline and Census key return empty/Not verified, without exception')
    with patch.object(census, 'api_key', return_value='test-only-not-a-real-key'), patch.object(net, 'get_json', side_effect=net.NetError('Simulated unavailable service')):
        assert census.population_for_zctas(['00000']) == {'00000': None}
        assert census.population_for_places(['0000000']) == {'0000000': None}
    check('Census API failure', 'Simulated service failure gracefully returns unverified populations')

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP / 'app.py'), default_timeout=90).run()
    assert not at.exception, str(at.exception)
    captions = ' '.join(str(x.value) for x in at.caption)
    assert 'Optional ZIP reference missing' in captions and 'No Census API key' in captions
    check('Empty Streamlit app', 'AppTest rendered with zero exceptions and both clear missing-reference messages')

    # Optional real source fixture is supplied only by the builder, never shipped.
    fixture = os.environ.get('CAT_MONITOR_AUDIT_CSV')
    if fixture:
        raw = Path(fixture).read_bytes()
        geo = os.environ.get('CAT_MONITOR_AUDIT_GEOJSON')
        sid = snapshots.save_snapshot(raw, Path(fixture).name, geojson_bytes=Path(geo).read_bytes() if geo else None)
        assert len(snapshots.list_snapshots()) == 1
        at = AppTest.from_file(str(APP / 'app.py'), default_timeout=90).run()
        assert not at.exception, str(at.exception)
        mark = next(x for x in at.button if x.label == 'Mark Reviewed')
        mark.click().run()
        assert not at.exception, str(at.exception)
        assert reviews.load()
        before = hashlib.sha256(reviews.REVIEW_FILE.read_bytes()).hexdigest()
        at2 = AppTest.from_file(str(APP / 'app.py'), default_timeout=90).run()
        assert not at2.exception
        assert hashlib.sha256(reviews.REVIEW_FILE.read_bytes()).hexdigest() == before
        try:
            snapshots.save_snapshot(raw, Path(fixture).name)
            raise AssertionError('Duplicate was accepted')
        except ValueError as exc:
            assert 'identical' in str(exc)
        check('Populated workflow', 'Real WFIGS import, dashboard, Mark Reviewed, new session reload, and duplicate rejection passed; fixture SHA256=' + hashlib.sha256(raw).hexdigest())
        if geo:
            import dashboard_map
            from geo import spatial
            feature = next(f for f in json.loads(Path(geo).read_text(encoding='utf-8'))['features'] if f.get('geometry') and f['geometry']['type'] in ('Polygon', 'MultiPolygon'))
            geometry = feature['geometry']
            with patch.object(analysis.perimeters, 'get_perimeter', return_value={'geometry': geometry}), patch.object(census, 'fetch_zctas', side_effect=net.NetError('Simulated blocked TIGERweb')):
                unavailable = analysis.run(sid, 'AUDIT-TIGERWEB-FAILURE', force=True)
                assert unavailable['status'] == 'not_calculated'
                assert 'Census TIGERweb unavailable' in unavailable['reason']
                assert analysis.load(sid, 'AUDIT-TIGERWEB-FAILURE')['reason'] == unavailable['reason']
            check('TIGERweb failure', 'Blocked geography service produces a saved explicit unavailable result, without crashing')
            # Real perimeter only; explicitly no Census reference features.
            inputs = {'perimeter': {'geometry': geometry}, 'zctas': {'features': []}, 'places': {'features': []}}
            result = {'status': 'calculated', 'spatial': spatial.analyze(geometry, [], [], 10.0)}
            prepared = dashboard_map.prepare(result, inputs)
            assert prepared['ok']
            path = MAP_DIR / 'audit-perimeter-only.html'
            dashboard_map.deck(prepared, 'Build test: real perimeter only').to_html(str(path), open_browser=False, notebook_display=False)
            assert path.stat().st_size > 500 and '<html' in path.read_text(encoding='utf-8').lower()
            ensure_directories()
            assert path.exists()
            check('Review map storage', 'Real perimeter serialized by existing map builder into persistent HTML; no Census features or populations synthesized')
    (ROOT / 'provenance/automated-checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
