"""Zero-fee native bootstrap: Python 3.11+ and Node 20+ required."""
import subprocess,sys,os,venv
from pathlib import Path
root=Path(__file__).resolve().parents[1]
venv.EnvBuilder(with_pip=True).create(root/'.venv')
python=root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
subprocess.run([str(python),'-m','pip','install','-r','services/api/requirements.txt'],cwd=root,check=True)
subprocess.run(['npm.cmd' if os.name=='nt' else 'npm','ci'],cwd=root/'apps/web',check=True)
subprocess.run([str(python),'scripts/migrate.py'],cwd=root,check=True)
subprocess.run([str(python),'scripts/seed.py'],cwd=root,check=True)
print('Ready. Run python scripts/dev.py and open http://localhost:5173')
