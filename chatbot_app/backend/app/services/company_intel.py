from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI
from openai.types.responses.response_usage import ResponseUsage

from app.services.manuav_eval import evaluate_company_with_usage_and_web_search_artifacts


def _app_dir() -> Path:
    # .../chatbot_app/backend/app/services/<this_file>
    return Path(__file__).resolve().parents[1]


PROMPTS_DIR = _app_dir() / "prompts" / "company_pitch"
DATA_DIR = _app_dir() / "data"


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        raise ValueError("URL is empty.")
    if len(u) > 2048:
        raise ValueError("URL is too long.")
    if not u.lower().startswith(("http://", "https://")):
        u = f"https://{u}"
    return u


def _extract_json_text(resp: Any) -> str:
    if hasattr(resp, "output_text") and isinstance(resp.output_text, str) and resp.output_text.strip():
        return resp.output_text
    parts: List[str] = []
    for item in getattr(resp, "output", []) or []:
        for c in getattr(item, "content", []) or []:
            t = getattr(c, "text", None)
            if isinstance(t, str) and t.strip():
                parts.append(t)
    if parts:
        return "\n".join(parts)
    raise RuntimeError("Could not extract text output from OpenAI response.")


def _responses_json(
    *,
    model: str,
    schema_name: str,
    json_schema: Dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    max_tool_calls: Optional[int] = None,
    timeout_seconds: Optional[float] = None,
) -> Tuple[Dict[str, Any], Optional[ResponseUsage], Dict[str, Any]]:
    client = OpenAI()
    call_client = client
    if timeout_seconds is not None and hasattr(client, "with_options"):
        call_client = client.with_options(timeout=float(timeout_seconds))

    create_kwargs: Dict[str, Any] = {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": json_schema,
            }
        },
    }
    if tools:
        create_kwargs["tools"] = tools
    if max_tool_calls is not None:
        create_kwargs["max_tool_calls"] = int(max_tool_calls)

    resp = call_client.responses.create(**create_kwargs)
    text = _extract_json_text(resp)
    return json.loads(text), getattr(resp, "usage", None), {}


