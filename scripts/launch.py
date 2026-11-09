"""One-command first-run installation and local demo."""
from pathlib import Path
import subprocess,sys,os
root=Path(__file__).resolve().parents[1]
python=root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
if not python.exists() or not (root/'apps/web/node_modules').exists():subprocess.run([sys.executable,'scripts/setup.py'],cwd=root,check=True)
subprocess.run([sys.executable,'scripts/dev.py'],cwd=root,check=True)
