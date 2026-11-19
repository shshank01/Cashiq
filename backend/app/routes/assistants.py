from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_workspace_user, get_db
from app.services.assistant_service import AssistantService

router = APIRouter(prefix="/assistants", tags=["assistants"])

@router.get("/")
def read_assistants(
    db: Session = Depends(get_db),
    workspace_context: dict = Depends(get_current_workspace_user)
):
    workspace_id = workspace_context["workspace_id"]
    return AssistantService.get_all(db, workspace_id)

@router.post("/")
def create_assistant(
    data: dict,
    db: Session = Depends(get_db),
    workspace_context: dict = Depends(get_current_workspace_user)
):
    workspace_id = workspace_context["workspace_id"]
    return AssistantService.create(db, workspace_id, data)