def load_golden_partners() -> List[Dict[str, Any]]:
    """
    Loads golden partners from either:
    - env `GOLDEN_PARTNERS_JSON` (JSON array), or
    - env `GOLDEN_PARTNERS_PATH` (path to JSON or XLSX), or
    - repo-root `kgs_001_ER47_20250626.xlsx` (if present), or
    - bundled `app/data/golden_partners.json` (fallback)
    """
    env_json = (os.environ.get("GOLDEN_PARTNERS_JSON") or "").strip()
    if env_json:
        data = json.loads(env_json)
        if not isinstance(data, list):
            raise ValueError("GOLDEN_PARTNERS_JSON must be a JSON array.")
        return data

    def _repo_root() -> Path:
        """
        Best-effort repo/service root resolution.

        Locally, this code lives at:
          <repo>/chatbot_app/backend/app/...
        so the repo root is typically 2 levels above `backend/app`.

        On Railway, the service is often deployed with the service directory as
        the filesystem root (e.g. `/app`), so `backend/app` may effectively be
        `/app/app` and does NOT have 3+ parent levels. In that case, we fall
        back to the service root.
        """
        app_dir = _app_dir()
        # Walk upwards looking for a repo marker or the XLSX itself.
        markers = [
            "kgs_001_ER47_20250626.xlsx",
            ".git",
            "railway.toml",
            "railway.json",
        ]
        for base in [app_dir, *list(app_dir.parents)]:
            try:
                for m in markers:
                    if (base / m).exists():
                        return base
            except Exception:
                # Extremely defensive: just keep walking.
                pass

        # Fallback: assume the service root is the parent of `app/`.
        return app_dir.parent if app_dir.parent.exists() else app_dir

    def _resolve_path(p: Path) -> Path:
        if p.is_absolute():
            return p
        # Try relative to repo root first (Railway root directory deployments can vary).
        cand = (_repo_root() / p).resolve()
        if cand.exists():
            return cand
        return p

    def _split_listish(s: str) -> List[str]:
        raw = (s or "").strip()
        if not raw:
            return []
        # Prefer semicolons; fall back to commas.
        parts = [p.strip() for p in raw.split(";")] if ";" in raw else [p.strip() for p in raw.split(",")]
        return [p for p in parts if p]

    def _load_from_xlsx(path: Path) -> List[Dict[str, Any]]:
        try:
            import pandas as pd  # type: ignore
        except Exception as e:  # pragma: no cover
            raise ValueError(f"Reading XLSX requires pandas. Import failed: {type(e).__name__}: {e}")
        try:
            df = pd.read_excel(path, sheet_name=0)
        except Exception as e:
            raise ValueError(f"Failed to read golden partners XLSX: {path} ({type(e).__name__}: {e})")

        df.columns = [str(c).strip() for c in df.columns]

        # Optional filter: only keep successful partners
        if "Is Successful Partner" in df.columns:
            try:
                df = df[df["Is Successful Partner"] == True]  # noqa: E712
            except Exception:
                pass

        def _cell_str(v: Any) -> str:
            try:
                if pd.isna(v):
                    return ""
            except Exception:
                pass
            return str(v).strip()

        def _cell_int(v: Any) -> Optional[int]:
            try:
                if pd.isna(v):
                    return None
            except Exception:
                pass
            try:
                # Excel numbers often come in as float
                return int(float(v))
            except Exception:
                s = _cell_str(v)
                if not s:
                    return None
                try:
                    return int(s)
                except Exception:
                    return None

        partners: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            name = _cell_str(row.get("Company Name"))
            if not name:
                continue

            industry = _cell_str(row.get("Industry"))
            products = _cell_str(row.get("Products/Services Offered"))
            usp = _cell_str(row.get("USP (Unique Selling Proposition) / Key Selling Points"))
            segments = _cell_str(row.get("Customer Target Segments"))
            business_model = _cell_str(row.get("Business Model"))
            geo = _cell_str(row.get("Geographic Reach"))
            website = _cell_str(row.get("Website"))
            notes = _cell_str(row.get("Source Document Section/Notes"))

            avg = _cell_int(row.get("Avg Leads Per Day")) or 0
            rank = _cell_int(row.get("Rank (1-47)")) or _cell_int(row.get("Rank")) or 0

            target_segments = _split_listish(segments)

            partner_description_parts = []
            if industry:
                partner_description_parts.append(f"Industry: {industry}")
            if products:
                partner_description_parts.append(f"Products/Services: {products}")
            if usp:
                partner_description_parts.append(f"USP: {usp}")
            if business_model:
                partner_description_parts.append(f"Business model: {business_model}")
            if geo:
                partner_description_parts.append(f"Geo: {geo}")
            if website:
                partner_description_parts.append(f"Website: {website}")

            partners.append(
                {
                    "name": name,
                    "rank": int(rank) if rank else None,
                    "avg_leads_per_day": int(avg) if avg else None,
                    "industry": industry or None,
                    "target_segments": target_segments,
                    "partner_description": " | ".join(partner_description_parts)[:2000] if partner_description_parts else None,
                    "case_study_summary": (notes or "").strip() or None,
                }
            )

        # Sort by rank if present.
        partners.sort(key=lambda p: (p.get("rank") is None, p.get("rank") or 10**9, p.get("name") or ""))
        return partners

    env_path = (os.environ.get("GOLDEN_PARTNERS_PATH") or "").strip()
    if env_path:
        path = _resolve_path(Path(env_path))
    else:
        # Repo-root XLSX (provided by user) – auto-detect if present.
        path = _repo_root() / "kgs_001_ER47_20250626.xlsx"
        if not path.exists():
            path = DATA_DIR / "golden_partners.json"

    if str(path).lower().endswith((".xlsx", ".xls")):
        return _load_from_xlsx(path)

    data = json.loads(_load_text(path))
    if not isinstance(data, list):
        raise ValueError(f"Golden partners file must contain a JSON array: {path}")
    return data


