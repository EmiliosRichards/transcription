from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Local import (keep this folder runnable without packaging).
from pitch_engine import generate_sales_pitch_for_company


def _truthy(s: str | None) -> bool:
    return (s or "").strip().lower() in {"1", "true", "yes", "y", "on"}


app = FastAPI(title="Manuav Sales Pitch (handover bucket v2)")

# Load .env for local dev only (prod should inject env vars).
if not os.environ.get("PYTEST_CURRENT_TEST"):
    load_dotenv(override=False)


_cors = (os.environ.get("CORS_ALLOW_ORIGINS") or "").strip()
if _cors:
    origins = [o.strip() for o in _cors.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )


class PitchRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    company_name: Optional[str] = Field(default="", max_length=200)
    description: Optional[str] = Field(default=None, description="Optional; if absent, service will summarize via web search.")
    eval_positives: list[str] = Field(default_factory=list)
    eval_concerns: list[str] = Field(default_factory=list)
    fit_attributes: Dict[str, Any] = Field(default_factory=dict)


class PitchResponse(BaseModel):
    matched_partner_name: str
    sales_pitch: str
    sales_pitch_template: str
    match_reasoning: list[str]
    avg_leads_per_day: Optional[int] = None
    debug: Optional[Dict[str, Any]] = None


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/pitch", response_model=PitchResponse)
def pitch(req: PitchRequest) -> PitchResponse:
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
            prompts_dir=Path(__file__).resolve().parents[1] / "prompts",
            golden_partners_csv=Path(os.environ.get("GOLDEN_PARTNERS_CSV") or "kgs_001_ER47_20250626.csv").resolve(),
        )

        partner_match = (out.get("partner_match") or {}) if isinstance(out.get("partner_match"), dict) else {}
        matched_partner = (out.get("matched_partner") or {}) if isinstance(out.get("matched_partner"), dict) else {}
        matched_partner_name = str(partner_match.get("matched_partner_name") or "")
        sales_pitch_filled = str(out.get("sales_pitch_filled") or "")
        sales_pitch_template = str(out.get("sales_pitch_template") or "")
        match_reasoning = (
            ((out.get("sales_pitch") or {}) if isinstance(out.get("sales_pitch"), dict) else {}).get("match_rationale_features")
            or partner_match.get("match_rationale_features")
            or []
        )
        if not isinstance(match_reasoning, list):
            match_reasoning = [str(match_reasoning)]

        debug = out if _truthy(os.environ.get("COMPANY_PITCH_DEBUG")) else None
        avg = matched_partner.get("avg_leads_per_day")
        try:
            avg_i = int(avg) if avg is not None else None
        except Exception:
            avg_i = None

        return PitchResponse(
            matched_partner_name=matched_partner_name,
            sales_pitch=sales_pitch_filled,
            sales_pitch_template=sales_pitch_template,
            match_reasoning=[str(x) for x in match_reasoning if str(x).strip()],
            avg_leads_per_day=avg_i,
            debug=debug,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")

