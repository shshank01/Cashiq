import os
import re
import joblib
import numpy as np
from typing import Dict, Any, Optional

from app.ml.business_taxonomy import infer_semantic_domain
from app.ml.merchant_normalizer import normalize_merchant_name

MODEL_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'ml_models', 'categorizer.joblib')


def clean_transaction_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r'ref:[a-f0-9]+', 'ref_id', text)
    text = re.sub(r'inr\s*[\d\.,]+', 'inr_amount', text)
    text = re.sub(r'usd\s*[\d\.,]+', 'usd_amount', text)
    text = re.sub(r'[\d]{4,}', 'num_token', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class TransactionCategorizer:
    def __init__(self):
        self.model = None
        self.vectorizer = None
        self.model_version = "v1.3.0-context-tfidf-logreg"
        self.classes = []
        self.confidence_threshold = 0.70
        # Workspace-scoped learned merchant -> category overrides from user feedback
        self._workspace_merchant_overrides: Dict[str, Dict[str, str]] = {}
        self.load_model()

    def load_model(self):
        if os.path.exists(MODEL_PATH):
            try:
                data = joblib.load(MODEL_PATH)
                self.model = data.get('model')
                self.vectorizer = data.get('vectorizer')
                self.model_version = data.get('model_version', self.model_version)
                self.classes = data.get('classes', [])
            except Exception as e:
                print(f"[TransactionCategorizer] Error loading model: {e}")

    def register_merchant_override(self, workspace_id: str, merchant: Optional[str], category: str) -> None:
        """Records a user-verified merchant -> category mapping for a specific workspace."""
        if not workspace_id or not merchant or not category:
            return
        canonical = normalize_merchant_name(merchant)["canonical"]
        if canonical:
            self._workspace_merchant_overrides.setdefault(workspace_id, {})[canonical] = category

    def rule_based_fallback(self, text: str) -> Dict[str, Any]:
        low = text.lower()
        if re.search(r'\b(aws|amazon web services|azure|google cloud|gcp|slack|github|zoom|figma|notion|jira|atlassian|datadog|mongodb|openai|anthropic|stripe billing|vercel)\b', low):
            return {
                "category": "Software & Cloud Services",
                "confidence": 0.95,
                "model_version": "v1.3.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(payroll|salary|gusto|rippling|adp|wages|bonus|contractor payout|deel)\b', low):
            return {
                "category": "Payroll & Wages",
                "confidence": 0.96,
                "model_version": "v1.3.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(wework|rent|lease|facilities|coned|comcast business|electricity|janitorial)\b', low):
            return {
                "category": "Rent & Facilities",
                "confidence": 0.92,
                "model_version": "v1.3.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(google ads|facebook ads|meta ads|linkedin ads|mailchimp|canva|advertising|marketing)\b', low):
            return {
                "category": "Marketing & Advertising",
                "confidence": 0.91,
                "model_version": "v1.3.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(uber|lyft|airline|flight|hotel|airbnb|rail|train|cab|taxi|makemytrip|indigo|vistara|air india)\b', low):
            return {
                "category": "Travel & Transportation",
                "confidence": 0.88,
                "model_version": "v1.3.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(starbucks|cafe|restaurant|doordash|swiggy|zomato|coffee|lunch|dinner|meals|dominos)\b', low):
            return {
                "category": "Meals & Entertainment",
                "confidence": 0.86,
                "model_version": "v1.3.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(client payment|wire transfer received|stripe payout|customer invoice|revenue|ach credit|subscription receipt|inward)\b', low):
            return {
                "category": "Client Revenue",
                "confidence": 0.93,
                "model_version": "v1.3.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(legal|attorney|cpa|accounting|audit|deloitte|retainer|tax compliance|advocate|chartered accountant)\b', low):
            return {
                "category": "Professional & Legal",
                "confidence": 0.89,
                "model_version": "v1.3.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(emi|loan|interest|mortgage|hdfc loan)\b', low):
            return {
                "category": "Loans & Financing",
                "confidence": 0.87,
                "model_version": "v1.3.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(office depot|staples|ikea|hardware|monitor|desk|electronics|supplies|stationery|printer paper|keyboard|usb)\b', low):
            return {
                "category": "Office Supplies & Equipment",
                "confidence": 0.84,
                "model_version": "v1.3.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(broadband|internet bill|telecom|airtel|jio|vodafone|mobile bill|water bill|gas bill|utility)\b', low):
            return {
                "category": "Utilities & Telecom",
                "confidence": 0.85,
                "model_version": "v1.3.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(gst payment|tds|advance tax|income tax|challan|statutory)\b', low):
            return {
                "category": "Taxes & Compliance",
                "confidence": 0.88,
                "model_version": "v1.3.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(insurance|policy premium|health cover|liability cover)\b', low):
            return {
                "category": "Insurance",
                "confidence": 0.86,
                "model_version": "v1.3.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(bank charges|service charge|forex markup|wire fee|atm fee|annual fee|sms alert charge)\b', low):
            return {
                "category": "Banking & Fees",
                "confidence": 0.86,
                "model_version": "v1.3.0-rules-fallback",
                "review_required": False
            }

        # Check general operational semantic domains (groceries/ingredients, medical, construction, shipping, etc.)
        semantic_cat = infer_semantic_domain(text)
        if semantic_cat:
            return {
                "category": semantic_cat,
                "confidence": 0.86,
                "model_version": "v1.3.0-domain-taxonomy",
                "review_required": False
            }

        return {
            "category": "Miscellaneous",
            "confidence": 0.40,
            "model_version": "v1.3.0-rules-fallback",
            "review_required": True
        }

    def categorize(
        self,
        text: str,
        workspace_id: Optional[str] = None,
        merchant: Optional[str] = None,
        workspace_merchant_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Categorizes raw transaction text using workspace feedback memory, domain rules, or supervised ML model."""
        if not text or not str(text).strip():
            return {
                "category": "Miscellaneous",
                "confidence": 0.0,
                "model_version": self.model_version,
                "review_required": True,
                "needs_review": True,
            }

        # 1. Check workspace-specific user-verified merchant overrides first
        if merchant or text:
            canonical_m = normalize_merchant_name(merchant or text)["canonical"]
            if canonical_m:
                override_cat = None
                if workspace_merchant_map and canonical_m in workspace_merchant_map:
                    override_cat = workspace_merchant_map[canonical_m]
                elif workspace_id and canonical_m in self._workspace_merchant_overrides.get(workspace_id, {}):
                    override_cat = self._workspace_merchant_overrides[workspace_id][canonical_m]
                if override_cat:
                    return {
                        "category": override_cat,
                        "confidence": 0.96,
                        "model_version": "v1.3.0-workspace-feedback",
                        "review_required": False,
                        "needs_review": False,
                    }

        cleaned = clean_transaction_text(text)

        # 2. Check rule-based / domain-taxonomy patterns
        rule_res = self.rule_based_fallback(text)
        if rule_res["confidence"] >= 0.80:
            rule_res["needs_review"] = rule_res["review_required"]
            return rule_res

        # 3. Trained ML model
        if self.model and self.vectorizer:
            try:
                vec = self.vectorizer.transform([cleaned])
                probas = self.model.predict_proba(vec)[0]
                best_idx = int(np.argmax(probas))
                confidence = float(probas[best_idx])
                predicted_category = self.model.classes_[best_idx]

                review_required = confidence < self.confidence_threshold
                return {
                    "category": predicted_category,
                    "confidence": round(confidence, 4),
                    "model_version": self.model_version,
                    "review_required": review_required,
                    "needs_review": review_required,
                }
            except Exception as e:
                print(f"[TransactionCategorizer] Prediction exception: {e}")

        rule_res["needs_review"] = rule_res["review_required"]
        return rule_res


categorizer_instance = TransactionCategorizer()
