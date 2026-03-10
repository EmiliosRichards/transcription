## Porting checklist (v1 → v2)

### Evaluator repo
- [ ] Replace `manuav_eval/schema.py` with the v2 version (adds `positives`, `concerns`, structured flags).
- [ ] Replace `manuav_eval/evaluator.py` with the v2 version.
  - Confirm there is **no** “visited Manuav website” text.
  - Confirm second-query instructions are still **disambiguation-only** (same semantics as v1).
- [ ] Replace `rubrics/manuav_rubric_v4_en.md` with the v2 version.
  - Confirm mixed B2C/B2B is treated as **potential** if any credible B2B wedge exists.
- [ ] Ensure the service returns `result` as a dict (so additive keys don’t break clients).

### Sales pitch repo / module (only if you want these updates)
- [ ] Vendor updated prompt templates from `sales_pitch/prompts/`.
- [ ] If you want a portable implementation: vendor `sales_pitch/python/pitch_engine.py`.
- [ ] Ensure golden partners CSV path is wired (`GOLDEN_PARTNERS_CSV`).
- [ ] If your pitch system already exists, just port the **prompt changes** and the **new attribute fields** first (lowest risk).

### Pipeline safety checks
- [ ] UI still displays score/confidence/reasoning even if it ignores new keys.
- [ ] Pitch generation still works if evaluator `positives/concerns` are missing (pass empty lists).
- [ ] No-match path still works (when partner matcher returns `"No suitable match found"`).

