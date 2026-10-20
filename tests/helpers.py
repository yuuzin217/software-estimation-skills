"""テスト用の最小依頼。"""


def minimal_request() -> dict:
    return {
        "schema_version": "1.0",
        "meta": {
            "system_name": "テストシステム",
            "purpose": "単体テスト",
            "estimation_date": "2026-10-20",
            "input_summary": "テスト用の最小入力",
            "effort_unit": "person_day",
        },
        "scope": {
            "functions": [{"id": "F-001", "name": "機能", "description": "テスト機能"}],
            "non_functional": [],
            "out_of_scope": [],
            "unknowns": [],
        },
        "assumptions": [{"id": "A-001", "statement": "テストの前提です", "impact": "なし"}],
        "risks": [],
        "wbs": [wbs_item()],
    }


def wbs_item(**overrides) -> dict:
    item = {
        "id": "WBS-001",
        "requirement_ids": ["F-001"],
        "name": "実装",
        "description": "機能を実装する",
        "phase": "implementation",
        "estimable": True,
        "optimistic": "1",
        "most_likely": "2",
        "pessimistic": "3",
        "uncertainty": "medium",
        "provisional": True,
        "basis": {"kind": "AI_ESTIMATE", "explanation": "テスト用の暫定見積もりである"},
    }
    item.update(overrides)
    return item


def history_record(**overrides) -> dict:
    record = {
        "project_id": "P-001",
        "project_type": "new_web_app",
        "project_scope": "new",
        "technology_stack": ["python", "fastapi"],
        "work_categories": ["implementation", "test"],
        "estimated_effort": "10",
        "actual_effort": "12",
        "effort_unit": "person_day",
        "fictional": True,
        "size": {"kind": "feature_count", "value": "4"},
        "notes": "架空データ",
    }
    record.update(overrides)
    return record


def comparison_profile() -> dict:
    return {
        "project_type": "new_web_app",
        "project_scope": "new",
        "technology_stack": ["python", "fastapi"],
        "work_categories": ["implementation", "test"],
    }
