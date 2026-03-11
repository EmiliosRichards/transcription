from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field

from app.config import settings
from app.services.company_intel import evaluate_company_url, generate_sales_pitch_for_company


router = APIRouter()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def _expected_api_key() -> str:
    # Prefer a dedicated key if present; fallback to the shared API_KEY.
    return (os.environ.get("COMPANY_API_KEY") or settings.API_KEY or "").strip()


async def require_api_key(api_key: str = Security(api_key_header)) -> str:
    expected = _expected_api_key()
    if not expected:
        raise HTTPException(status_code=500, detail="Missing API key config (set COMPANY_API_KEY or API_KEY).")
    if api_key != expected:
        raise HTTPException(status_code=403, detail="Could not validate credentials")
    return api_key


class CompanyEvaluateRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048, description="Company website URL")
    include_description: bool = Field(default=True, description="Also produce a description blob for downstream pitch generation")


class CompanyEvaluateResponse(BaseModel):
    input_url: str
    company_name: str
    score: float
    confidence: str
    reasoning: str
    positives: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    fit_attributes: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None
    meta: Dict[str, Any]


class CompanyPitchRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048, description="Company website URL")
    company_name: Optional[str] = Field(default="", description="Optional company name")
    description: Optional[str] = Field(default=None, description="Optional description text to reuse (from evaluation step)")
    eval_positives: list[str] = Field(default_factory=list, description="Optional evaluator positives (German)")
    eval_concerns: list[str] = Field(default_factory=list, description="Optional evaluator concerns (German)")
    fit_attributes: Dict[str, Any] = Field(default_factory=dict, description="Optional structured fit attributes from evaluation step")
    pitch_template: Optional[str] = Field(
        default="bullets",
        description='Optional pitch template selector. Supported: "bullets" (current) | "classic" (2 sentences + CTA).',
    )


@router.post("/company/evaluate", response_model=CompanyEvaluateResponse, tags=["Company"])
def evaluate_company(req: CompanyEvaluateRequest, _api_key: str = Security(require_api_key)) -> CompanyEvaluateResponse:
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY on server.")
    try:
        out = evaluate_company_url(url=req.url, include_description=bool(req.include_description))
        return CompanyEvaluateResponse(
            input_url=str(out.get("input_url") or ""),
            company_name=str(out.get("company_name") or ""),
            score=float(out.get("score") or 0),
            confidence=str(out.get("confidence") or "low"),
            reasoning=str(out.get("reasoning") or ""),
            positives=list(out.get("positives") or []),
            concerns=list(out.get("concerns") or []),
            fit_attributes=dict(out.get("fit_attributes") or {}),
            description=(str(out.get("description") or "").strip() or None),
            meta=dict(out.get("meta") or {}),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Treat provider errors as 502 for cleaner UI handling.
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")


@router.post("/company/pitch", tags=["Company"])
def generate_pitch(req: CompanyPitchRequest, _api_key: str = Security(require_api_key)) -> Dict[str, Any]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY on server.")
    try:
        out = generate_sales_pitch_for_company(
            company_url=req.url,
            company_name=req.company_name or "",
            description=req.description,
            eval_positives=req.eval_positives,
            eval_concerns=req.eval_concerns,
            eval_fit_attributes=req.fit_attributes,
            pitch_template=req.pitch_template,
        )
        # Shape the response to what the UI needs now:
        partner_match = (out.get("partner_match") or {}) if isinstance(out.get("partner_match"), dict) else {}
        sales_pitch = (out.get("sales_pitch") or {}) if isinstance(out.get("sales_pitch"), dict) else {}

        matched_partner_name = str(partner_match.get("matched_partner_name") or "")
        # Prefer filled pitch if available; fallback to raw template.
        phone_sales_line = str(out.get("sales_pitch_filled") or sales_pitch.get("phone_sales_line") or "")
        match_reasoning = sales_pitch.get("match_rationale_features") or partner_match.get("match_rationale_features") or []
        if not isinstance(match_reasoning, list):
            match_reasoning = [str(match_reasoning)]

        resp: Dict[str, Any] = {
            "matched_partner_name": matched_partner_name,
            "sales_pitch": phone_sales_line,
            "sales_pitch_template": str(out.get("sales_pitch_template") or sales_pitch.get("phone_sales_line") or ""),
            "match_reasoning": match_reasoning,
            "avg_leads_per_day": ((out.get("matched_partner") or {}) if isinstance(out.get("matched_partner"), dict) else {}).get("avg_leads_per_day"),
        }
        # Optional: include debug payload when explicitly enabled server-side.
        if os.environ.get("COMPANY_PITCH_DEBUG", "").strip().lower() in {"1", "true", "yes", "y"}:
            resp["debug"] = out
        return resp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")

