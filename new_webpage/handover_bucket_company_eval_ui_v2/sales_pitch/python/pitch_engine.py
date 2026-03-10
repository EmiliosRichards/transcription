from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI


# ----------------------------
# Small helpers
# ----------------------------


def normalize_url(url: str) -> str:
    s = (url or "").strip()
    if not s:
        return ""
    if s.lower().startswith(("http://", "https://")):
        return s
    return f"https://{s}"


def _extract_json_text(resp: Any) -> str:
    if hasattr(resp, "output_text") and isinstance(resp.output_text, str) and resp.output_text.strip():
        return resp.output_text
    try:
        parts = []
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                t = getattr(c, "text", None)
                if isinstance(t, str) and t.strip():
                    parts.append(t)
        if parts:
            return "\n".join(parts)
    except Exception:
        pass
    raise RuntimeError("Could not extract text output from OpenAI response.")


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _prompt_from_template(path: Path, replacements: Dict[str, str]) -> str:
    txt = _load_text(path)
    for k, v in replacements.items():
        txt = txt.replace(k, v)
    return txt


def _responses_json(
    *,
    model: str,
    schema_name: str,
    json_schema: Dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    max_tool_calls: Optional[int] = None,
    timeout_seconds: float = 60.0,
) -> Tuple[Dict[str, Any], Any]:
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
    return json.loads(text), getattr(resp, "usage", None)


# ----------------------------
# Golden partners loader (CSV)
# ----------------------------


EXCLUDED_PARTNER_NAMES = {"pnp media", "visitronic gmbh"}


def _split_listish(s: str) -> List[str]:
    raw = (s or "").strip()
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(";")] if ";" in raw else [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def _cell_bool(v: Any) -> Optional[bool]:
    s = str(v or "").strip().lower()
    if not s:
        return None
    if s in {"not found", "unknown", "n/a", "na", "none", "-"}:
        return None
    if s in {"0", "false", "no", "n"}:
        return False
    if s in {"1", "true", "yes", "y", "t"}:
        return True
    return None


def _cell_int(v: Any) -> Optional[int]:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def load_golden_partners_from_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    partners: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("Company Name") or "").strip()
        if not name:
            continue
        if name.strip().lower() in EXCLUDED_PARTNER_NAMES:
            continue

        industry = str(row.get("Industry") or "").strip() or None
        products = str(row.get("Products/Services Offered") or "").strip() or None
        usp = str(row.get("USP (Unique Selling Proposition) / Key Selling Points") or "").strip() or None
        segments_raw = str(row.get("Customer Target Segments") or "").strip()
        business_model = str(row.get("Business Model") or "").strip() or None
        company_size_indicators_text = str(row.get("Company Size Indicators") or "").strip() or None
        innovation_level_indicators_text = str(row.get("Innovation Level Indicators") or "").strip() or None
        targets_specific_industry_type_raw = str(row.get("Targets_Specific_Industry_Type") or "").strip()

        avg = _cell_int(row.get("Avg Leads Per Day")) or 0
        rank = _cell_int(row.get("Rank (1-47)")) or _cell_int(row.get("Rank")) or 0

        target_segments = _split_listish(segments_raw)
        targets_specific_industry_type = _split_listish(targets_specific_industry_type_raw)

        partners.append(
            {
                "name": name,
                "rank": int(rank) if rank else None,
                "avg_leads_per_day": int(avg) if avg else None,
                "industry": industry,
                "target_segments": target_segments,
                "products_services_offered": products,
                "usp_key_selling_points": usp,
                "business_model": business_model,
                "company_size_indicators_text": company_size_indicators_text,
                "innovation_level_indicators_text": innovation_level_indicators_text,
                "targets_specific_industry_type": targets_specific_industry_type,
                "is_startup": _cell_bool(row.get("Is_Startup")),
                "is_ai_software": _cell_bool(row.get("Is_AI_Software")),
                "is_innovative_product": _cell_bool(row.get("Is_Innovative_Product")),
                "is_disruptive_product": _cell_bool(row.get("Is_Disruptive_Product")),
                "is_vc_funded": _cell_bool(row.get("Is_VC_Funded")),
                "is_saas_software": _cell_bool(row.get("Is_SaaS_Software")),
                "is_complex_solution": _cell_bool(row.get("Is_Complex_Solution")),
                "is_investment_product": _cell_bool(row.get("Is_Investment_Product")),
            }
        )

    partners.sort(key=lambda p: (p.get("rank") is None, p.get("rank") or 10**9, p.get("name") or ""))
    return partners


