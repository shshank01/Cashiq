import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.transaction import Transaction
from app.models.account import Account
from app.models.payable import Payable
from app.models.receivable import Receivable
from app.models.recurring import RecurringRule
from app.models.business_profile import BusinessProfile
from app.services.insight_service import InsightService
from app.ml.forecaster import forecaster_instance
from app.config import settings

class FinancialAssistantService:
    """
    Controlled tool-based financial intelligence assistant.
    Strictly isolated to authenticated workspace data. Never invents numbers.
    """

    @staticmethod
    async def execute_tools(db: AsyncSession, workspace_id: str, query: str) -> Dict[str, Any]:
        """Runs controlled data retrieval tools based on query intent."""
        now = datetime.now(timezone.utc)
        q = query.lower()
        tools_executed = []
        data_context = {}

        # 1. getDashboardSummary
        if any(w in q for w in ["summary", "overview", "dashboard", "health", "how is my business", "status"]):
            tools_executed.append("getDashboardSummary()")
            accts = (await db.execute(select(Account).where(Account.workspace_id == workspace_id))).scalars().all()
            cash = sum(a.balance_minor for a in accts)
            
            txs = (await db.execute(select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.date >= now - timedelta(days=30)
            ))).scalars().all()
            inc = sum(abs(t.amount_minor) for t in txs if t.type == "income")
            exp = sum(abs(t.amount_minor) for t in txs if t.type == "expense")
            
            data_context["dashboard_summary"] = {
                "current_cash": f"${cash/100:,.2f}",
                "last_30d_income": f"${inc/100:,.2f}",
                "last_30d_expenses": f"${exp/100:,.2f}",
                "net_cash_flow": f"${(inc - exp)/100:,.2f}",
                "accounts_count": len(accts)
            }

        # 2. getCategorySpend / comparePeriods (e.g., "why did expenses increase", "biggest expense")
        if any(w in q for w in ["expense", "spend", "category", "increase", "biggest", "cost", "more"]):
            tools_executed.append("getCategorySpend()")
            tools_executed.append("comparePeriods()")
            
            txs_60 = (await db.execute(select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.type == "expense",
                Transaction.date >= now - timedelta(days=60)
            ))).scalars().all()
            
            curr_cats = {}
            prev_cats = {}
            thirty_d = now - timedelta(days=30)
            
            for t in txs_60:
                cat = t.category_name or "Miscellaneous"
                amt = abs(t.amount_minor)
                t_date = t.date if t.date.tzinfo else t.date.replace(tzinfo=timezone.utc)
                if t_date >= thirty_d:
                    curr_cats[cat] = curr_cats.get(cat, 0) + amt
                else:
                    prev_cats[cat] = prev_cats.get(cat, 0) + amt
                    
            cat_comparison = []
            for cat in set(list(curr_cats.keys()) + list(prev_cats.keys())):
                c_val = curr_cats.get(cat, 0)
                p_val = prev_cats.get(cat, 0)
                diff = c_val - p_val
                pct = ((diff / p_val) * 100.0) if p_val > 0 else (100.0 if c_val > 0 else 0.0)
                cat_comparison.append({
                    "category": cat,
                    "current_30d": f"${c_val/100:,.2f}",
                    "previous_30d": f"${p_val/100:,.2f}",
                    "change": f"{'+' if diff > 0 else ''}${diff/100:,.2f} ({pct:+.1f}%)",
                    "raw_diff": diff
                })
            cat_comparison.sort(key=lambda x: x["raw_diff"], reverse=True)
            data_context["category_spend_comparison"] = cat_comparison[:5]

        # 3. getPayables / getReceivables (e.g., "what payments are due", "receivables", "invoices")
        if any(w in q for w in ["payable", "due", "owe", "bill", "vendor", "pay"]):
            tools_executed.append("getPayables()")
            pays = (await db.execute(select(Payable).where(
                Payable.workspace_id == workspace_id,
                Payable.status != "paid"
            ).order_by(Payable.due_date.asc()))).scalars().all()
            data_context["upcoming_payables"] = [
                {
                    "vendor": p.vendor,
                    "amount": f"${p.amount_minor/100:,.2f}",
                    "due_date": p.due_date.strftime("%Y-%m-%d"),
                    "status": p.status
                }
                for p in pays[:5]
            ]

        if any(w in q for w in ["receivable", "client", "incoming", "collect", "invoice", "expect"]):
            tools_executed.append("getReceivables()")
            recs = (await db.execute(select(Receivable).where(
                Receivable.workspace_id == workspace_id,
                Receivable.status != "received"
            ).order_by(Receivable.due_date.asc()))).scalars().all()
            data_context["upcoming_receivables"] = [
                {
                    "client": r.client,
                    "amount": f"${r.amount_minor/100:,.2f}",
                    "due_date": r.due_date.strftime("%Y-%m-%d"),
                    "status": r.status
                }
                for r in recs[:5]
            ]

        # 4. getForecast (e.g., "expected cash position", "runway", "forecast", "future")
        if any(w in q for w in ["forecast", "future", "runway", "cash position", "projection", "next month", "burn"]):
            tools_executed.append("getForecast()")
            accts = (await db.execute(select(Account).where(Account.workspace_id == workspace_id))).scalars().all()
            cash = sum(a.balance_minor for a in accts)
            txs = (await db.execute(select(Transaction).where(Transaction.workspace_id == workspace_id))).scalars().all()
            pays = (await db.execute(select(Payable).where(Payable.workspace_id == workspace_id))).scalars().all()
            recs = (await db.execute(select(Receivable).where(Receivable.workspace_id == workspace_id))).scalars().all()
            prof = (await db.execute(select(BusinessProfile).where(BusinessProfile.workspace_id == workspace_id))).scalar_one_or_none()
            
            fc = forecaster_instance.forecast_cash_flow(
                current_cash_minor=cash,
                transactions=txs,
                business_profile=prof,
                known_payables=pays,
                known_receivables=recs,
                forecast_days=30
            )
            data_context["cash_flow_forecast"] = {
                "classification": fc["forecast_type"],
                "current_balance": f"${cash/100:,.2f}",
                "projected_end_30d_balance": f"${fc['summary']['end_cash_position_minor']/100:,.2f}",
                "lowest_projected_balance": f"${fc['summary']['lowest_cash_position_minor']/100:,.2f}",
                "method": fc["model_info"]["method"]
            }

        # 5. getInsights
        if any(w in q for w in ["insight", "unusual", "alert", "anomaly", "recommendation"]):
            tools_executed.append("getInsights()")
            insights = await InsightService.get_all(db, workspace_id)
            data_context["active_insights"] = [
                {"title": i["title"], "description": i["description"], "severity": i["severity"]}
                for i in insights[:4]
            ]

        # Default fallback to dashboard summary if nothing matched
        if not tools_executed:
            tools_executed.append("getDashboardSummary()")
            tools_executed.append("getInsights()")
            accts = (await db.execute(select(Account).where(Account.workspace_id == workspace_id))).scalars().all()
            cash = sum(a.balance_minor for a in accts)
            data_context["dashboard_summary"] = {"current_cash": f"${cash/100:,.2f}"}

        return {"tools_executed": tools_executed, "data_context": data_context}

    @staticmethod
    def clean_api_key(api_key: Optional[str]) -> str:
        """Sanitizes API keys by trimming whitespace, quotes, Bearer prefix, and accidental prepends."""
        k = (api_key or "").strip().strip('"\'`')
        if k.lower().startswith("bearer "):
            k = k[7:].strip()
        # If user accidentally prepended AIzaSy to an AQ. Auth Key
        if "AQ." in k and not k.startswith("AQ."):
            aq_idx = k.find("AQ.")
            k = k[aq_idx:].strip()
        return k

    @staticmethod
    def is_text_generation_model(name: str) -> bool:
        """Ensures the model supports text generation and excludes audio/TTS/image/video models."""
        n = name.lower()
        for excluded in ["-tts", "tts", "audio", "image", "imagen", "video", "veo", "embed", "realtime", "live"]:
            if excluded in n:
                return False
        return True

    @staticmethod
    def extract_gemini_text(data: Dict[str, Any]) -> str:
        """Safely extracts generated text from Gemini API response without KeyError."""
        if not isinstance(data, dict):
            return ""
        candidates = data.get("candidates", [])
        if not candidates or not isinstance(candidates, list):
            return ""
        candidate = candidates[0]
        if not isinstance(candidate, dict):
            return ""
        content = candidate.get("content", {})
        if isinstance(content, str):
            return content.strip()
        parts = content.get("parts", []) if isinstance(content, dict) else []
        text_pieces = []
        for p in parts:
            if isinstance(p, dict) and "text" in p:
                text_pieces.append(str(p["text"]))
            elif isinstance(p, str):
                text_pieces.append(p)
        return "".join(text_pieces).strip()

    @staticmethod
    async def call_gemini(model: str, key: str, system_prompt: str, user_prompt: str) -> str:
        """Call Google Gemini with dynamic text model resolution if requested model is unavailable."""
        import httpx
        clean_key = FinancialAssistantService.clean_api_key(key)
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": clean_key
        }

        # Try user's requested model first if text-capable, then standard candidates
        models_to_try = []
        if model and "1.5-flash" not in model and FinancialAssistantService.is_text_generation_model(model):
            models_to_try.append(model)
        for def_m in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-8b", "gemini-pro"]:
            if def_m not in models_to_try:
                models_to_try.append(def_m)

        async with httpx.AsyncClient(timeout=45.0) as http_client:
            for m in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={clean_key}"
                payload = {
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                    "generationConfig": {"maxOutputTokens": 1000, "temperature": 0.3}
                }
                resp = await http_client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    text = FinancialAssistantService.extract_gemini_text(data)
                    if text:
                        return text
                elif resp.status_code in [400, 404]:
                    continue
                else:
                    err_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    msg = err_data.get("error", {}).get("message", resp.text)
                    raise RuntimeError(f"Google Gemini Error ({resp.status_code}): {msg}")

            # If predefined candidates fail, query ListModels dynamically to get active text models for this key
            list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={clean_key}"
            list_resp = await http_client.get(list_url, headers=headers)
            if list_resp.status_code == 200:
                available = [
                    m["name"].replace("models/", "")
                    for m in list_resp.json().get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])
                    and FinancialAssistantService.is_text_generation_model(m["name"])
                ]
                for live_m in available:
                    if live_m not in models_to_try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{live_m}:generateContent?key={clean_key}"
                        payload = {
                            "system_instruction": {"parts": [{"text": system_prompt}]},
                            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                            "generationConfig": {"maxOutputTokens": 1000, "temperature": 0.3}
                        }
                        resp = await http_client.post(url, json=payload, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            text = FinancialAssistantService.extract_gemini_text(data)
                            if text:
                                return text

        raise RuntimeError(f"Google Gemini Error: Unable to complete request with models {models_to_try}.")

    @staticmethod
    def get_llm_client():
        """Returns configured LLM parameters (provider, model, clean key or client)."""
        openai_key = FinancialAssistantService.clean_api_key(settings.OPENAI_API_KEY)
        gemini_key = FinancialAssistantService.clean_api_key(settings.GEMINI_API_KEY)
        provider = (settings.AI_PROVIDER or "openai").lower()

        from openai import AsyncOpenAI

        # Check Gemini
        if gemini_key and (provider == "gemini" or not openai_key or gemini_key.startswith("AIzaSy") or gemini_key.startswith("AQ.")):
            chosen_model = settings.AI_MODEL or "gemini-2.5-flash"
            if "1.5-flash" in chosen_model or not FinancialAssistantService.is_text_generation_model(chosen_model):
                chosen_model = "gemini-2.5-flash"
            return "gemini", chosen_model, gemini_key

        # Check OpenAI
        if openai_key and (provider == "openai" or not gemini_key or openai_key.startswith("sk-")):
            client = AsyncOpenAI(api_key=openai_key)
            model = settings.AI_MODEL if "gpt" in (settings.AI_MODEL or "").lower() else "gpt-4o-mini"
            return "openai", model, client

        return None, None, None

    @staticmethod
    async def test_key(provider: str, api_key: str, model: Optional[str] = None) -> Dict[str, Any]:
        """Validates an API key by dynamically discovering accessible text models and testing completion."""
        from openai import AsyncOpenAI
        import httpx
        from app.config import save_env_variables

        key = FinancialAssistantService.clean_api_key(api_key)
        if not key:
            return {"success": False, "error": "API key cannot be empty. Please paste your key."}

        # Auto-detect if provider prefix is obvious
        if key.startswith("AIzaSy") or key.startswith("AQ."):
            provider = "gemini"
        elif key.startswith("sk-"):
            provider = "openai"

        # Pre-check common copy-paste errors for Gemini
        if provider == "gemini":
            if key.startswith("AIzaSy"):
                if "." in key:
                    return {
                        "success": False,
                        "error": "Invalid Gemini Key: A standard Gemini key starting with 'AIzaSy' never contains periods ('.'). If you copied an 'AQ.' key, do not prepend 'AIzaSy'."
                    }
                if len(key) < 32 or len(key) > 46:
                    return {
                        "success": False,
                        "error": f"Invalid Key Length: Standard Gemini API keys are 39 characters long (yours has {len(key)} characters)."
                    }
            elif key.startswith("AQ."):
                if len(key) < 40:
                    return {
                        "success": False,
                        "error": f"Invalid Key Length: Gemini Auth Key starting with 'AQ.' appears truncated ({len(key)} characters)."
                    }

        try:
            if provider == "gemini":
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": key
                }
                async with httpx.AsyncClient(timeout=25.0) as http_client:
                    # 1. Ask Google for the exact list of models available for this key
                    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                    r_list = await http_client.get(list_url, headers=headers)
                    
                    if r_list.status_code != 200:
                        err_json = r_list.json() if r_list.headers.get("content-type", "").startswith("application/json") else {}
                        err_message = err_json.get("error", {}).get("message", r_list.text)
                        err_status = err_json.get("error", {}).get("status", "")
                        details_str = str(err_json.get("error", {}).get("details", []))
                        
                        if "ACCESS_TOKEN_TYPE_UNSUPPORTED" in details_str or "ACCESS_TOKEN_TYPE_UNSUPPORTED" in r_list.text:
                            return {
                                "success": False,
                                "error": (
                                    "Google Cloud Project Restriction (ACCESS_TOKEN_TYPE_UNSUPPORTED): "
                                    "This 'AQ.' key was created under an existing Google Cloud project where the Generative Language API is disabled or restricted. "
                                    "Quick 30-Second Fix: In Google AI Studio (https://aistudio.google.com/app/apikey), click '+ Create API key', and select 'Create API key in new project' (instead of selecting an existing project). "
                                    "Google AI Studio will automatically configure permissions and produce an unrestricted key that connects immediately."
                                )
                            }
                        elif "API key not valid" in err_message or err_status == "INVALID_ARGUMENT":
                            return {
                                "success": False,
                                "error": "Google rejected the API key (INVALID_ARGUMENT). Please ensure you copied the key from Google AI Studio without extra prefixes or characters."
                            }
                        elif "PERMISSION_DENIED" in err_status:
                            return {
                                "success": False,
                                "error": "Permission denied: Ensure the 'Generative Language API' is enabled on this project."
                            }
                        elif "RESOURCE_EXHAUSTED" in err_status or "quota" in err_message.lower():
                            return {
                                "success": False,
                                "error": "Google Gemini rate limit / quota exceeded for this key."
                            }
                        else:
                            return {"success": False, "error": f"Gemini Error ({r_list.status_code}): {err_message}"}

                    models_data = r_list.json().get("models", [])
                    # Strictly filter for text generation models only (exclude TTS, audio, image, video)
                    available = [
                        m["name"].replace("models/", "")
                        for m in models_data
                        if "generateContent" in m.get("supportedGenerationMethods", [])
                        and FinancialAssistantService.is_text_generation_model(m["name"])
                    ]

                    if not available:
                        return {
                            "success": False,
                            "error": "Google authenticated your API key, but no text generation models are enabled on this project."
                        }

                    # Order candidate models: requested model first, then standard flash models, then pro, then any
                    candidates = []
                    if model and model in available:
                        candidates.append(model)
                    for pref in ["2.5-flash", "2.0-flash", "1.5-flash-8b", "flash", "pro"]:
                        for a in available:
                            if pref in a.lower() and a not in candidates:
                                candidates.append(a)
                    for a in available:
                        if a not in candidates:
                            candidates.append(a)

                    # 2. Test generation with top candidates from Google's verified text list
                    for test_model in candidates:
                        gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/{test_model}:generateContent?key={key}"
                        r_gen = await http_client.post(
                            gen_url,
                            headers=headers,
                            json={
                                "contents": [{"parts": [{"text": "Say 'OK' in one word"}]}],
                                "generationConfig": {"maxOutputTokens": 100, "temperature": 0.2}
                            }
                        )
                        if r_gen.status_code == 200:
                            data = r_gen.json()
                            reply = FinancialAssistantService.extract_gemini_text(data) or "OK"
                            # Persist verified working model
                            save_env_variables({"AI_MODEL": test_model, "AI_PROVIDER": "gemini", "GEMINI_API_KEY": key})
                            return {
                                "success": True,
                                "message": f"Successfully connected to Google Gemini using active model '{test_model}'!",
                                "reply": reply,
                                "provider": "gemini",
                                "model": test_model,
                                "available_models": available[:6]
                            }
                        elif r_gen.status_code in [400, 404]:
                            # Skip models that return modality mismatch (400) or 404
                            continue
                        else:
                            err_data = r_gen.json() if r_gen.headers.get("content-type", "").startswith("application/json") else {}
                            err_msg = err_data.get("error", {}).get("message", r_gen.text)
                            return {"success": False, "error": f"Gemini Error ({r_gen.status_code}): {err_msg}"}

                    return {
                        "success": False,
                        "error": f"Gemini Error: Could not generate text content with models: {candidates[:3]}"
                    }
            else:
                test_model = model if model and "gpt" in model.lower() else "gpt-4o-mini"
                client = AsyncOpenAI(api_key=key)
                resp = await client.chat.completions.create(
                    model=test_model,
                    messages=[{"role": "user", "content": "Respond with: OK"}],
                    max_tokens=10
                )
                reply = resp.choices[0].message.content.strip()
                return {
                    "success": True,
                    "message": f"Successfully connected to {test_model} via OpenAI!",
                    "reply": reply,
                    "provider": provider,
                    "model": test_model
                }
        except Exception as e:
            err_msg = str(e)
            err_lower = err_msg.lower()
            if "quota" in err_lower or "insufficient_quota" in err_lower:
                err_msg = "OpenAI quota exceeded. Please check your credit balance at https://platform.openai.com/settings/organization/billing."
            elif any(k in err_lower for k in ["please pass a valid api key", "api_key_invalid", "401", "incorrect api key", "invalid_request_error"]):
                err_msg = f"Invalid API key for {provider.upper()}. Please verify you copied the key correctly."
            return {"success": False, "error": err_msg}

    @staticmethod
    async def chat(db: AsyncSession, workspace_id: str, message: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        conv_id = conversation_id or str(uuid.uuid4())
        tool_results = await FinancialAssistantService.execute_tools(db, workspace_id, message)
        data_ctx = tool_results["data_context"]
        tools = tool_results["tools_executed"]

        # Check if an active LLM client is configured
        llm_type, model, client_or_key = FinancialAssistantService.get_llm_client()
        if llm_type:
            try:
                import json
                clean_ctx = json.dumps(data_ctx, indent=2)
                system_prompt = (
                    "You are CashIQ Financial Assistant, an elite AI financial advisor, CFO copilot, and accounting intelligence engine.\n\n"
                    "=== AUTHENTICATED WORKSPACE FINANCIAL METRICS ===\n"
                    f"{clean_ctx}\n"
                    "==================================================\n\n"
                    "CORE DIRECTIVES:\n"
                    "1. ACCURACY & INTEGRITY: For questions specifically about this workspace, business, transactions, cash, burn, or forecasts, strictly cite the verified workspace data above. Never invent fake workspace numbers.\n"
                    "2. GENERAL QUERIES & FINANCIAL EXPERTISE: When the user asks general financial, accounting, startup, tax, economic, or strategic questions (e.g. 'What is EBITDA?', 'How do I calculate runway?', 'How can a business optimize cash flow?', 'Explain accrual vs cash accounting', etc.), provide comprehensive, authoritative, structured, and insightful answers.\n"
                    "3. BLENDED QUESTIONS: When a question relates a general principle to their business, explain the concept clearly and ground it with their actual workspace metrics.\n"
                    "4. CLARITY: Distinguish historical facts from projections. Format using clean GitHub markdown formatting (bold terms, bullet points, headers) for readability."
                )

                if llm_type == "gemini":
                    ai_reply = await FinancialAssistantService.call_gemini(
                        model=model,
                        key=client_or_key,
                        system_prompt=system_prompt,
                        user_prompt=message
                    )
                else:
                    response = await client_or_key.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": message}
                        ],
                        max_tokens=800
                    )
                    ai_reply = response.choices[0].message.content

                return {
                    "response": ai_reply,
                    "conversation_id": conv_id,
                    "tools_executed": tools,
                    "model_used": model,
                    "provider": llm_type
                }
            except Exception as e:
                print(f"[AssistantService] LLM API call error: {e}. Falling back to deterministic engine.")

        # Deterministic financial intelligence synthesis engine
        text_parts = []
        q = message.lower()

        if "why did my expenses increase" in q or "expenses increase" in q or "biggest expense" in q or "spend" in q:
            comp = data_ctx.get("category_spend_comparison", [])
            if comp:
                text_parts.append("**Month-over-Month Expense Analysis:**\n")
                for c in comp:
                    text_parts.append(f"• **{c['category']}**: Currently {c['current_30d']} vs {c['previous_30d']} previously (Net change: {c['change']})")
                top = comp[0]
                text_parts.append(f"\nThe largest driver was **{top['category']}**, which changed by {top['change']}.")
            else:
                text_parts.append("Expense records indicate consistent spending across all categories with no anomalous surges.")

        elif "payment" in q or "due" in q or "payable" in q:
            pays = data_ctx.get("upcoming_payables", [])
            if pays:
                text_parts.append("**Upcoming Vendor Obligations & Payables:**\n")
                for p in pays:
                    text_parts.append(f"• **{p['vendor']}**: {p['amount']} (Due: {p['due_date']}, Status: {p['status']})")
            else:
                text_parts.append("You have no pending or overdue payables due at this time.")

        elif "receivable" in q or "client" in q or "incoming" in q or "invoice" in q:
            recs = data_ctx.get("upcoming_receivables", [])
            if recs:
                text_parts.append("**Expected Client Inflows & Receivables:**\n")
                for r in recs:
                    text_parts.append(f"• **{r['client']}**: {r['amount']} (Expected Due: {r['due_date']}, Status: {r['status']})")
            else:
                text_parts.append("No active uncollected client invoices are currently logged.")

        elif "forecast" in q or "cash position" in q or "runway" in q or "next month" in q:
            fc = data_ctx.get("cash_flow_forecast", {})
            if fc:
                text_parts.append(f"**Cash Position Projection ({fc.get('classification', 'projected').capitalize()} Model):**\n")
                text_parts.append(f"• **Current Available Cash:** {fc.get('current_balance')}")
                text_parts.append(f"• **Projected 30-Day Ending Cash:** {fc.get('projected_end_30d_balance')}")
                text_parts.append(f"• **Lowest Expected Cash Point:** {fc.get('lowest_projected_balance')}")
                text_parts.append(f"\n*Note: This projection is classified as an **{fc.get('classification')}** using verified cash flow patterns and scheduled obligations.*")
            else:
                text_parts.append("Forecasting models require baseline transaction records to establish accurate trajectory.")

        else:
            summary = data_ctx.get("dashboard_summary", {})
            text_parts.append("**CashIQ Workspace Financial Summary:**\n")
            if "current_cash" in summary:
                text_parts.append(f"• **Current Cash Position:** {summary['current_cash']}")
            if "last_30d_income" in summary:
                text_parts.append(f"• **Last 30 Days Income:** {summary['last_30d_income']}")
                text_parts.append(f"• **Last 30 Days Expenses:** {summary['last_30d_expenses']}")
                text_parts.append(f"• **Net Cash Flow:** {summary['net_cash_flow']}")
            
            insights = data_ctx.get("active_insights", [])
            if insights:
                text_parts.append("\n**Key Active Insights:**")
                for i in insights:
                    text_parts.append(f"• **{i['title']}**: {i['description']}")

            text_parts.append("\n\n---\n*💡 **Pro Tip**: To answer any general financial questions, explain complex accounting, or get strategic CFO advice, add your OpenAI or Google Gemini API key in **Settings > AI Assistant**.*")

        response_text = "\n".join(text_parts)
        return {
            "response": response_text,
            "conversation_id": conv_id,
            "tools_executed": tools,
            "model_used": "deterministic-rules",
            "provider": "local"
        }
