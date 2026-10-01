import json
from pathlib import Path
from fastapi import Request
from api.main import app
from api.deps import get_database
from data.database import Database
ROOT=Path('/private/tmp/ai-trainer-daily-fix-20261001')
manifest=json.loads((ROOT/'evidence/browser-db-manifest.json').read_text())
databases={case:Database(path) for case,path in manifest.items()}
def audit_database(request:Request):
    return databases[request.query_params.get('audit_case','ordinary')]
app.dependency_overrides[get_database]=audit_database
