import base64
import math
from pathlib import Path
from statistics import mean, stdev
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document

from database import get_db_connection, release_db_connection
from sql_guardrails import assert_sql_safe


MAX_FETCH_ROWS = 5000
REPORT_DIR = Path(__file__).resolve().parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)

ANALYSIS_RESULTS: dict[str, dict[str, Any]] = {}
DEFAULT_METHODS = ["基线特征", "结局发生率", "暴露分组OR", "分层描述"]


def get_analysis_result(session_id: str) -> dict[str, Any] | None:
    return ANALYSIS_RESULTS.get(session_id)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _safe_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _safe_sd(values: list[float]) -> float | None:
    return stdev(values) if len(values) > 1 else None


def _summarize_baseline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_fields = ["age_at_recruitment", "townsend_deprivation_index", "exposure_value"]
    summary: dict[str, Any] = {}
    for field in numeric_fields:
        values = [_as_float(row.get(field)) for row in rows]
        clean_values = [value for value in values if value is not None]
        summary[field] = {"n": len(clean_values), "mean": _safe_mean(clean_values), "sd": _safe_sd(clean_values)}
    return summary


def _summarize_outcome(rows: list[dict[str, Any]]) -> dict[str, Any]:
    outcome_positive = sum(1 for row in rows if int(row.get("outcome_status") or 0) == 1)
    return {
        "positive": outcome_positive,
        "negative": len(rows) - outcome_positive,
        "rate": outcome_positive / len(rows) if rows else None,
    }