def summarize_company_from_url(
    *,
    url: str,
    company_name_hint: str = "",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Uses OpenAI web_search tool to produce a compact company description blob suitable
    for attribute extraction + partner matching + pitch generation.
    """
    url = normalize_url(url)
    model = (model or os.environ.get("COMPANY_INTEL_MODEL") or "gpt-4o-mini").strip()
    if not model:
        raise ValueError("Missing COMPANY_INTEL_MODEL (empty).")

    schema: Dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "input_url": {"type": "string"},
            "company_name": {"type": "string"},
            "description": {"type": "string", "maxLength": 3000},
            "highlights": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
        },
        "required": ["input_url", "company_name", "description", "highlights"],
    }

    system_prompt = (
        "You are a concise B2B company analyst. "
        "You will research the company using the web search tool and produce a factual description for sales analysis. "
        "Do not hallucinate; if uncertain, say so plainly."
    )
    user_prompt = f"""\
Research the company behind this website URL and produce a compact description for later analysis.

Requirements:
- Use the web search tool (required).
- Prefer the company's own website (home, product, pricing, cases, careers, legal/imprint/contact) and corroborate with 1-2 reputable third-party sources when possible.
- Output JSON only (no markdown).
- Write `description` in German (short, information-dense paragraph).
- Write `highlights` in German (5-10 bullet-like strings) capturing concrete facts (ICP, Produkt, Pricing-Signale, Region-Fokus, Business Model, etc.).
- If something is unclear, state uncertainty explicitly in German rather than guessing.

Input URL: {url}
Company name hint (may be blank): {company_name_hint}
"""

    result, _usage, _meta = _responses_json(
        model=model,
        schema_name="company_description",
        json_schema=schema,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tools=[{"type": "web_search_preview"}],
        max_tool_calls=int(os.environ.get("COMPANY_INTEL_MAX_TOOL_CALLS", "2") or 2),
        timeout_seconds=float(os.environ.get("COMPANY_INTEL_TIMEOUT_SECONDS", "60") or 60),
    )
    # Ensure the input_url matches the normalized URL for downstream determinism.
    if isinstance(result, dict):
        result["input_url"] = url
        if company_name_hint and not str(result.get("company_name") or "").strip():
            result["company_name"] = company_name_hint
    return result


def evaluate_company_url(
    *,
    url: str,
    model: Optional[str] = None,
    include_description: bool = True,
) -> Dict[str, Any]:
    """
    Returns:
    - score (0..10)
    - confidence (low/medium/high)
    - reasoning
    - company_name
    - description (optional)
    """
    url = normalize_url(url)
    # Default to a widely-available, lower-cost model unless overridden.
    model = (model or os.environ.get("COMPANY_EVAL_MODEL") or "gpt-5.1-2025-11-13").strip()
    if not model:
        raise ValueError("Missing COMPANY_EVAL_MODEL (empty).")

    # Run rubric-based evaluator (OpenAI responses + web search tool).
    res, usage, billed_q, citations = evaluate_company_with_usage_and_web_search_artifacts(
        url,
        model,
        max_tool_calls=int(os.environ.get("COMPANY_EVAL_MAX_TOOL_CALLS", "2") or 2),
        # Default ON to reduce domain/lookalike misattribution (can still be disabled explicitly).
        second_query_on_uncertainty=(
            os.environ.get("COMPANY_EVAL_SECOND_QUERY", "1").strip().lower() in {"1", "true", "yes", "y"}
        ),
    )

    score = float(res.get("manuav_fit_score", 0))
    company_name = str(res.get("company_name") or "").strip()
    confidence = str(res.get("confidence") or "").strip().lower() or "low"
    reasoning = str(res.get("reasoning") or "").strip()

    out: Dict[str, Any] = {
        "input_url": url,
        "company_name": company_name,
        "score": score,
        "confidence": confidence,
        "reasoning": reasoning,
        "meta": {
            "model": model,
            "web_search_calls": int(billed_q),
            "url_citations": citations,
            "usage": usage.model_dump() if usage is not None and hasattr(usage, "model_dump") else None,
        },
    }

    if include_description:
        out["description_bundle"] = summarize_company_from_url(url=url, company_name_hint=company_name)
        out["description"] = str((out["description_bundle"] or {}).get("description") or "").strip()
    return out


def _render_partner_summaries(partners: List[Dict[str, Any]]) -> str:
    # Prompt-friendly format: JSON list is usually easiest for the model to scan.
    compact = []
    for p in partners:
        compact.append(
            {
                "name": p.get("name", ""),
                "rank": p.get("rank", None),
                "avg_leads_per_day": p.get("avg_leads_per_day", None),
                "industry": p.get("industry", None),
                "target_segments": p.get("target_segments", None),
                "partner_description": p.get("partner_description", None),
                "case_study_summary": p.get("case_study_summary", None),
            }
        )
    return json.dumps(compact, ensure_ascii=False, indent=2)


def _prompt_from_template(path: Path, replacements: Dict[str, str]) -> str:
    txt = _load_text(path)
    for k, v in replacements.items():
        txt = txt.replace(k, v)
    return txt


def generate_sales_pitch_for_company(
    *,
    company_url: str,
    company_name: str = "",
    description: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates:
    - extracted attributes
    - matched golden partner
    - German sales pitch line
    - match reasoning
    """
    url = normalize_url(company_url)
    model = (model or os.environ.get("COMPANY_PITCH_MODEL") or "gpt-4o-mini").strip()
    if not model:
        raise ValueError("Missing COMPANY_PITCH_MODEL (empty).")

    if not description or not str(description).strip():
        desc_bundle = summarize_company_from_url(url=url, company_name_hint=company_name)
        description = str(desc_bundle.get("description") or "").strip()
    else:
        desc_bundle = {"input_url": url, "company_name": company_name, "description": description, "highlights": []}

    # 1) Extract attributes from description
    attr_prompt = _prompt_from_template(
        PROMPTS_DIR / "attribute_extractor_prompt.txt",
        {"{{WEBSITE_SUMMARY_TEXT_PLACEHOLDER}}": description or ""},
    )
    attr_schema: Dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "input_summary_url": {"type": "string"},
            "b2b_indicator": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
            "phone_outreach_suitability": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
            "target_group_size_assessment": {"type": "string"},
            "industry": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "products_services_offered": {"type": "array", "items": {"type": "string"}},
            "usp_key_selling_points": {"type": "array", "items": {"type": "string"}},
            "customer_target_segments": {"type": "array", "items": {"type": "string"}},
            "business_model": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "company_size_indicators_text": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "company_size_category_inferred": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "innovation_level_indicators_text": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "website_clarity_notes": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
        "required": [
            "input_summary_url",
            "b2b_indicator",
            "phone_outreach_suitability",
            "target_group_size_assessment",
            "industry",
            "products_services_offered",
            "usp_key_selling_points",
            "customer_target_segments",
            "business_model",
            "company_size_indicators_text",
            "company_size_category_inferred",
            "innovation_level_indicators_text",
            "website_clarity_notes",
        ],
    }
    attrs, _u1, _ = _responses_json(
        model=model,
        schema_name="company_attributes",
        json_schema=attr_schema,
        system_prompt="You extract structured company attributes from short summaries.",
        user_prompt=attr_prompt,
        tools=None,
        timeout_seconds=float(os.environ.get("COMPANY_PITCH_TIMEOUT_SECONDS", "60") or 60),
    )
    if isinstance(attrs, dict):
        attrs["input_summary_url"] = url

    # 2) Match partner
    partners = load_golden_partners()
    partner_summaries = _render_partner_summaries(partners)
    pm_prompt = _prompt_from_template(
        PROMPTS_DIR / "german_partner_matching_prompt.txt",
        {
            "{{TARGET_COMPANY_ATTRIBUTES_JSON_PLACEHOLDER}}": json.dumps(attrs, ensure_ascii=False, indent=2),
            "{{GOLDEN_PARTNER_SUMMARIES_PLACEHOLDER}}": partner_summaries,
        },
    )
    pm_schema: Dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "match_score": {"type": "string", "enum": ["High", "Medium", "Low"]},
            "matched_partner_name": {"type": "string"},
            "match_rationale_features": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        },
        "required": ["match_score", "matched_partner_name", "match_rationale_features"],
    }
    partner_match, _u2, _ = _responses_json(
        model=model,
        schema_name="partner_match",
        json_schema=pm_schema,
        system_prompt="Du matchst Unternehmen mit passenden Fallstudien (Golden Partner).",
        user_prompt=pm_prompt,
        tools=None,
        timeout_seconds=float(os.environ.get("COMPANY_PITCH_TIMEOUT_SECONDS", "60") or 60),
    )

    matched_name = str((partner_match or {}).get("matched_partner_name") or "").strip()
    match_score = str((partner_match or {}).get("match_score") or "").strip()

    def _is_no_match(name: str, score: str) -> bool:
        if not name:
            return True
        n = name.strip().lower()
        if n in {
            "no suitable match found",
            "no suitable match",
            "no match",
            "none",
            "n/a",
            "-",
        }:
            return True
        if score.strip().lower() == "low" and n.startswith("no"):
            return True
        return False

    matched_partner = None
    if matched_name and not _is_no_match(matched_name, match_score):
        for p in partners:
            if str(p.get("name") or "").strip() == matched_name:
                matched_partner = p
                break

    no_match = matched_partner is None
    if no_match:
        # Normalize the model output so the UI is consistent.
        partner_match = {
            "match_score": "Low",
            "matched_partner_name": "No suitable match found",
            "match_rationale_features": [],
        }

    # 3) Generate pitch
    prev_rationale = (partner_match or {}).get("match_rationale_features") or []
    sp_template = (
        PROMPTS_DIR / "german_sales_pitch_generation_prompt_no_match.txt"
        if no_match
        else PROMPTS_DIR / "german_sales_pitch_generation_prompt.txt"
    )
    sp_replacements = {
        "{{TARGET_COMPANY_ATTRIBUTES_JSON_PLACEHOLDER}}": json.dumps(attrs, ensure_ascii=False, indent=2),
    }
    if not no_match:
        sp_replacements["{{PREVIOUS_MATCH_RATIONALE_PLACEHOLDER}}"] = json.dumps(prev_rationale, ensure_ascii=False, indent=2)
        sp_replacements["{{MATCHED_GOLDEN_PARTNER_JSON_PLACEHOLDER}}"] = json.dumps(matched_partner or {}, ensure_ascii=False, indent=2)
    sp_prompt = _prompt_from_template(sp_template, sp_replacements)
    sp_schema: Dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "match_rationale_features": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            "phone_sales_line": {"type": "string", "maxLength": 1200},
        },
        "required": ["match_rationale_features", "phone_sales_line"],
    }
    sales_pitch, _u3, _ = _responses_json(
        model=model,
        schema_name="sales_pitch",
        json_schema=sp_schema,
        system_prompt="Du schreibst eine kurze, überzeugende, beratende Sales-Line auf Deutsch.",
        user_prompt=sp_prompt,
        tools=None,
        timeout_seconds=float(os.environ.get("COMPANY_PITCH_TIMEOUT_SECONDS", "60") or 60),
    )

    # Optionally fill the placeholder using matched partner avg leads/day.
    avg_leads = None
    try:
        avg_leads = (matched_partner or {}).get("avg_leads_per_day") if isinstance(matched_partner, dict) else None
    except Exception:
        avg_leads = None
    sales_pitch_template = str((sales_pitch or {}).get("phone_sales_line") or "")
    sales_pitch_filled = sales_pitch_template
    if not no_match:
        # Only fill lead placeholders when we actually have a matched partner case study.
        if avg_leads is not None:
            # Support both the new and legacy placeholder tokens.
            sales_pitch_filled = (
                sales_pitch_template.replace("{avg_leads_per_day}", str(int(avg_leads)))
                .replace("{programmatic placeholder}", str(int(avg_leads)))
            )
        else:
            # Ensure we never leak placeholder tokens to the UI.
            sales_pitch_filled = (
                sales_pitch_template.replace("{avg_leads_per_day}", "mehrere")
                .replace("{programmatic placeholder}", "mehrere")
            )
    else:
        # Make the "match reasoning" section explicit in the UI.
        if isinstance(sales_pitch, dict):
            sales_pitch.setdefault(
                "match_rationale_features",
                ["Kein passender Golden-Partner-Match gefunden; generischer Pitch ohne Fallstudie."],
            )

    return {
        "inputs": {"company_url": url, "company_name": company_name},
        "description_bundle": desc_bundle,
        "attributes": attrs,
        "partner_match": partner_match,
        "matched_partner": matched_partner,
        "sales_pitch": sales_pitch,
        "sales_pitch_template": sales_pitch_template,
        "sales_pitch_filled": sales_pitch_filled,
    }

