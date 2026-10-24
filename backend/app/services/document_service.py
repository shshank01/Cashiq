from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.document import Document
from app.models.transaction import Transaction
from app.ml.document_parser import document_parser_instance
from app.services.transaction_service import TransactionService

class DocumentService:
    @staticmethod
    async def process_upload(db: AsyncSession, workspace_id: str, filename: str, content: bytes) -> Dict[str, Any]:
        lower_name = filename.lower()
        if lower_name.endswith(".csv"):
            file_type = "csv"
            drafts = document_parser_instance.parse_csv(content)
        elif lower_name.endswith(".pdf"):
            file_type = "pdf"
            drafts = document_parser_instance.parse_pdf(content)
        else:
            file_type = "receipt"
            drafts = await document_parser_instance.parse_receipt(content)

        doc = Document(
            workspace_id=workspace_id,
            filename=filename,
            file_type=file_type,
            status="processed",
            extracted_data=drafts
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        return {
            "document_id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "status": doc.status,
            "draft_transactions": drafts,
            "count": len(drafts)
        }

    @staticmethod
    async def confirm_drafts(db: AsyncSession, workspace_id: str, document_id: str, selected_drafts: List[Dict[str, Any]]) -> Dict[str, Any]:
        created = []
        for draft in selected_drafts:
            t = await TransactionService.create_transaction(db, workspace_id, draft)
            created.append(t)
        return {"confirmed_count": len(created), "transactions": created}