def _compute_group_or(rows: list[dict[str, Any]]) -> dict[str, Any]:
    exposure_values = [_as_float(row.get("exposure_value")) for row in rows]
    clean_values = [value for value in exposure_values if value is not None]
    if len(clean_values) < 2:
        return {
            "method": "median split odds ratio",
            "available": False,
            "message": "暴露变量没有足够的数值，无法计算分组 OR。",
        }

    median_value = sorted(clean_values)[len(clean_values) // 2]
    high_case = high_control = low_case = low_control = 0
    for row in rows:
        exposure = _as_float(row.get("exposure_value"))
        if exposure is None:
            continue
        has_outcome = int(row.get("outcome_status") or 0) == 1
        if exposure >= median_value:
            if has_outcome:
                high_case += 1
            else:
                high_control += 1
        else:
            if has_outcome:
                low_case += 1
            else:
                low_control += 1

    odds_ratio = ((high_case + 0.5) * (low_control + 0.5)) / ((high_control + 0.5) * (low_case + 0.5))
    standard_error = math.sqrt(
        1 / (high_case + 0.5)
        + 1 / (high_control + 0.5)
        + 1 / (low_case + 0.5)
        + 1 / (low_control + 0.5)
    )
    log_or = math.log(odds_ratio)
    ci_low = math.exp(log_or - 1.96 * standard_error)
    ci_high = math.exp(log_or + 1.96 * standard_error)

    return {
        "method": "median split odds ratio",
        "available": True,
        "median_exposure": median_value,
        "odds_ratio": odds_ratio,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "counts": {
            "high_case": high_case,
            "high_control": high_control,
            "low_case": low_case,
            "low_control": low_control,
        },
    }


def _summarize_by_sex(rows: list[dict[str, Any]]) -> dict[str, Any]:
    strata: dict[str, dict[str, Any]] = {}
    for row in rows:
        sex = str(row.get("sex") or "Unknown")
        item = strata.setdefault(sex, {"n": 0, "outcome_positive": 0})
        item["n"] += 1
        if int(row.get("outcome_status") or 0) == 1:
            item["outcome_positive"] += 1

    for item in strata.values():
        item["outcome_rate"] = item["outcome_positive"] / item["n"] if item["n"] else None
    return strata


def _create_plot(session_id: str, stats: dict[str, Any]) -> dict[str, str]:
    plot_path = REPORT_DIR / f"{session_id}_plot.png"
    group_or = stats.get("group_or", {})
    baseline = stats.get("baseline", {})

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    if group_or.get("available"):
        odds_ratio = group_or["odds_ratio"]
        ci_low = group_or["ci_low"]
        ci_high = group_or["ci_high"]
        ax.errorbar(
            [odds_ratio],
            [0],
            xerr=[[odds_ratio - ci_low], [ci_high - odds_ratio]],
            fmt="o",
            color="#111827",
            ecolor="#2563eb",
            capsize=5,
        )
        ax.axvline(1, color="#9ca3af", linestyle="--", linewidth=1)
        ax.set_yticks([0])
        ax.set_yticklabels(["High vs low exposure"])
        ax.set_xlabel("Odds Ratio (95% CI)")
        ax.set_title("Exposure Group OR")
    else:
        labels = ["Age", "Townsend", "Exposure"]
        keys = ["age_at_recruitment", "townsend_deprivation_index", "exposure_value"]
        values = [baseline.get(key, {}).get("mean") or 0 for key in keys]
        ax.bar(labels, values, color=["#0f172a", "#2563eb", "#059669"])
        ax.set_title("Baseline Mean Values")
        ax.set_ylabel("Mean")

    fig.tight_layout()
    fig.savefig(plot_path, dpi=160)
    plt.close(fig)

    image_bytes = plot_path.read_bytes()
    image_base64 = base64.b64encode(image_bytes).decode("ascii")
    return {"plot_path": str(plot_path), "plot_html": f'<img alt="analysis chart" src="data:image/png;base64,{image_base64}" />'}


def _format_number(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _create_report(session_id: str, params: dict[str, Any], stats: dict[str, Any], plot_path: str, row_count: int) -> str:
    report_path = REPORT_DIR / f"medical_cohort_report_{session_id}.docx"
    methods = params.get("methods") or DEFAULT_METHODS

    document = Document()
    document.add_heading("Medical Cohort Analysis Report", level=1)
    document.add_paragraph(f"Session ID: {session_id}")
    document.add_paragraph(f"Analysis type: {params.get('analysis_type', 'NA')}")
    document.add_paragraph(f"Selected methods: {', '.join(methods)}")
    document.add_paragraph(f"Exposure: {params.get('exposure', 'NA')}")
    document.add_paragraph(f"Outcome ICD-10: {params.get('icd_code', params.get('outcome', 'NA'))}")
    document.add_paragraph(f"Fetched rows: {row_count}")

    if "基线特征" in methods and stats.get("baseline"):
        document.add_heading("Baseline Characteristics", level=2)
        table = document.add_table(rows=1, cols=4)
        header_cells = table.rows[0].cells
        header_cells[0].text = "Variable"
        header_cells[1].text = "N"
        header_cells[2].text = "Mean"
        header_cells[3].text = "SD"
        for variable, values in stats["baseline"].items():
            row_cells = table.add_row().cells
            row_cells[0].text = variable
            row_cells[1].text = _format_number(values.get("n"))
            row_cells[2].text = _format_number(values.get("mean"))
            row_cells[3].text = _format_number(values.get("sd"))

    if "结局发生率" in methods and stats.get("outcome"):
        outcome = stats["outcome"]
        document.add_heading("Outcome Incidence", level=2)
        document.add_paragraph(
            f"Outcome events: {outcome.get('positive', 0)} positive / {outcome.get('negative', 0)} negative "
            f"(rate={_format_number(outcome.get('rate'))})"
        )

    if "暴露分组OR" in methods and stats.get("group_or"):
        group_or = stats["group_or"]
        document.add_heading("Exposure Group OR", level=2)
        if group_or.get("available"):
            document.add_paragraph(
                f"OR: {_format_number(group_or.get('odds_ratio'))} "
                f"(95% CI {_format_number(group_or.get('ci_low'))} - {_format_number(group_or.get('ci_high'))})"
            )
        else:
            document.add_paragraph(group_or.get("message", "No OR result available."))

    if "分层描述" in methods and stats.get("sex_strata"):
        document.add_heading("Sex Stratified Summary", level=2)
        for sex, item in stats["sex_strata"].items():
            document.add_paragraph(
                f"{sex}: n={item.get('n')}, events={item.get('outcome_positive')}, rate={_format_number(item.get('outcome_rate'))}"
            )

    document.add_heading("Visualization", level=2)
    document.add_picture(plot_path)
    document.save(report_path)
    return str(report_path)


async def execute_cohort_sql(sql: str, limit: int = MAX_FETCH_ROWS) -> list[dict[str, Any]]:
    assert_sql_safe(sql)
    cleaned_sql = sql.strip().rstrip(";")
    limited_sql = f"SELECT * FROM ({cleaned_sql}) AS cohort_data LIMIT $1;"
    connection = await get_db_connection()
    try:
        rows = await connection.fetch(limited_sql, limit)
    finally:
        await release_db_connection(connection)
    return [dict(row) for row in rows]


async def preview_cohort(sql: str, limit: int = MAX_FETCH_ROWS) -> dict[str, Any]:
    rows = await execute_cohort_sql(sql, limit)
    baseline = _summarize_baseline(rows)
    outcome = _summarize_outcome(rows)
    return {
        "row_count": len(rows),
        "baseline": baseline,
        "outcome": outcome,
        "has_numeric_exposure": baseline.get("exposure_value", {}).get("n", 0) > 1,
        "sample_columns": list(rows[0].keys()) if rows else [],
    }


async def run_analysis(session_id: str, params: dict[str, Any], sql: str) -> dict[str, Any]:
    rows = await execute_cohort_sql(sql)
    methods = params.get("methods") or DEFAULT_METHODS
    stats: dict[str, Any] = {}

    if "基线特征" in methods:
        stats["baseline"] = _summarize_baseline(rows)
    else:
        stats["baseline"] = _summarize_baseline(rows)

    if "结局发生率" in methods:
        stats["outcome"] = _summarize_outcome(rows)

    if "暴露分组OR" in methods or params.get("analysis_type") == "孟德尔随机化":
        stats["group_or"] = _compute_group_or(rows)
        stats["mr"] = stats["group_or"]
    else:
        stats["group_or"] = {"available": False, "message": "未选择暴露分组 OR。"}
        stats["mr"] = stats["group_or"]

    if "分层描述" in methods:
        stats["sex_strata"] = _summarize_by_sex(rows)

    plot = _create_plot(session_id, stats)
    report_path = _create_report(session_id, params, stats, plot["plot_path"], len(rows))

    result = {
        "reply": f"分析完成：已执行 {', '.join(methods)}，统计结果和 Word 报告已生成。",
        "status": "success",
        "step": "analysis_complete",
        "count": len(rows),
        "stats": stats,
        "visualization_html": plot["plot_html"],
        "report_path": report_path,
        "report_url": f"/api/download/{session_id}",
    }
    ANALYSIS_RESULTS[session_id] = result
    return result


