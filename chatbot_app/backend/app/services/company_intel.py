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
    - env `GOLDEN_PARTNERS_PATH` (path to JSON, CSV, or XLSX), or
    - repo-root `kgs_001_ER47_20250626.csv` / `kgs_001_ER47_20250626.xlsx` (if present), or
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
        # Walk upwards looking for a repo marker or the partner file itself.
        markers = [
            "kgs_001_ER47_20250626.csv",
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

    EXCLUDED_PARTNER_NAMES = {"pnp media", "visitronic gmbh"}

    def _is_excluded_partner_name(name: str) -> bool:
        return str(name or "").strip().lower() in EXCLUDED_PARTNER_NAMES

    def _load_from_csv(path: Path) -> List[Dict[str, Any]]:
        import csv

        def _truthy(v: Any) -> bool:
            s = str(v or "").strip().lower()
            return s in {"1", "true", "yes", "y", "t"}

        def _cell_str(v: Any) -> str:
            return str(v or "").strip()

        def _cell_bool(v: Any) -> Optional[bool]:
            s = _cell_str(v).strip().lower()
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
            s = _cell_str(v)
            if not s:
                return None
            try:
                return int(float(s))
            except Exception:
                return None

        try:
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except Exception as e:
            raise ValueError(f"Failed to read golden partners CSV: {path} ({type(e).__name__}: {e})")

        partners: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue

            # Optional filter: only keep successful partners
            if "Is Successful Partner" in row and not _truthy(row.get("Is Successful Partner")):
                continue

            name = _cell_str(row.get("Company Name"))
            if not name:
                continue
            if _is_excluded_partner_name(name):
                continue

            industry = _cell_str(row.get("Industry"))
            products = _cell_str(row.get("Products/Services Offered"))
            usp = _cell_str(row.get("USP (Unique Selling Proposition) / Key Selling Points"))
            segments = _cell_str(row.get("Customer Target Segments"))
            business_model = _cell_str(row.get("Business Model"))
            company_size_indicators_text = _cell_str(row.get("Company Size Indicators"))
            innovation_level_indicators_text = _cell_str(row.get("Innovation Level Indicators"))
            geo = _cell_str(row.get("Geographic Reach"))
            targets_specific_industry_type_raw = _cell_str(row.get("Targets_Specific_Industry_Type"))

            avg = _cell_int(row.get("Avg Leads Per Day")) or 0
            rank = _cell_int(row.get("Rank (1-47)")) or _cell_int(row.get("Rank")) or 0

            target_segments = _split_listish(segments)
            targets_specific_industry_type = _split_listish(targets_specific_industry_type_raw)

            is_startup = _cell_bool(row.get("Is_Startup"))
            is_ai_software = _cell_bool(row.get("Is_AI_Software"))
            is_innovative_product = _cell_bool(row.get("Is_Innovative_Product"))
            is_disruptive_product = _cell_bool(row.get("Is_Disruptive_Product"))
            is_vc_funded = _cell_bool(row.get("Is_VC_Funded"))
            is_saas_software = _cell_bool(row.get("Is_SaaS_Software"))
            is_complex_solution = _cell_bool(row.get("Is_Complex_Solution"))
            is_investment_product = _cell_bool(row.get("Is_Investment_Product"))

            partner_description_parts = []
            if industry:
                partner_description_parts.append(f"Industry: {industry}")
            if products:
                partner_description_parts.append(f"Products/Services: {products}")
            if usp:
                partner_description_parts.append(f"USP: {usp}")
            if business_model:
                partner_description_parts.append(f"Business model: {business_model}")
            if company_size_indicators_text:
                partner_description_parts.append(f"Company size signals: {company_size_indicators_text}")
            if innovation_level_indicators_text:
                partner_description_parts.append(f"Innovation signals: {innovation_level_indicators_text}")
            if geo:
                partner_description_parts.append(f"Geo: {geo}")

            partners.append(
                {
                    "name": name,
                    "rank": int(rank) if rank else None,
                    "avg_leads_per_day": int(avg) if avg else None,
                    "industry": industry or None,
                    "target_segments": target_segments,
                    "products_services_offered": products or None,
                    "usp_key_selling_points": usp or None,
                    "business_model": business_model or None,
                    "company_size_indicators_text": company_size_indicators_text or None,
                    "innovation_level_indicators_text": innovation_level_indicators_text or None,
                    "targets_specific_industry_type": targets_specific_industry_type,
                    "is_startup": is_startup,
                    "is_ai_software": is_ai_software,
                    "is_innovative_product": is_innovative_product,
                    "is_disruptive_product": is_disruptive_product,
                    "is_vc_funded": is_vc_funded,
                    "is_saas_software": is_saas_software,
                    "is_complex_solution": is_complex_solution,
                    "is_investment_product": is_investment_product,
                    "partner_description": " | ".join(partner_description_parts)[:2000] if partner_description_parts else None,
                    "case_study_summary": None,
                }
            )

        # Sort by rank if present.
        partners.sort(key=lambda p: (p.get("rank") is None, p.get("rank") or 10**9, p.get("name") or ""))
        return partners

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
            if _is_excluded_partner_name(name):
                continue

            industry = _cell_str(row.get("Industry"))
            products = _cell_str(row.get("Products/Services Offered"))
            usp = _cell_str(row.get("USP (Unique Selling Proposition) / Key Selling Points"))
            segments = _cell_str(row.get("Customer Target Segments"))
            business_model = _cell_str(row.get("Business Model"))
            company_size_indicators_text = _cell_str(row.get("Company Size Indicators"))
            innovation_level_indicators_text = _cell_str(row.get("Innovation Level Indicators"))
            geo = _cell_str(row.get("Geographic Reach"))
            targets_specific_industry_type_raw = _cell_str(row.get("Targets_Specific_Industry_Type"))

            avg = _cell_int(row.get("Avg Leads Per Day")) or 0
            rank = _cell_int(row.get("Rank (1-47)")) or _cell_int(row.get("Rank")) or 0

            target_segments = _split_listish(segments)
            targets_specific_industry_type = _split_listish(targets_specific_industry_type_raw)

            def _cell_bool(v: Any) -> Optional[bool]:
                s = _cell_str(v).strip().lower()
                if not s:
                    return None
                if s in {"not found", "unknown", "n/a", "na", "none", "-"}:
                    return None
                if s in {"0", "false", "no", "n"}:
                    return False
                if s in {"1", "true", "yes", "y", "t"}:
                    return True
                return None

            is_startup = _cell_bool(row.get("Is_Startup"))
            is_ai_software = _cell_bool(row.get("Is_AI_Software"))
            is_innovative_product = _cell_bool(row.get("Is_Innovative_Product"))
            is_disruptive_product = _cell_bool(row.get("Is_Disruptive_Product"))
            is_vc_funded = _cell_bool(row.get("Is_VC_Funded"))
            is_saas_software = _cell_bool(row.get("Is_SaaS_Software"))
            is_complex_solution = _cell_bool(row.get("Is_Complex_Solution"))
            is_investment_product = _cell_bool(row.get("Is_Investment_Product"))

            partner_description_parts = []
            if industry:
                partner_description_parts.append(f"Industry: {industry}")
            if products:
                partner_description_parts.append(f"Products/Services: {products}")
            if usp:
                partner_description_parts.append(f"USP: {usp}")
            if business_model:
                partner_description_parts.append(f"Business model: {business_model}")
            if company_size_indicators_text:
                partner_description_parts.append(f"Company size signals: {company_size_indicators_text}")
            if innovation_level_indicators_text:
                partner_description_parts.append(f"Innovation signals: {innovation_level_indicators_text}")
            if geo:
                partner_description_parts.append(f"Geo: {geo}")

            partners.append(
                {
                    "name": name,
                    "rank": int(rank) if rank else None,
                    "avg_leads_per_day": int(avg) if avg else None,
                    "industry": industry or None,
                    "target_segments": target_segments,
                    "products_services_offered": products or None,
                    "usp_key_selling_points": usp or None,
                    "business_model": business_model or None,
                    "company_size_indicators_text": company_size_indicators_text or None,
                    "innovation_level_indicators_text": innovation_level_indicators_text or None,
                    "targets_specific_industry_type": targets_specific_industry_type,
                    "is_startup": is_startup,
                    "is_ai_software": is_ai_software,
                    "is_innovative_product": is_innovative_product,
                    "is_disruptive_product": is_disruptive_product,
                    "is_vc_funded": is_vc_funded,
                    "is_saas_software": is_saas_software,
                    "is_complex_solution": is_complex_solution,
                    "is_investment_product": is_investment_product,
                    "partner_description": " | ".join(partner_description_parts)[:2000] if partner_description_parts else None,
                    "case_study_summary": None,
                }
            )

        # Sort by rank if present.
        partners.sort(key=lambda p: (p.get("rank") is None, p.get("rank") or 10**9, p.get("name") or ""))
        return partners

    env_path = (os.environ.get("GOLDEN_PARTNERS_PATH") or "").strip()
    if env_path:
        path = _resolve_path(Path(env_path))
    else:
        # Repo-root partner file (provided by user) – auto-detect if present (prefer CSV).
        root = _repo_root()
        path = root / "kgs_001_ER47_20250626.csv"
        if not path.exists():
            path = root / "kgs_001_ER47_20250626.xlsx"
        if not path.exists():
            path = DATA_DIR / "golden_partners.json"

    lower = str(path).lower()
    if lower.endswith(".csv"):
        return _load_from_csv(path)
    if lower.endswith((".xlsx", ".xls")):
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
    model = (model or os.environ.get("COMPANY_INTEL_MODEL") or "gpt-5.2-2025-12-11").strip()
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
        max_tool_calls=int(os.environ.get("COMPANY_INTEL_MAX_TOOL_CALLS", "5") or 5),
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
    model = (model or os.environ.get("COMPANY_EVAL_MODEL") or "gpt-5.2-2025-12-11").strip()
    if not model:
        raise ValueError("Missing COMPANY_EVAL_MODEL (empty).")

    # Run rubric-based evaluator (OpenAI responses + web search tool).
    res, usage, billed_q, citations = evaluate_company_with_usage_and_web_search_artifacts(
        url,
        model,
        max_tool_calls=int(os.environ.get("COMPANY_EVAL_MAX_TOOL_CALLS", "15") or 15),
        # Default ON to reduce domain/lookalike misattribution (can still be disabled explicitly).
        second_query_on_uncertainty=(
            os.environ.get("COMPANY_EVAL_SECOND_QUERY", "1").strip().lower() in {"1", "true", "yes", "y"}
        ),
    )

    score = float(res.get("manuav_fit_score", 0))
    company_name = str(res.get("company_name") or "").strip()
    confidence = str(res.get("confidence") or "").strip().lower() or "low"
    reasoning = str(res.get("reasoning") or "").strip()
    positives = res.get("positives") if isinstance(res, dict) else None
    concerns = res.get("concerns") if isinstance(res, dict) else None

    if not isinstance(positives, list):
        positives = []
    if not isinstance(concerns, list):
        concerns = []

    fit_attributes = {}
    if isinstance(res, dict):
        fit_attributes = {
            "company_size_indicators_text": res.get("company_size_indicators_text"),
            "innovation_level_indicators_text": res.get("innovation_level_indicators_text"),
            "targets_specific_industry_type": res.get("targets_specific_industry_type") or [],
            "is_startup": res.get("is_startup"),
            "is_ai_software": res.get("is_ai_software"),
            "is_innovative_product": res.get("is_innovative_product"),
            "is_disruptive_product": res.get("is_disruptive_product"),
            "is_vc_funded": res.get("is_vc_funded"),
            "is_saas_software": res.get("is_saas_software"),
            "is_complex_solution": res.get("is_complex_solution"),
            "is_investment_product": res.get("is_investment_product"),
        }

    out: Dict[str, Any] = {
        "input_url": url,
        "company_name": company_name,
        "score": score,
        "confidence": confidence,
        "reasoning": reasoning,
        "positives": [str(x) for x in positives if str(x).strip()],
        "concerns": [str(x) for x in concerns if str(x).strip()],
        "fit_attributes": fit_attributes,
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
    # Keep this intentionally compact so we can include ALL partners without
    # blowing up prompt size. For matching, "who we can call" (target_segments)
    # matters most; product/model/flags are supporting context only.
    compact = []
    for p in partners:
        def _trunc(v: Any, n: int) -> Any:
            if v is None:
                return None
            if isinstance(v, str):
                s = v.strip()
                return (s[:n] + "…") if len(s) > n else s
            return v

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


def _prefilter_partners_for_matching(
    partners: List[Dict[str, Any]],
    *,
    target_attrs: Dict[str, Any],
    limit: int = 12,
) -> List[Dict[str, Any]]:
    """
    Reduce prompt size and avoid shallow matches by prefiltering partners to a
    small candidate set based on structured similarity signals.

    - Uses `targets_specific_industry_type` overlap when available.
    - Uses a few boolean flags (SaaS/AI/complex/startup) as weak tie-breakers.
    - Falls back to rank ordering when evidence is sparse.
    """
    limit = max(5, min(int(limit or 12), 25))
    if not partners:
        return []
    if not isinstance(target_attrs, dict):
        return sorted(
            partners,
            key=lambda p: (
                (p.get("rank") is None) or (int(p.get("rank") or 0) <= 0),
                int(p.get("rank") or 10**9) if int(p.get("rank") or 0) > 0 else 10**9,
                str(p.get("name") or ""),
            ),
        )[:limit]

    def _norm_list(v: Any) -> List[str]:
        if not isinstance(v, list):
            return []
        out = []
        for x in v:
            s = str(x or "").strip().lower()
            if s:
                out.append(s)
        return out

    def _norm_bool(v: Any) -> Optional[bool]:
        if isinstance(v, bool):
            return v
        return None

    target_types = set(_norm_list(target_attrs.get("targets_specific_industry_type")))
    t_is_saas = _norm_bool(target_attrs.get("is_saas_software"))
    t_is_ai = _norm_bool(target_attrs.get("is_ai_software"))
    t_is_complex = _norm_bool(target_attrs.get("is_complex_solution"))
    t_is_startup = _norm_bool(target_attrs.get("is_startup"))

    import re

    _word_re = re.compile(r"[a-z0-9]+", re.IGNORECASE)
    _stop = {
        "and",
        "the",
        "for",
        "with",
        "from",
        "into",
        "over",
        "under",
        "other",
        "general",
        "services",
        "service",
        "solutions",
        "solution",
        "software",
        "platform",
        "products",
        "product",
        "sector",
        "industry",
        "industrie",
        "und",
        "der",
        "die",
        "das",
        "mit",
        "für",
        "von",
        "im",
        "in",
        "am",
        "an",
        "auf",
        "bei",
        "zum",
        "zur",
        "b2b",
        "b2c",
    }

    def _label_words(labels: Any) -> set[str]:
        if not isinstance(labels, list):
            return set()
        out: set[str] = set()
        for lbl in labels:
            s = str(lbl or "").strip().lower()
            for w in _word_re.findall(s):
                if len(w) < 3:
                    continue
                if w in _stop:
                    continue
                out.add(w)
        return out

    target_type_words = _label_words(list(target_types))
    target_industry_words = set(_word_re.findall(str(target_attrs.get("industry") or "").lower())) - _stop

    def _overlap_score(p: Dict[str, Any]) -> float:
        p_types = set(_norm_list(p.get("targets_specific_industry_type")))
        # Exact label overlap (best signal when taxonomies align).
        if target_types and p_types:
            inter = len(target_types.intersection(p_types))
            union = len(target_types.union(p_types)) or 1
            exact = (inter / union) * 10.0
        else:
            exact = 0.0

        # Word-level overlap across labels (helps when label sets differ but share keywords).
        p_type_words = _label_words(list(p_types))
        if target_type_words and p_type_words:
            winter = len(target_type_words.intersection(p_type_words))
            wunion = len(target_type_words.union(p_type_words)) or 1
            words = (winter / wunion) * 6.0
        else:
            words = 0.0

        # Tiny industry-word overlap as last resort.
        p_industry_words = set(_word_re.findall(str(p.get("industry") or "").lower())) - _stop
        if target_industry_words and p_industry_words:
            iinter = len(target_industry_words.intersection(p_industry_words))
            iunion = len(target_industry_words.union(p_industry_words)) or 1
            ind = (iinter / iunion) * 2.0
        else:
            ind = 0.0

        base = exact + words + ind

        # Gentle tie-breakers on high-level motion/complexity flags
        bonus = 0.0
        for key, tv in [
            ("is_saas_software", t_is_saas),
            ("is_ai_software", t_is_ai),
            ("is_complex_solution", t_is_complex),
            ("is_startup", t_is_startup),
        ]:
            pv = _norm_bool(p.get(key))
            if tv is None or pv is None:
                continue
            if tv == pv:
                bonus += 0.75
            else:
                bonus -= 0.25

        # Very mild preference for higher-ranked partners when all else equal.
        try:
            r = p.get("rank")
            rank_penalty = 0.0 if r is None else (min(50.0, float(r)) / 200.0)
        except Exception:
            rank_penalty = 0.0

        return base + bonus - rank_penalty

    scored = [(p, _overlap_score(p)) for p in partners]
    # If everything is 0-ish (no types + no flags), just take the top by rank.
    if max((s for _, s in scored), default=0.0) <= 0.01:
        return sorted(
            partners,
            key=lambda p: (
                (p.get("rank") is None) or (int(p.get("rank") or 0) <= 0),
                int(p.get("rank") or 10**9) if int(p.get("rank") or 0) > 0 else 10**9,
                str(p.get("name") or ""),
            ),
        )[:limit]

    scored.sort(
        key=lambda t: (
            -(t[1] or 0.0),
            ((t[0].get("rank") is None) or (int(t[0].get("rank") or 0) <= 0), int(t[0].get("rank") or 10**9)),
            str(t[0].get("name") or ""),
        )
    )
    return [p for p, _s in scored[:limit]]


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
    eval_positives: Optional[List[str]] = None,
    eval_concerns: Optional[List[str]] = None,
    eval_fit_attributes: Optional[Dict[str, Any]] = None,
    pitch_template: Optional[str] = None,
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
    model = (model or os.environ.get("COMPANY_PITCH_MODEL") or "gpt-5.2-2025-12-11").strip()
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

    # Merge structured fit attributes from the evaluator (if provided).
    if isinstance(attrs, dict) and isinstance(eval_fit_attributes, dict) and eval_fit_attributes:
        for k, v in eval_fit_attributes.items():
            # Prefer evaluator values when present; keep extractor output otherwise.
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            attrs[k] = v

    # 2) Match partner
    partners = load_golden_partners()
    # IMPORTANT: We intentionally include ALL partners for matching, but keep
    # their summaries compact so the model can compare globally.
    partner_summaries = _render_partner_summaries(partners)
    eval_positives = eval_positives if isinstance(eval_positives, list) else []
    eval_concerns = eval_concerns if isinstance(eval_concerns, list) else []
    pm_prompt = _prompt_from_template(
        PROMPTS_DIR / "german_partner_matching_prompt.txt",
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
        # Prefer exact match, but allow case-insensitive fallback to reduce "no match" from minor formatting.
        by_exact: Dict[str, Dict[str, Any]] = {str(p.get("name") or "").strip(): p for p in partners}
        matched_partner = by_exact.get(matched_name)
        if matched_partner is None:
            lookup = {str(k).strip().lower(): v for k, v in by_exact.items() if str(k).strip()}
            matched_partner = lookup.get(matched_name.strip().lower())

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
    pt = (pitch_template or "bullets").strip().lower()
    if pt not in {"bullets", "classic"}:
        pt = "bullets"

    if no_match:
        sp_template = PROMPTS_DIR / "german_sales_pitch_generation_prompt_no_match.txt"
    else:
        sp_template = (
            PROMPTS_DIR / "german_sales_pitch_generation_prompt_classic.txt"
            if pt == "classic"
            else PROMPTS_DIR / "german_sales_pitch_generation_prompt.txt"
        )
    sp_replacements = {
        "{{TARGET_COMPANY_ATTRIBUTES_JSON_PLACEHOLDER}}": json.dumps(attrs, ensure_ascii=False, indent=2),
        "{{EVALUATOR_POSITIVES_JSON_PLACEHOLDER}}": json.dumps(eval_positives, ensure_ascii=False, indent=2),
        "{{EVALUATOR_CONCERNS_JSON_PLACEHOLDER}}": json.dumps(eval_concerns, ensure_ascii=False, indent=2),
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

