"""Create a clean, shareable Windows source package using an explicit allowlist."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib,json,re

root=Path(__file__).resolve().parent
out=root/'dist'/'RiverGuard-Windows.zip'
files=[root/name for name in ['api.py','ui_api.py','security.py','serve.py','data_service.py','chat_service.py','core.py','dashboard.py','charting.py','companion.py','evaluate.py','rill_ai.py','rill_jobs.py','rill_store.py','river_status.py','benchmark_rill_quality.py','package_app.py','install.ps1','launch.ps1','Start RiverGuard.cmd','Setup RiverGuard.cmd','START HERE.txt','README.md','requirements.txt','requirements-lock.txt']]
files += [root/'.streamlit'/'config.toml',root/'reading_visuals.py',root/'sensor_support.py',root/'rill_verification.py',root/'rill_models.py',root/'stop.ps1',root/'Stop RiverGuard.cmd']
files += [root/'station_setup.py',root/'setup_ui.py']
files += list((root/'output'/'pdf').glob('RiverGuard-Friend-Setup.pdf'))
for directory in ['assets','hardware','evaluation','tests']:
    files += [p for p in (root/directory).rglob('*') if p.is_file() and not any(part in {'__pycache__','.pio'} for part in p.parts) and p.name!='station_config.h' and p.suffix not in ('.pyc','.pyo')]
files += [p for p in (root/'frontend').rglob('*') if p.is_file() and not any(part in {'node_modules','.vite','coverage'} for part in p.relative_to(root/'frontend').parts) and not p.name.startswith('.env') and not p.name.endswith('.tsbuildinfo')]
assert (root/'frontend/dist/index.html').is_file(),'Build the frontend before packaging.'
for p in files:
    assert p.is_file(),p
    if p.suffix.lower() in {'.py','.ps1','.cmd','.md','.txt','.toml','.css','.ino','.cpp','.h','.ini'}:
        text=p.read_text(encoding='utf-8-sig')
        assert not re.search(r'AIza[0-9A-Za-z_-]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{30,}',text),f'Possible secret in {p.name}'
out.parent.mkdir(exist_ok=True)
with ZipFile(out,'w',ZIP_DEFLATED,compresslevel=9) as z:
    for p in sorted(set(files)):
        z.write(p,Path('RiverGuard')/p.relative_to(root))
with ZipFile(out) as z:
    assert z.testzip() is None
    names=z.namelist()
    assert not any(part in {'data','.venv','ui-review','__pycache__'} for n in names for part in Path(n).parts)
    assert not any(Path(n).suffix in {'.db','.log'} or Path(n).name in {'.env','secrets.toml'} for n in names)
    assert any(n=='RiverGuard/frontend/dist/index.html' for n in names)
    assert not any('node_modules' in Path(n).parts or Path(n).name in {'station_config.h','owner-link.html'} for n in names)
print(json.dumps({'zip':str(out),'files':len(names),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest()},indent=2))
