import os
import re
import joblib
import numpy as np
from typing import Dict, Any, Optional

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
        self.model_version = "v1.2.0-kaggle-tfidf-logreg"
        self.classes = []
        self.confidence_threshold = 0.70
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
                
    def rule_based_fallback(self, text: str) -> Dict[str, Any]:
        low = text.lower()
        if re.search(r'\b(aws|amazon web services|azure|google cloud|gcp|slack|github|zoom|figma|notion|jira|atlassian|datadog|mongodb|openai|anthropic|stripe billing|vercel)\b', low):
            return {
                "category": "Software & Cloud Services",
                "confidence": 0.95,
                "model_version": "v1.2.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(payroll|salary|gusto|rippling|adp|wages|bonus|contractor payout|deel)\b', low):
            return {
                "category": "Payroll & Wages",
                "confidence": 0.96,
                "model_version": "v1.2.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(wework|rent|lease|facilities|coned|comcast business|electricity|janitorial)\b', low):
            return {
                "category": "Rent & Facilities",
                "confidence": 0.92,
                "model_version": "v1.2.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(google ads|facebook ads|meta ads|linkedin ads|mailchimp|canva|advertising|marketing)\b', low):
            return {
                "category": "Marketing & Advertising",
                "confidence": 0.91,
                "model_version": "v1.2.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(uber|lyft|airline|flight|hotel|airbnb|rail|train|cab|taxi|makemytrip)\b', low):
            return {
                "category": "Travel & Transportation",
                "confidence": 0.88,
                "model_version": "v1.2.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(starbucks|cafe|restaurant|doordash|swiggy|zomato|coffee|lunch|dinner|meals|dominos)\b', low):
            return {
                "category": "Meals & Entertainment",
                "confidence": 0.86,
                "model_version": "v1.2.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(client payment|wire transfer received|stripe payout|customer invoice|revenue|ach credit|subscription receipt)\b', low):
            return {
                "category": "Client Revenue",
                "confidence": 0.93,
                "model_version": "v1.2.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(legal|attorney|cpa|accounting|audit|deloitte|retainer|tax compliance)\b', low):
            return {
                "category": "Professional & Legal",
                "confidence": 0.89,
                "model_version": "v1.2.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(emi|loan|interest|mortgage|hdfc loan)\b', low):
            return {
                "category": "Loans & Financing",
                "confidence": 0.87,
                "model_version": "v1.2.0-rules-fallback",
                "review_required": False
            }
        elif re.search(r'\b(office depot|staples|ikea|hardware|monitor|desk|electronics|supplies)\b', low):
            return {
                "category": "Office Supplies & Equipment",
                "confidence": 0.82,
                "model_version": "v1.2.0-rules-fallback",
                "review_required": False
            }
            
        return {
            "category": "Miscellaneous",
            "confidence": 0.40,
            "model_version": "v1.2.0-rules-fallback",
            "review_required": True
        }

    def categorize(self, text: str) -> Dict[str, Any]:
        """Categorizes raw transaction text using supervised model or high-precision rule fallback."""
        if not text or not str(text).strip():
            return {
                "category": "Miscellaneous",
                "confidence": 0.0,
                "model_version": self.model_version,
                "review_required": True
            }
            
        cleaned = clean_transaction_text(text)
        
        # Check rule-based override for domain-specific exact patterns first
        rule_res = self.rule_based_fallback(text)
        if rule_res["confidence"] >= 0.80:
            return rule_res

        # If trained ML model is available
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
                    "review_required": review_required
                }
            except Exception as e:
                print(f"[TransactionCategorizer] Prediction exception: {e}")
                
        return rule_res

categorizer_instance = TransactionCategorizer()
