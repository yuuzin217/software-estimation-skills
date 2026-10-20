"""見積もり結果のMarkdown。数値は計算結果だけを使い、ここでは再計算しない。"""


def render_markdown(result: dict) -> str:
    lines: list[str] = ["# 見積もり結果", ""]
    lines.append(
        "この見積もりは保証値ではありません。PERT期待値は三点の加重平均であり、"
        "統計的な信頼区間でも、IPAやSIerが保証した値でもありません。"
    )
    lines.append("")
    if result["history_evaluation"]["fictional_records_present"]:
        lines.append("**注意:** 実績に架空データが含まれています。本番の見積根拠にしないでください。")
        lines.append("")
    for warning in result["warnings"]:
        lines.append(f"- 警告: {warning}")
    if result["warnings"]:
        lines.append("")

    meta = result["meta"]
    method = result["method"]
    lines.extend(
        [
            "## 基本情報",
            "",
            f"- 対象システム: {meta['system_name']}",
            f"- 見積もり目的: {meta['purpose']}",
            f"- 見積もり対象: {meta['input_summary']}",
            f"- 見積もり方式: 主方式 {method['primary']} / 補助 {method['auxiliary']}",
            f"- 方式を選んだ理由: {method['reason']}",
            f"- 見積もり実施日: {meta['estimation_date']}",
            f"- 工数単位: {_unit_label(meta['effort_unit'])}",
            f"- 1人日の時間: {meta['hours_per_person_day'] or '未指定（換算しない）'}",
            "",
            "### 入力情報",
            "",
            meta["input_summary"],
            "",
            "### 前提条件",
            "",
        ]
    )
    if result["assumptions"]:
        for item in result["assumptions"]:
            lines.append(f"- {item['id']}: {item['statement']}（影響: {item['impact']}）")
    else:
        lines.append("- 記録された前提条件はありません。")
    lines.append("")

    scope = result["scope"]
    lines.extend(["## スコープ", "", "### 対象機能", ""])
    _write_scope_items(lines, scope["functions"])
    lines.extend(["", "### 非機能要件", ""])
    _write_scope_items(lines, scope["non_functional"])
    lines.extend(["", "### 対象外", ""])
    _bullets(lines, scope["out_of_scope"], "記録された対象外はありません。")
    lines.extend(["", "### 未確定事項", ""])
    _bullets(lines, scope["unknowns"], "記録された未確定事項はありません。")
    if result["unestimated_items"]:
        lines.extend(["", "### 未算定の作業", ""])
        for item in result["unestimated_items"]:
            lines.append(f"- {item['id']} {item['name']}: {item['reason']}")
    lines.append("")

    lines.extend(["## WBS", ""])
    if result["wbs"]["cross_check_only"]:
        lines.append("このWBS合計は照合用です。計画工数には加算していません。")
        lines.append("")
    lines.extend(
        [
            "| WBS ID | 要件ID | 作業名 | 楽観 | 最頻 | 悲観 | 期待 | 算定根拠 |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for item in result["wbs"]["lines"]:
        if not item["estimable"]:
            lines.append(
                f"| {item['id']} | {_ids(item['requirement_ids'])} | {item['name']} | 未算定 | 未算定 | 未算定 | 未算定 | {item['blocked_reason']} |"
            )
            continue
        basis = item["basis"]
        lines.append(
            "| {id} | {reqs} | {name} | {optimistic} | {most_likely} | {pessimistic} | {expected} | {kind}: {explanation} |".format(
                id=item["id"],
                reqs=_ids(item["requirement_ids"]),
                name=item["name"],
                optimistic=item["optimistic"],
                most_likely=item["most_likely"],
                pessimistic=item["pessimistic"],
                expected=item["expected"],
                kind=basis["kind"],
                explanation=basis["explanation"].replace("|", "/"),
            )
        )
    lines.append("")
    if result["wbs"]["status"] == "calculated":
        lines.append(
            "WBS期待工数合計（丸め後）: "
            f"{result['wbs']['expected']} {_unit_label(result['wbs']['effort_unit'])}"
        )
        lines.append("根拠区分ごとの期待工数（丸め前）:")
        for kind, value in result["wbs"]["provenance_totals_exact"].items():
            lines.append(f"- {kind}: {value}")
    else:
        lines.append(result["wbs"]["reason"])
    lines.append("")

    summary = result["summary"]
    lines.extend(["## 工数サマリー", ""])
    if summary["status"] != "calculated":
        lines.append(f"計画工数は未算定です。{summary['reason']}")
    else:
        unit = _unit_label(summary["effort_unit"])
        lines.extend(
            [
                f"- 楽観工数合計: {summary['optimistic']} {unit}",
                f"- 最頻工数合計: {summary['most_likely']} {unit}",
                f"- 悲観工数合計: {summary['pessimistic']} {unit}",
                f"- 期待工数合計: {summary['expected']} {unit}",
                f"- 予備工数: {summary['contingency']} {unit}",
                f"- 計画工数: {summary['planned']} {unit}",
                f"- 主根拠: {summary['primary_basis']}",
                f"- 集計の説明: {summary['reason']}",
            ]
        )
        if summary["planned_differs_from_expected"]:
            lines.append(f"- 期待工数と計画工数が異なる理由: {summary['planned_difference_reason']}")
        else:
            lines.append("- 期待工数と計画工数は同じです。独立した予備工数はありません。")
        lines.append(f"- 丸め: {summary['rounding']['note']}（{summary['rounding']['mode']}、小数第2位）")
    lines.append("")

    lines.extend(["## 費用", ""])
    cost = result["cost"]
    if cost["status"] != "calculated":
        lines.append(f"費用は未算定です。{cost['reason']}")
    else:
        lines.extend(
            [
                f"- 通貨: {cost['currency']}",
                f"- 単価: {cost['rate']}（{cost['rate_unit']}、根拠 {cost['rate_basis']['kind']}）",
                f"- 単価の説明: {cost['rate_basis']['explanation']}",
                f"- 労務費: {cost['labor']}",
                f"- 経費合計: {cost['extra_total']}",
                f"- 合計: {cost['total']}",
                f"- 計算: {cost['reason']}",
                "- 労務費は、表示済みの計画工数へ掛けた値ではなく、丸める前の計画工数に単価を掛けてから小数第2位へ丸めています。",
            ]
        )
        if cost["conversion"]:
            lines.append(f"- 換算: {cost['conversion']}")
        for extra in cost["extra_costs"]:
            lines.append(
                f"- 経費 {extra['name']}: {extra['amount']}（{extra['basis_kind']}: {extra['explanation']}）"
            )
    lines.append("")

    lines.extend(["## 開発期間", ""])
    schedule = result["schedule"]
    lines.append(f"状態: {schedule['status']}")
    lines.append("")
    lines.append(schedule["reason"])
    if schedule["status"] != "not_calculated":
        lines.append("")
        lines.append(f"- 経過日数（暫定）: {schedule['elapsed_days']}")
        if schedule.get("lower_bound_days"):
            lines.append(f"- 稼働だけから見た下限: {schedule['lower_bound_days']}")
        lines.append(f"- 人数: {schedule['team_size']}")
        lines.append(f"- 稼働率: {schedule['utilization']}")
        if schedule.get("calendar_factor"):
            basis = schedule["calendar_factor_basis"]
            lines.append(
                f"- 暦日係数: {schedule['calendar_factor']}（{basis['kind']}: {basis['explanation']}）"
            )
    if schedule.get("limitations"):
        lines.extend(["", "期間の限界:"])
        for item in schedule["limitations"]:
            lines.append(f"- {item}")
    lines.append("")

    lines.extend(["## リスク", ""])
    if not result["risks"]:
        lines.append("記録されたリスクはありません。")
    else:
        for risk in result["risks"]:
            contained = "三点見積もりに含む" if risk["already_in_three_point"] else "三点見積もりに含まない"
            lines.extend(
                [
                    f"### {risk['id']}",
                    "",
                    f"- 内容: {risk['description']}",
                    f"- 発生条件: {risk['trigger']}",
                    f"- 影響範囲: {risk['impact_area']}",
                    f"- 見積もりへの影響: {risk['estimation_impact']}",
                    f"- 対応方針: {risk['response']}",
                    f"- 不確実性の扱い: {contained}",
                    "",
                ]
            )
    if result["contingency"]["reason"]:
        lines.append(
            "予備工数 "
            f"{result['contingency']['effort']} {_unit_label(result['contingency']['effort_unit'])}: "
            f"{result['contingency']['reason']}（対象リスク: {', '.join(result['contingency']['covered_risk_ids'])}）"
        )
        lines.append("")

    lines.extend(["## 根拠", "", "### 計算方法", ""])
    lines.append("PERT期待値 E = (O + 4M + P) / 6。期待値は保証値ではなく、悲観値は信頼区間の上限ではありません。")
    lines.append(result["summary"].get("rounding", {}).get("note", ""))
    lines.append(f"計算パッケージの版: {result['calculator_version']}")
    lines.append("")
    lines.append("方式選択の方針（外部標準ではない）:")
    policy = method["policy"]
    lines.append(f"- 類似度の下限: {policy['similarity_threshold']}")
    lines.append(f"- historical を主方式にする最少件数: {policy['minimum_records_for_historical_primary']}")
    lines.append(f"- 規模按分に必要な工程の重なり: {policy['minimum_category_jaccard_for_scaling']}")
    lines.append(f"- {policy['note']}")
    lines.extend(["", "### 実績データ", ""])
    history = result["history_evaluation"]
    lines.append(
        f"読込 {history['loaded_count']} 件、有効 {history['valid_count']} 件、"
        f"類似度が下限以上 {history['similar_count']} 件、規模按分に使用 {history['usable_for_scaling_count']} 件。"
    )
    historical = result["historical_estimate"]
    lines.append(f"実績見積もり: {historical['status']}。{historical.get('reason', '')}")
    if historical["status"] == "calculated":
        lines.append(
            "使用した実績: "
            + ", ".join(historical["used_record_ids"])
            + f"。期待工数 {historical['expected']} {_unit_label(historical['effort_unit'])}。"
        )
        lines.append(historical["applied_note"])
    for record in history["records"]:
        if record["exclusion_reasons"]:
            lines.append(f"- {record['project_id']} を不採用: {' / '.join(record['exclusion_reasons'])}")
    lines.extend(["", "### 外部ベンチマーク", ""])
    benchmark = result["benchmark"]
    lines.append(f"状態: {benchmark['status']}。{benchmark.get('reason', '')}")
    if benchmark.get("source"):
        source = benchmark["source"]
        lines.append(
            f"- 出典: {source['publisher']}『{source['title']}』 {source.get('table') or ''}、{source.get('period') or ''}"
        )
        lines.append(f"- URL: {source['url']}")
        if source.get("population"):
            lines.append(f"- 母集団: {source['population']}（N={source.get('n')}）")
    for limitation in benchmark.get("limitations") or []:
        lines.append(f"- 制約: {limitation}")
    for reason in benchmark.get("rejection_reasons") or []:
        lines.append(f"- 不採用理由: {reason}")
    if benchmark["status"] in {"cross_check_only", "reference_only_small_sample"}:
        lines.append(
            "照合の人時幅（計画工数ではない）: "
            f"楽観 {benchmark['optimistic']} / 最頻 {benchmark['most_likely']} / 悲観 {benchmark['pessimistic']}"
        )
    lines.extend(["", "### 暫定仮定", ""])
    wrote_assumption = False
    for item in result["wbs"]["lines"]:
        if item["estimable"] and item["basis"]["kind"] in {"ASSUMPTION", "AI_ESTIMATE"}:
            lines.append(f"- {item['id']} {item['basis']['kind']}: {item['basis']['explanation']}")
            wrote_assumption = True
    if not wrote_assumption:
        lines.append("- WBS上の暫定仮定はありません。")
    lines.append("")

    lines.extend(
        [
            "## 補足",
            "",
            "### 追加確認事項",
            "",
        ]
    )
    _bullets(lines, scope["unknowns"], "追加確認事項として記録された未確定事項はありません。")
    lines.extend(
        [
            "",
            "### 再見積もり条件",
            "",
            "- 未確定事項が解消したとき",
            "- 対象範囲、体制、単価、稼働率、工程範囲が変わったとき",
            "- 実績の測定単位や工程が今回と揃ったデータが追加されたとき",
            "- 外部ベンチマークの母集団に、本件が当てはまると確認できたとき",
            "",
            "### 見積もりの限界",
            "",
            "- 要件の分解と三点の幅は入力側の判断であり、計算式はその数値を検証・集計するだけです。",
            "- 過去実績が少ない段階の幅は、統計的な予測区間ではありません。",
            "- IPAの統計は、条件が一致した照合に限って参照します。現代のクラウド開発やAI支援開発へ無条件には使いません。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_scope_items(lines: list[str], items: list[dict]) -> None:
    if not items:
        lines.append("- 記録はありません。")
        return
    for item in items:
        lines.append(f"- {item['id']} {item['name']}: {item['description']}")


def _bullets(lines: list[str], items: list[str], empty: str) -> None:
    if not items:
        lines.append(f"- {empty}")
        return
    for item in items:
        lines.append(f"- {item}")


def _ids(values: list[str]) -> str:
    return ", ".join(values)


def _unit_label(unit: str | None) -> str:
    if unit == "person_day":
        return "人日"
    if unit == "person_hour":
        return "人時"
    return unit or ""
