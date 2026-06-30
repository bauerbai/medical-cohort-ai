from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowStage:
    id: str
    name: str
    purpose: str
    agent_role: str
    human_gate: str
    outputs: list[str]
    tools: list[str]


@dataclass(frozen=True)
class ResearchWorkflowPlan:
    source: str
    fit: str
    integration_point: str
    stages: list[WorkflowStage]
    data_governance: list[str]
    next_actions: list[str]

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


RWE_ACADEMIC_WORKFLOW = ResearchWorkflowPlan(
    source="Imbad0202/academic-research-skills",
    fit=(
        "Use it as a research workflow orchestrator above the existing RWE agent. "
        "The statistics engine remains responsible for computation; the academic "
        "workflow layer decides when to ask the PI, when to search or validate "
        "evidence, when to run analyses, and when to generate manuscript/report artifacts."
    ),
    integration_point="agent layer: AcademicWorkflow -> RWE Agent -> Cohort Builder -> Stats Engine -> Report Generator",
    stages=[
        WorkflowStage(
            id="stage_0_intake",
            name="选题与研究问题澄清",
            purpose="把 PI 的自然语言想法转成 PICO/PECO、目标估计量、时间零点和可执行研究设计。",
            agent_role="research_architect",
            human_gate="PI 确认研究问题、暴露、结局、目标人群和主要假设。",
            outputs=["Research Question Brief", "Methodology Blueprint", "Bias Pre-mortem"],
            tools=["metadata_scanner.scan_schema", "research_catalog", "agent.system_prompt"],
        ),
        WorkflowStage(
            id="stage_1_evidence",
            name="证据与文献上下文",
            purpose="整理既有证据、常见混杂因素、临床合理性和待验证假设。",
            agent_role="literature_strategist",
            human_gate="PI 审核纳入/排除标准、关键文献和临床变量清单。",
            outputs=["Literature Matrix", "Covariate Rationale", "Evidence Gap Summary"],
            tools=["future: literature_connector", "future: citation_verifier"],
        ),
        WorkflowStage(
            id="stage_2_cohort",
            name="队列构建与数据预检",
            purpose="生成 SQL、抽样预检、检查结局事件数、缺失率和数据可行性。",
            agent_role="cohort_engineer",
            human_gate="PI 确认队列定义、排除标准、随访窗口和是否继续分析。",
            outputs=["Executable Cohort SQL", "Data Feasibility Report", "Missingness Summary"],
            tools=["cohort_builder.build_cohort_sql", "stats_engine.preview_cohort", "asyncpg"],
        ),
        WorkflowStage(
            id="stage_3_analysis",
            name="统计分析执行",
            purpose="根据研究设计调用 Table 1、回归、生存分析、PSM/IPTW、机器学习等统计模块。",
            agent_role="biostatistician",
            human_gate="PI 选择主分析、敏感性分析和亚组分析组合。",
            outputs=["Statistical Results", "Plots JSON/HTML", "Sensitivity Analysis Notes"],
            tools=["engine.AnalysisRegistry", "agent.tools", "stats_engine.run_analysis"],
        ),
        WorkflowStage(
            id="stage_4_review",
            name="方法学复核与完整性检查",
            purpose="检查偏倚、混杂、时间零点、PH 假设、匹配平衡、引用和结论是否被数据支持。",
            agent_role="methods_reviewer",
            human_gate="PI 对高风险问题进行确认、修订或记录理由。",
            outputs=["Integrity Checklist", "Reviewer Critique", "Revision Plan"],
            tools=["engine.survival.CoxRegressionAnalysis", "engine.causal_inference.PropensityScoreMatching"],
        ),
        WorkflowStage(
            id="stage_5_report",
            name="报告与论文草稿",
            purpose="把分析结果转成 Word 报告、摘要、方法段、结果段和图表说明。",
            agent_role="scientific_writer",
            human_gate="PI 审核解释、临床意义、限制和投稿目标。",
            outputs=["DOCX Report", "Manuscript Draft Sections", "Figure Legends"],
            tools=["stats_engine.generate_docx_report", "future: manuscript_writer"],
        ),
    ],
    data_governance=[
        "不把原始患者级数据发送给外部 LLM；LLM 只接收聚合统计、字段字典和经过脱敏的摘要。",
        "数据库密码继续只从 .env 加载，不进入 prompt、日志或报告。",
        "每个阶段保留 session_id、SQL、参数、统计结果和 PI 确认记录，方便复现。",
        "文献证据需要引用验证；不能让模型凭空生成 DOI、PMID 或指南出处。",
    ],
    next_actions=[
        "把 /api/agent 增加科研工作流触发语：科研流程、论文、文献、academic-research-skills。",
        "新增 /api/academic-workflow，让前端右侧展示阶段图和人类确认门。",
        "后续接入文献检索连接器后，把 stage_1_evidence 从占位升级为真实检索和引用核验。",
    ],
)


def build_academic_workflow_plan() -> dict[str, Any]:
    return RWE_ACADEMIC_WORKFLOW.model_dump()


def format_workflow_for_pi() -> str:
    lines = [
        "可以加，而且非常适合加在 Agent 层，作为“科研项目经理/流程编排器”。",
        "它不替代统计引擎，而是把选题、证据、队列构建、统计分析、方法学复核和报告写作串起来。",
        "",
        "建议工作流：",
    ]
    for index, stage in enumerate(RWE_ACADEMIC_WORKFLOW.stages, start=1):
        lines.append(f"{index}. {stage.name}：{stage.purpose}")
        lines.append(f"   PI 确认点：{stage.human_gate}")
    lines.extend(
        [
            "",
            "我建议先落地两个入口：",
            "- 你问“科研流程怎么设计”时，返回完整阶段图。",
            "- 进入真实分析前，强制经过研究问题、偏倚检查、队列定义和分析方案确认。",
        ]
    )
    return "\n".join(lines)