def _render_partner_summaries(partners: List[Dict[str, Any]]) -> str:
    def _trunc(v: Any, n: int) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return (s[:n] + "…") if len(s) > n else s
        return v

    compact: List[Dict[str, Any]] = []
    for p in partners:
        compact.append(
            {
                "name": p.get("name", ""),
                "industry": _trunc(p.get("industry", None), 220),
                "target_segments": p.get("target_segments", []) or [],
                "products_services_offered": _trunc(p.get("products_services_offered", None), 360),
                "business_model": _trunc(p.get("business_model", None), 220),
                "targets_specific_industry_type": p.get("targets_specific_industry_type", []) or [],
                "is_startup": p.get("is_startup", None),
                "is_ai_software": p.get("is_ai_software", None),
                "is_saas_software": p.get("is_saas_software", None),
                "is_complex_solution": p.get("is_complex_solution", None),
            }
        )
    return json.dumps(compact, ensure_ascii=False, indent=2)


# ----------------------------
# Pitch pipeline
# ----------------------------


@dataclass(frozen=True)
class DescriptionBundle:
    input_url: str
    company_name: str
    description: str
    highlights: List[str]


def summarize_company_from_url(
    *,
    url: str,
    company_name_hint: str = "",
    model: str,
    max_tool_calls: int = 3,
    timeout_seconds: float = 60.0,
) -> DescriptionBundle:
    url = normalize_url(url)
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

    result, _usage = _responses_json(
        model=model,
        schema_name="company_description",
        json_schema=schema,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tools=[{"type": "web_search_preview"}],
        max_tool_calls=int(max_tool_calls),
        timeout_seconds=timeout_seconds,
    )
    if isinstance(result, dict):
        result["input_url"] = url
        if company_name_hint and not str(result.get("company_name") or "").strip():
            result["company_name"] = company_name_hint

    return DescriptionBundle(
        input_url=str(result.get("input_url") or url),
        company_name=str(result.get("company_name") or company_name_hint or ""),
        description=str(result.get("description") or "").strip(),
        highlights=[str(x) for x in (result.get("highlights") or []) if str(x).strip()],
    )


