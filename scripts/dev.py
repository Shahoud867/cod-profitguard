"""Start API and Vite without shell-specific process syntax. Ctrl-C stops both."""
import os,subprocess,sys,time,signal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
python=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
if not python.exists(): sys.exit('Run python scripts/setup.py first.')
processes=[]
try:
    processes.append(subprocess.Popen([str(python),'-m','uvicorn','app.main:app','--app-dir','services/api','--host','127.0.0.1','--port','8000'],cwd=ROOT))
    # The native dev port is 5173. A managed preview may supply PORT.
    port=os.environ.get('PORT','5173')
    npm='npm.cmd' if os.name=='nt' else 'npm'
    processes.append(subprocess.Popen([npm,'run','dev','--','--port',port],cwd=ROOT/'apps/web'))
    while all(p.poll() is None for p in processes):time.sleep(.5)
except KeyboardInterrupt:pass
finally:
    for p in processes:
        if p.poll() is None:p.terminate()
    for p in processes:
        try:p.wait(timeout=10)
        except subprocess.TimeoutExpired:p.kill()
