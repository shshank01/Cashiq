import os

entities = [
    'workspace', 'category', 'account', 'dashboard', 'payable', 
    'receivable', 'recurring', 'forecast', 'insight', 'document', 
    'assistant', 'report'
]

backend_dir = r"c:\Users\LENOVO\Downloads\cashiq___\backend\app"
services_dir = os.path.join(backend_dir, "services")
routes_dir = os.path.join(backend_dir, "routes")

os.makedirs(services_dir, exist_ok=True)
os.makedirs(routes_dir, exist_ok=True)

service_template = """from sqlalchemy.orm import Session
import uuid

class {Title}Service:
    @staticmethod
    def get_all(db: Session, workspace_id: str):
        # Filtering by workspace_id enforced
        return []

    @staticmethod
    def create(db: Session, workspace_id: str, data: dict):
        # All money values in data should be amount_minor (cents/paise)
        return {{"id": str(uuid.uuid4()), "workspace_id": workspace_id, **data}}
"""

route_template = """from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_workspace_user, get_db
from app.services.{name}_service import {Title}Service

router = APIRouter(prefix="/{plural}", tags=["{plural}"])

@router.get("/")
def read_{plural}(
    db: Session = Depends(get_db),
    workspace_context: dict = Depends(get_current_workspace_user)
):
    workspace_id = workspace_context["workspace_id"]
    return {Title}Service.get_all(db, workspace_id)

@router.post("/")
def create_{name}(
    data: dict,
    db: Session = Depends(get_db),
    workspace_context: dict = Depends(get_current_workspace_user)
):
    workspace_id = workspace_context["workspace_id"]
    return {Title}Service.create(db, workspace_id, data)
"""

for e in entities:
    title = e.capitalize()
    if e == 'workspace':
        plural = 'workspaces'
    elif e == 'insight':
        plural = 'insights'
    elif e.endswith('y'):
        plural = e[:-1] + 'ies'
    else:
        plural = e + 's'

    service_path = os.path.join(services_dir, f"{e}_service.py")
    with open(service_path, "w") as f:
        f.write(service_template.format(Title=title))
        
    route_path = os.path.join(routes_dir, f"{plural}.py")
    with open(route_path, "w") as f:
        f.write(route_template.format(name=e, plural=plural, Title=title))

print("Generation complete.")