def generate_sales_pitch_for_company(
    *,
    company_url: str,
    company_name: str = "",
    description: Optional[str] = None,
    eval_positives: Optional[List[str]] = None,
    eval_concerns: Optional[List[str]] = None,
    eval_fit_attributes: Optional[Dict[str, Any]] = None,
    prompts_dir: Optional[Path] = None,
    golden_partners_csv: Optional[Path] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Portable pitch pipeline:
    - summarize (if needed)
    - extract attributes (from description)
    - load golden partners (CSV)
    - match partner
    - generate pitch (match or no-match template)
    """
    url = normalize_url(company_url)
    prompts_dir = prompts_dir or Path(__file__).resolve().parents[1] / "prompts"
    model = (model or os.environ.get("COMPANY_PITCH_MODEL") or "gpt-5.2-2025-12-11").strip()
    if not model:
        raise ValueError("Missing COMPANY_PITCH_MODEL (empty).")

    if not description or not str(description).strip():
        desc_bundle = summarize_company_from_url(
            url=url,
            company_name_hint=company_name,
            model=(os.environ.get("COMPANY_INTEL_MODEL") or model).strip() or model,
            max_tool_calls=int(os.environ.get("COMPANY_INTEL_MAX_TOOL_CALLS", "3") or 3),
            timeout_seconds=float(os.environ.get("COMPANY_INTEL_TIMEOUT_SECONDS", "60") or 60),
        )
        description = desc_bundle.description
    else:
        desc_bundle = DescriptionBundle(input_url=url, company_name=company_name, description=str(description).strip(), highlights=[])

    # 1) Extract attributes from description
    attr_prompt = _prompt_from_template(
        prompts_dir / "attribute_extractor_prompt.txt",
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
            "callable_account_types": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
            "callable_buyer_roles": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
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
            "callable_account_types",
            "callable_buyer_roles",
            "business_model",
            "company_size_indicators_text",
            "company_size_category_inferred",
            "innovation_level_indicators_text",
            "website_clarity_notes",
        ],
    }
    attrs, _u1 = _responses_json(
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

    # Merge structured fit attributes from an evaluator (if provided).
    if isinstance(attrs, dict) and isinstance(eval_fit_attributes, dict) and eval_fit_attributes:
        for k, v in eval_fit_attributes.items():
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            attrs[k] = v

    # 2) Load partners
    if golden_partners_csv is None:
        golden_partners_csv = Path(os.environ.get("GOLDEN_PARTNERS_CSV") or "kgs_001_ER47_20250626.csv").resolve()
    partners = load_golden_partners_from_csv(golden_partners_csv)
    partner_summaries = _render_partner_summaries(partners)

    # 3) Match partner
    eval_positives = eval_positives if isinstance(eval_positives, list) else []
    eval_concerns = eval_concerns if isinstance(eval_concerns, list) else []
    pm_prompt = _prompt_from_template(
        prompts_dir / "german_partner_matching_prompt.txt",
        {
            "{{TARGET_COMPANY_ATTRIBUTES_JSON_PLACEHOLDER}}": json.dumps(attrs, ensure_ascii=False, indent=2),
            "{{GOLDEN_PARTNER_SUMMARIES_PLACEHOLDER}}": partner_summaries,
            "{{EVALUATOR_POSITIVES_JSON_PLACEHOLDER}}": json.dumps(eval_positives, ensure_ascii=False, indent=2),
            "{{EVALUATOR_CONCERNS_JSON_PLACEHOLDER}}": json.dumps(eval_concerns, ensure_ascii=False, indent=2),
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
    partner_match, _u2 = _responses_json(
        model=model,
        schema_name="partner_match",
        json_schema=pm_schema,
        system_prompt="You match a target company to the most relevant golden partner.",
        user_prompt=pm_prompt,
        tools=None,
        timeout_seconds=float(os.environ.get("COMPANY_PITCH_TIMEOUT_SECONDS", "60") or 60),
    )

    matched_name = str((partner_match or {}).get("matched_partner_name") or "").strip()
    no_match = (not matched_name) or matched_name.lower() == "no suitable match found"

    matched_partner: Optional[Dict[str, Any]] = None
    if not no_match:
        # Case-insensitive lookup fallback
        by_lower = {str(p.get("name") or "").strip().lower(): p for p in partners}
        matched_partner = by_lower.get(matched_name.lower())
        if matched_partner is None:
            for p in partners:
                if str(p.get("name") or "").strip() == matched_name:
                    matched_partner = p
                    break

    # 4) Generate pitch
    sp_prompt_path = (
        prompts_dir / "german_sales_pitch_generation_prompt_no_match.txt"
        if no_match
        else prompts_dir / "german_sales_pitch_generation_prompt.txt"
    )
    prev_rationale = (partner_match or {}).get("match_rationale_features") or []
    if not isinstance(prev_rationale, list):
        prev_rationale = [str(prev_rationale)]
    sp_prompt = _prompt_from_template(
        sp_prompt_path,
        {
            "{{TARGET_COMPANY_ATTRIBUTES_JSON_PLACEHOLDER}}": json.dumps(attrs, ensure_ascii=False, indent=2),
            "{{MATCHED_GOLDEN_PARTNER_JSON_PLACEHOLDER}}": json.dumps(matched_partner or {}, ensure_ascii=False, indent=2),
            "{{PREVIOUS_MATCH_RATIONALE_PLACEHOLDER}}": json.dumps(prev_rationale, ensure_ascii=False, indent=2),
            "{{EVALUATOR_POSITIVES_JSON_PLACEHOLDER}}": json.dumps(eval_positives, ensure_ascii=False, indent=2),
            "{{EVALUATOR_CONCERNS_JSON_PLACEHOLDER}}": json.dumps(eval_concerns, ensure_ascii=False, indent=2),
        },
    )
    sp_schema: Dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "match_rationale_features": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
            "phone_sales_line": {"type": "string", "maxLength": 1500},
        },
        "required": ["match_rationale_features", "phone_sales_line"],
    }
    sales_pitch, _u3 = _responses_json(
        model=model,
        schema_name="sales_pitch",
        json_schema=sp_schema,
        system_prompt="You write short, spoken German phone sales lines for Manuav.",
        user_prompt=sp_prompt,
        tools=None,
        timeout_seconds=float(os.environ.get("COMPANY_PITCH_TIMEOUT_SECONDS", "60") or 60),
    )

    template = str((sales_pitch or {}).get("phone_sales_line") or "")
    filled = template
    avg = None
    if matched_partner and isinstance(matched_partner, dict):
        avg = matched_partner.get("avg_leads_per_day")
    if avg is not None:
        try:
            filled = filled.replace("{avg_leads_per_day}", str(int(avg)))
        except Exception:
            filled = filled.replace("{avg_leads_per_day}", str(avg))

    return {
        "inputs": {"company_url": url, "company_name": company_name},
        "description_bundle": {
            "input_url": desc_bundle.input_url,
            "company_name": desc_bundle.company_name,
            "description": desc_bundle.description,
            "highlights": desc_bundle.highlights,
        },
        "attributes": attrs,
        "partner_match": partner_match,
        "matched_partner": matched_partner,
        "sales_pitch": sales_pitch,
        "sales_pitch_template": template,
        "sales_pitch_filled": filled,
    }

