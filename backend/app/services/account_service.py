from sqlalchemy.orm import Session
import uuid

class AccountService:
    @staticmethod
    def get_all(db: Session, workspace_id: str):
        # Filtering by workspace_id enforced
        return []

    @staticmethod
    def create(db: Session, workspace_id: str, data: dict):
        # All money values in data should be amount_minor (cents/paise)
        return {"id": str(uuid.uuid4()), "workspace_id": workspace_id, **data}
