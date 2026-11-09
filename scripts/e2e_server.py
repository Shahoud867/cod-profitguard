"""Browser harness: isolate mutations from the working merchant demo."""
import os,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='profitguard-e2e-') as tmp:
    env=dict(os.environ);env.setdefault('PROFITGUARD_DB',str(Path(tmp)/'e2e.db'))
    try:subprocess.run([sys.executable,str(root/'scripts/dev.py')],cwd=root,env=env,check=True)
    except KeyboardInterrupt:pass
