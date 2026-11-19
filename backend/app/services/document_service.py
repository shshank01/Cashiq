from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.ml.document_parser import document_parser_instance
from app.services.transaction_service import TransactionService


class DocumentService:
    @staticmethod
    async def process_upload(db: AsyncSession, workspace_id: str, filename: str, content: bytes) -> Dict[str, Any]:
        # Unified async format-aware pipeline (fixes missing await on parse_pdf, adds file-hash caching & provenance)
        parsed = await document_parser_instance.parse_file_with_metadata(filename=filename, content=content)
        drafts = parsed["drafts"]
        file_type = parsed["file_type"]

        doc = Document(
            workspace_id=workspace_id,
            filename=filename,
            file_type=file_type,
            file_hash=parsed["file_hash"],
            status="processed",
            extracted_data=drafts,
            raw_text=parsed.get("raw_text"),
            extraction_metadata={
                **parsed.get("metadata", {}),
                "cache_hit": parsed.get("cache_hit", False),
                "processing_ms": parsed.get("processing_ms"),
                "review_required_count": parsed.get("review_required_count", 0),
                "validation_failed_count": parsed.get("validation_failed_count", 0),
            },
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        return {
            "document_id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "file_hash": doc.file_hash,
            "status": doc.status,
            "draft_transactions": drafts,
            "count": len(drafts),
            "review_required_count": parsed.get("review_required_count", 0),
            "validation_failed_count": parsed.get("validation_failed_count", 0),
            "cache_hit": parsed.get("cache_hit", False),
            "processing_ms": parsed.get("processing_ms"),
            "extraction_metadata": doc.extraction_metadata,
        }

    @staticmethod
    async def confirm_drafts(db: AsyncSession, workspace_id: str, document_id: str, selected_drafts: List[Dict[str, Any]]) -> Dict[str, Any]:
        created = []
        for draft in selected_drafts:
            t = await TransactionService.create_transaction(db, workspace_id, draft)
            created.append(t)
        return {"confirmed_count": len(created), "transactions": created}
