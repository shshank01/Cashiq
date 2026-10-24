from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_workspace_user, get_db
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])

@router.get("/")
def read_documents(
    db: Session = Depends(get_db),
    workspace_context: dict = Depends(get_current_workspace_user)
):
    workspace_id = workspace_context["workspace_id"]
    return DocumentService.get_all(db, workspace_id)

@router.post("/")
def create_document(
    data: dict,
    db: Session = Depends(get_db),
    workspace_context: dict = Depends(get_current_workspace_user)
):
    workspace_id = workspace_context["workspace_id"]
    return DocumentService.create(db, workspace_id, data)
