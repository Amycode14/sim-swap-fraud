import os
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path.insert(0, str(root))
if not (root / '.env').exists():
    raise SystemExit('Run python scripts/init_demo.py first')
for line in (root / '.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        key, value = line.split('=', 1)
        os.environ.setdefault(key, value)
import uvicorn
from backend.app.main import create_app
uvicorn.run(create_app(), host='127.0.0.1', port=int(os.getenv('PORT', '8000')))
