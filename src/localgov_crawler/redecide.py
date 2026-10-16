"""保存済みの結果から、ハブの判定(hub.decide / hub.ascend)だけをやり直す(D-104)。
自治体のサイトには接続しない。判定のルールを変えたとき、取得済みの上位候補と親ページの確認結果(parent_check)から、
新しいルールでの結果を作る。取得を伴う変更(候補の集め方など)には使えない。"""
from __future__ import annotations

import copy
from dataclasses import fields

from . import hub

_CAND_FIELDS = {f.name for f in fields(hub.Candidate)}


def _candidate(d: dict) -> hub.Candidate:
    return hub.Candidate(**{k: v for k, v in d.items() if k in _CAND_FIELDS})


def redecide(result: dict, route: str, rules: str) -> dict:
    out = copy.deepcopy(result)
    out["run"] = {**out["run"], "route": route, "redecided_from": result["run"]["route"], "hub_rules": rules}
    if result["outcome"] not in ("hub_selected", "hub_multiple", "hub_not_found", "needs_headless") or not result.get("genre_entrypoints"):
        return out
    ge = out["genre_entrypoints"][0]
    cands = [_candidate(c) for c in ge["candidates"] if c.get("source") != "parent"]
    decision = hub.decide(cands)
    pc = ge.get("parent_check")
    ascended = hub.ascend(decision, pc)
    if pc is not None:
        for k in ("ascended", "decision_before"):
            pc.pop(k, None)
        if ascended is not decision:
            pc["ascended"] = True
            pc["decision_before"] = decision.outcome
    ge.update(decision=ascended.outcome, quality=ascended.quality,
              selected=ascended.selected.to_dict() if ascended.selected else None,
              candidates=[c.to_dict() for c in ascended.top])
    needs_headless = bool(out["site_profile"].get("rendering", {}).get("needs_headless"))
    outcome = ascended.outcome
    review = [r for r in out["needs_review"] if r not in ("hub_multiple", "hub_not_found", "needs_headless")]
    if needs_headless and outcome != "hub_selected":
        outcome = "needs_headless"
        review.append("needs_headless")
    if outcome in ("hub_multiple", "hub_not_found"):
        review.append(outcome)
    out["needs_review"] = review
    out["ai_needed"] = outcome in ("hub_multiple", "hub_not_found") and not needs_headless
    out["outcome"] = outcome
    return out
