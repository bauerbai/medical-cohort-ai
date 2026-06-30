"use client";

import { FormEvent, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type ChatRole = "user" | "assistant";

type Option = {
  value: string;
  label: string;
  description?: string;
  available?: boolean;
};

type MetadataTable = {
  row_count: number;
  columns: { name: string; data_type: string }[];
};

type SchemaMetadata = {
  schema?: string;
  table_count?: number;
  total_rows?: number;
  patient_count?: number;
  tables?: Record<string, MetadataTable>;
  icd10_top_codes?: { code: string; description: string; count: number }[];
};

type SemanticOverview = {
  total_patients?: number;
  sex_distribution?: { label: string; n: number }[];
  top_diseases?: { label: string; patient_count: number }[];
  top_drugs?: { label: string; patient_count: number }[];
  top_first_occurrences?: { label: string; event_count: number }[];
};

type DiseaseCount = {
  disease?: string;
  total_patients?: number;
  patient_count?: number;
  record_count?: number;
  prevalence?: number | null;
};

type DiseaseIntersection = {
  diseases?: { label: string; code?: string | null }[];
  count?: number;
  total_patients?: number;
  prevalence?: number | null;
  sex_distribution?: { label: string; n: number; percent?: number }[];
  download_url?: string;
};

type DiseaseDrugOverlap = {
  disease?: string;
  drug?: string;
  disease_patients?: number;
  drug_users_in_disease?: number;
  drug_non_users_in_disease?: number;
  drug_use_rate_in_disease?: number | null;
  top_matching_drugs?: { label: string; patient_count: number; record_count: number }[];
  mechanisms?: { mechanism: string; patient_count: number; patient_percent?: number; record_count: number }[];
  translated_drugs?: { mechanism: string; drug_name_cn: string; drug_label: string; patient_count: number; record_count: number }[];
  per_drug_patient_count_sum?: number;
  counting_note?: string;
  download_url?: string;
};

type DrugMechanismSummary = {
  disease?: string;
  drug?: string;
  drug_users_in_disease?: number;
  mechanisms?: {
    mechanism: string;
    patient_count_sum: number;
    record_count_sum: number;
    drugs: { drug_name_cn: string; drug_label: string; patient_count: number; record_count: number }[];
  }[];
  translated_drugs?: { mechanism: string; drug_name_cn: string; drug_label: string; patient_count: number; record_count: number }[];
  counting_note?: string;
  download_url?: string;
};

type SampleDistribution = {
  total_patients?: number;
  sex_distribution?: { label: string; n: number }[];
  age_summary?: {
    mean?: number | null;
    sd?: number | null;
    min?: number | null;
    median?: number | null;
    max?: number | null;
  };
  age_bands?: { label: string; n: number }[];
  top_diseases?: { label: string; patient_count: number }[];
  top_drugs?: { label: string; patient_count: number }[];
};

type ResponseMetadata = SchemaMetadata & {
  semantic_overview?: SemanticOverview;
  disease_count?: DiseaseCount;
  disease_intersection?: DiseaseIntersection;
  disease_drug_overlap?: DiseaseDrugOverlap;
  drug_mechanism_summary?: DrugMechanismSummary;
  sample_distribution?: SampleDistribution;
  demographic_distribution?: SampleDistribution;
  variable_distribution?: unknown;
  academic_workflow?: unknown;
  feasibility?: unknown;
  schema?: string | SchemaMetadata;
};

type BaselineSummary = {
  n: number;
  mean: number | null;
  sd: number | null;
};

type ChatResponse = {
  reply: string;
  status: string;
  step?: string;
  params?: Record<string, unknown>;
  options?: Option[];
  metadata?: ResponseMetadata;
  sql?: string;
  warnings?: string[];
  count?: number;
  can_analyze?: boolean;
  cohort_params?: Record<string, unknown>;
  preview?: {
    row_count: number;
    has_numeric_exposure: boolean;
    outcome?: { positive?: number; negative?: number; rate?: number | null };
    baseline?: Record<string, BaselineSummary>;
  };
  selected_methods?: string[];
  stats?: {
    baseline?: Record<string, BaselineSummary | Record<string, number | null>>;
    group_or?: {
      available?: boolean;
      odds_ratio?: number;
      ci_low?: number;
      ci_high?: number;
      message?: string;
      method?: string;
    };
    mr?: {
      available?: boolean;
      odds_ratio?: number;
      ci_low?: number;
      ci_high?: number;
      message?: string;
      method?: string;
    };
  };
  visualization_html?: string;
  report_url?: string;
};

type Message = {
  id: string;
  role: ChatRole;
  content: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001";
const AGENT_ENDPOINT = process.env.NEXT_PUBLIC_AGENT_ENDPOINT ?? "/api/agent-v2";
const sessionId = `web-${Math.random().toString(36).slice(2)}`;

function formatNumber(value?: number | null) {
  if (typeof value !== "number") return "--";
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 3 }).format(value);
}

function renderMarkdownContent(content: string) {
  return (
    <ReactMarkdown
      components={{
        code({ children, className }) {
          const inline = !className;
          if (inline) {
            return <code className="rounded bg-neutral-100 px-1 py-0.5 text-[12px]">{children}</code>;
          }
          return (
            <code className="block overflow-x-auto whitespace-pre rounded-md bg-neutral-950 p-3 text-[12px] leading-5 text-neutral-50">
              {children}
            </code>
          );
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "你好，我可以读取队列数据库结构，协助生成队列研究和孟德尔随机化 SQL。",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [latestResult, setLatestResult] = useState<ChatResponse | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const schemaMetadata = useMemo<SchemaMetadata | null>(() => {
    const metadata = latestResult?.metadata;
    if (!metadata) return null;
    if (metadata.tables) return metadata;
    if (metadata.schema && typeof metadata.schema === "object" && "tables" in metadata.schema) {
      return metadata.schema;
    }
    return null;
  }, [latestResult]);

  const semanticOverview = latestResult?.metadata?.semantic_overview;
  const diseaseCount = latestResult?.metadata?.disease_count;
  const diseaseIntersection = latestResult?.metadata?.disease_intersection;
  const diseaseDrugOverlap = latestResult?.metadata?.disease_drug_overlap;
  const drugMechanismSummary = latestResult?.metadata?.drug_mechanism_summary;
  const sampleDistribution = latestResult?.metadata?.sample_distribution ?? latestResult?.metadata?.demographic_distribution;

  const metricCount = useMemo(() => {
    if (typeof latestResult?.count === "number") return latestResult.count;
    return drugMechanismSummary?.drug_users_in_disease ?? diseaseDrugOverlap?.drug_users_in_disease ?? diseaseIntersection?.count ?? diseaseCount?.patient_count ?? sampleDistribution?.total_patients ?? schemaMetadata?.total_rows ?? semanticOverview?.total_patients;
  }, [latestResult, drugMechanismSummary, diseaseDrugOverlap, diseaseIntersection, diseaseCount, sampleDistribution, schemaMetadata, semanticOverview]);

  const downloadUrl = latestResult?.report_url ? `${API_BASE_URL}${latestResult.report_url}` : null;
  const downloadLabel = downloadUrl?.endsWith(".csv") ? "下载数据" : "下载报告";

  function appendAssistant(data: ChatResponse & { analysis_result?: ChatResponse }) {
    if (data.analysis_result) {
      data = { ...data, ...data.analysis_result };
    }
    setLatestResult(data);
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.sql ? `${data.reply}\n\n\`\`\`sql\n${data.sql}\n\`\`\`` : data.reply,
      },
    ]);
  }

  async function sendMessage(rawMessage: string) {
    const text = rawMessage.trim();
    if (!text || isLoading || isAnalyzing) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}${AGENT_ENDPOINT}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      appendAssistant((await response.json()) as ChatResponse);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "未知错误";
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `请求失败：${detail}`,
        },
      ]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  }

  async function startAnalysis() {
    if (isAnalyzing) return;
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", content: "开始分析" },
    ]);
    setIsAnalyzing(true);
    try {
      const response = await fetch(`${API_BASE_URL}${AGENT_ENDPOINT}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: "开始分析", session_id: sessionId }) });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      appendAssistant((await response.json()) as ChatResponse);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "未知错误";
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: "assistant", content: `分析失败：${detail}` },
      ]);
    } finally {
      setIsAnalyzing(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendMessage(input);
  }

  return (
    <main className="flex h-screen min-h-[720px] bg-[#f6f7f9] text-neutral-950">
      <section className="flex w-full max-w-[520px] basis-1/3 flex-col border-r border-neutral-200 bg-white">
        <header className="flex h-16 items-center justify-between border-b border-neutral-200 px-5">
          <div>
            <h1 className="text-base font-semibold">Medical Cohort AI</h1>
            
          </div>
          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">Online</span>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-3 ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {message.role === "assistant" && (
                <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-neutral-950 text-xs font-semibold text-white">
                  美女
                </div>
              )}
              <div
                className={`max-w-[82%] rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm ${
                  message.role === "user"
                    ? "rounded-br-md bg-neutral-950 text-white"
                    : "rounded-bl-md border border-neutral-200 bg-[#fafafa] text-neutral-900"
                }`}
              >
                <div className="prose prose-sm max-w-none break-words prose-pre:m-0 prose-pre:bg-transparent prose-pre:p-0">
                  {renderMarkdownContent(message.content)}
                </div>
              </div>
              {message.role === "user" && (
                <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-sky-600 text-xs font-semibold text-white">
                  帅哥
                </div>
              )}
            </div>
          ))}
          {(isLoading || isAnalyzing) && (
            <div className="flex items-center gap-3 text-sm text-neutral-500">
              <div className="grid h-8 w-8 place-items-center rounded-full bg-neutral-950 text-xs font-semibold text-white">美女</div>
              <span>{isAnalyzing ? "正在执行 SQL 并生成报告..." : "正在分析..."}</span>
            </div>
          )}
        </div>

        {(latestResult?.options?.length || latestResult?.can_analyze || downloadUrl) && (
          <div className="border-t border-neutral-200 px-5 py-3">
            <div className="flex flex-wrap gap-2">
              {latestResult?.options?.map((option) => (
                <Button
                  key={option.value}
                  type="button"
                  variant="secondary"
                  className="h-9 max-w-full justify-start truncate text-xs"
                  title={option.description ?? option.label}
                  onClick={() => void sendMessage(option.value)}
                >
                  {option.label}
                </Button>
              ))}
              {latestResult?.can_analyze && (
                <Button type="button" className="h-9 text-xs" disabled={isAnalyzing} onClick={() => void startAnalysis()}>
                  {isAnalyzing ? "分析中" : "开始分析"}
                </Button>
              )}
              {downloadUrl && (
                <a
                  href={downloadUrl}
                  className="inline-flex h-9 items-center rounded-md border border-neutral-200 bg-white px-4 text-xs font-medium text-neutral-900 hover:bg-neutral-50"
                >
                  {downloadLabel}
                </a>
              )}
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="border-t border-neutral-200 p-4">
          <div className="flex gap-2 rounded-xl border border-neutral-200 bg-white p-2 shadow-sm">
            <input
              ref={inputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="输入：你能做什么 / 孟德尔随机化"
              className="min-w-0 flex-1 bg-transparent px-3 text-sm outline-none placeholder:text-neutral-400"
            />
            <Button type="submit" disabled={isLoading || isAnalyzing || !input.trim()}>
              发送
            </Button>
          </div>
        </form>
      </section>

      <section className="flex min-w-0 flex-1 basis-2/3 flex-col">
        <header className="flex h-16 items-center justify-between border-b border-neutral-200 bg-white px-6">
          <div>
            <h2 className="text-base font-semibold">结果工作区</h2>
            <p className="text-xs text-neutral-500">表结构、统计数字、图表和报告会显示在这里</p>
          </div>
          <div className="text-xs text-neutral-500">localhost:3000</div>
        </header>

        <div className="flex-1 overflow-y-auto p-6">
          {!latestResult ? (
            <div className="flex h-full items-center justify-center text-center">
              <div>
                <p className="text-xl font-semibold">欢迎进入医学队列分析工作台</p>
                <p className="mt-2 text-sm text-neutral-500">从左侧发送“你能做什么”开始扫描数据库能力。</p>
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="grid grid-cols-3 gap-4">
                <Card className="p-4">
                  <p className="text-xs text-neutral-500">分析行数</p>
                  <p className="mt-2 text-3xl font-semibold tabular-nums">{formatNumber(metricCount)}</p>
                </Card>
                <Card className="p-4">
                  <p className="text-xs text-neutral-500">OR 值</p>
                  <p className="mt-2 text-3xl font-semibold tabular-nums">
                    {formatNumber(latestResult.stats?.mr?.odds_ratio ?? latestResult.stats?.group_or?.odds_ratio)}
                  </p>
                </Card>
                <Card className="p-4">
                  <p className="text-xs text-neutral-500">当前步骤</p>
                  <p className="mt-2 truncate text-xl font-semibold">{latestResult.step ?? "metadata"}</p>
                </Card>
              </div>

              {semanticOverview && (
                <div className="rounded-lg border border-neutral-200 bg-white p-4">
                  <h3 className="text-sm font-semibold">语义化数据概况</h3>
                  <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">队列人数</p>
                      <p className="mt-1 text-xl font-semibold">{formatNumber(semanticOverview.total_patients)}</p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">性别分布</p>
                      <p className="mt-1 font-medium">
                        {(semanticOverview.sex_distribution ?? []).map((item) => `${item.label} ${item.n}`).join(" / ") || "--"}
                      </p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">首位诊断</p>
                      <p className="mt-1 font-medium">{semanticOverview.top_diseases?.[0]?.label ?? "--"}</p>
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="text-xs font-medium text-neutral-500">排名靠前的疾病</p>
                      <ul className="mt-2 space-y-1">
                        {(semanticOverview.top_diseases ?? []).map((item) => (
                          <li key={item.label} className="flex justify-between rounded bg-neutral-50 px-3 py-2">
                            <span>{item.label}</span>
                            <span className="tabular-nums">{formatNumber(item.patient_count)}人</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-neutral-500">常见药物</p>
                      <ul className="mt-2 space-y-1">
                        {(semanticOverview.top_drugs ?? []).map((item) => (
                          <li key={item.label} className="flex justify-between rounded bg-neutral-50 px-3 py-2">
                            <span>{item.label}</span>
                            <span className="tabular-nums">{formatNumber(item.patient_count)}人</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )}

              {sampleDistribution && (
                <div className="rounded-lg border border-neutral-200 bg-white p-4">
                  <h3 className="text-sm font-semibold">样本分布</h3>
                  <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">受试者人数</p>
                      <p className="mt-1 text-xl font-semibold">{formatNumber(sampleDistribution.total_patients)}</p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">性别</p>
                      <p className="mt-1 font-medium">
                        {(sampleDistribution.sex_distribution ?? []).map((item) => `${item.label} ${item.n}`).join(" / ") || "--"}
                      </p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">年龄</p>
                      <p className="mt-1 font-medium">
                        {typeof sampleDistribution.age_summary?.mean === "number"
                          ? `均值 ${sampleDistribution.age_summary.mean.toFixed(1)}岁`
                          : "--"}
                      </p>
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="text-xs font-medium text-neutral-500">年龄分层</p>
                      <ul className="mt-2 space-y-1">
                        {(sampleDistribution.age_bands ?? []).map((item) => (
                          <li key={item.label} className="flex justify-between rounded bg-neutral-50 px-3 py-2">
                            <span>{item.label}</span>
                            <span className="tabular-nums">{formatNumber(item.n)}人</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-neutral-500">常见诊断</p>
                      <ul className="mt-2 space-y-1">
                        {(sampleDistribution.top_diseases ?? []).slice(0, 5).map((item) => (
                          <li key={item.label} className="flex justify-between rounded bg-neutral-50 px-3 py-2">
                            <span>{item.label}</span>
                            <span className="tabular-nums">{formatNumber(item.patient_count)}人</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )}

              {diseaseCount && (
                <div className="rounded-lg border border-neutral-200 bg-white p-4">
                  <h3 className="text-sm font-semibold">疾病人数查询</h3>
                  <div className="mt-3 grid grid-cols-4 gap-3 text-sm">
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">疾病</p>
                      <p className="mt-1 font-medium">{diseaseCount.disease ?? "--"}</p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">患者人数</p>
                      <p className="mt-1 text-xl font-semibold">{formatNumber(diseaseCount.patient_count)}</p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">占比</p>
                      <p className="mt-1 text-xl font-semibold">
                        {typeof diseaseCount.prevalence === "number" ? `${(diseaseCount.prevalence * 100).toFixed(2)}%` : "--"}
                      </p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">诊断记录</p>
                      <p className="mt-1 text-xl font-semibold">{formatNumber(diseaseCount.record_count)}</p>
                    </div>
                  </div>
                </div>
              )}

              {diseaseIntersection && (
                <div className="rounded-lg border border-neutral-200 bg-white p-4">
                  <h3 className="text-sm font-semibold">复合疾病人群</h3>
                  <div className="mt-3 grid grid-cols-4 gap-3 text-sm">
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">疾病组合</p>
                      <p className="mt-1 font-medium">
                        {(diseaseIntersection.diseases ?? []).map((item) => item.label).join(" + ") || "--"}
                      </p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">交集人数</p>
                      <p className="mt-1 text-xl font-semibold">{formatNumber(diseaseIntersection.count)}</p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">总体占比</p>
                      <p className="mt-1 text-xl font-semibold">
                        {typeof diseaseIntersection.prevalence === "number" ? `${(diseaseIntersection.prevalence * 100).toFixed(2)}%` : "--"}
                      </p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">性别分布</p>
                      <p className="mt-1 font-medium">
                        {(diseaseIntersection.sex_distribution ?? [])
                          .map((item) => `${item.label} ${item.n}人${typeof item.percent === "number" ? ` ${(item.percent * 100).toFixed(1)}%` : ""}`)
                          .join(" / ") || "--"}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {diseaseDrugOverlap && (
                <div className="rounded-lg border border-neutral-200 bg-white p-4">
                  <h3 className="text-sm font-semibold">疾病人群用药分布</h3>
                  <div className="mt-3 grid grid-cols-4 gap-3 text-sm">
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">人群</p>
                      <p className="mt-1 font-medium">{diseaseDrugOverlap.disease ?? "--"}</p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">目标药物</p>
                      <p className="mt-1 font-medium">{diseaseDrugOverlap.drug ?? "--"}</p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">使用人数</p>
                      <p className="mt-1 text-xl font-semibold">{formatNumber(diseaseDrugOverlap.drug_users_in_disease)}</p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">使用率</p>
                      <p className="mt-1 text-xl font-semibold">
                        {typeof diseaseDrugOverlap.drug_use_rate_in_disease === "number"
                          ? `${(diseaseDrugOverlap.drug_use_rate_in_disease * 100).toFixed(1)}%`
                          : "--"}
                      </p>
                    </div>
                  </div>
                  <div className="mt-4 overflow-x-auto">
                    {(diseaseDrugOverlap.mechanisms ?? []).length > 0 && (
                      <div className="mb-4 grid grid-cols-3 gap-3">
                        {(diseaseDrugOverlap.mechanisms ?? []).slice(0, 6).map((item) => (
                          <div key={item.mechanism} className="rounded-md bg-neutral-50 p-3">
                            <p className="text-xs text-neutral-500">{item.mechanism}</p>
                            <p className="mt-1 text-lg font-semibold">{formatNumber(item.patient_count)}人</p>
                            <p className="text-xs text-neutral-500">
                              {typeof item.patient_percent === "number" ? `${(item.patient_percent * 100).toFixed(1)}%` : ""}
                            </p>
                          </div>
                        ))}
                      </div>
                    )}
                    <table className="w-full text-left text-sm">
                      <thead className="bg-neutral-50 text-xs text-neutral-500">
                        <tr>
                          <th className="px-3 py-2 font-medium">药物</th>
                          <th className="px-3 py-2 font-medium">中文名</th>
                          <th className="px-3 py-2 font-medium">类型</th>
                          <th className="px-3 py-2 font-medium">患者数</th>
                          <th className="px-3 py-2 font-medium">记录数</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(diseaseDrugOverlap.top_matching_drugs ?? []).slice(0, 8).map((item) => (
                          <tr key={item.label} className="border-t border-neutral-100">
                            <td className="px-3 py-2">{item.label}</td>
                            <td className="px-3 py-2">
                              {diseaseDrugOverlap.translated_drugs?.find((drug) => drug.drug_label === item.label)?.drug_name_cn ?? "--"}
                            </td>
                            <td className="px-3 py-2">
                              {diseaseDrugOverlap.translated_drugs?.find((drug) => drug.drug_label === item.label)?.mechanism ?? "--"}
                            </td>
                            <td className="px-3 py-2 tabular-nums">{formatNumber(item.patient_count)}</td>
                            <td className="px-3 py-2 tabular-nums">{formatNumber(item.record_count)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {diseaseDrugOverlap.counting_note && (
                    <p className="mt-3 text-xs text-neutral-500">{diseaseDrugOverlap.counting_note}</p>
                  )}
                </div>
              )}

              {drugMechanismSummary && (
                <div className="rounded-lg border border-neutral-200 bg-white p-4">
                  <h3 className="text-sm font-semibold">降压药机制分类</h3>
                  <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">人群</p>
                      <p className="mt-1 font-medium">{drugMechanismSummary.disease ?? "--"}</p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">患者级用药人数</p>
                      <p className="mt-1 text-xl font-semibold">{formatNumber(drugMechanismSummary.drug_users_in_disease)}</p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">机制类型数</p>
                      <p className="mt-1 text-xl font-semibold">{formatNumber(drugMechanismSummary.mechanisms?.length)}</p>
                    </div>
                  </div>
                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="bg-neutral-50 text-xs text-neutral-500">
                        <tr>
                          <th className="px-3 py-2 font-medium">类型</th>
                          <th className="px-3 py-2 font-medium">中文药名</th>
                          <th className="px-3 py-2 font-medium">原始药名</th>
                          <th className="px-3 py-2 font-medium">患者数</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(drugMechanismSummary.translated_drugs ?? []).slice(0, 12).map((item) => (
                          <tr key={`${item.mechanism}-${item.drug_label}`} className="border-t border-neutral-100">
                            <td className="px-3 py-2">{item.mechanism}</td>
                            <td className="px-3 py-2 font-medium">{item.drug_name_cn}</td>
                            <td className="px-3 py-2 text-neutral-600">{item.drug_label}</td>
                            <td className="px-3 py-2 tabular-nums">{formatNumber(item.patient_count)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {drugMechanismSummary.counting_note && (
                    <p className="mt-3 text-xs text-neutral-500">{drugMechanismSummary.counting_note}</p>
                  )}
                </div>
              )}

              {schemaMetadata?.tables && (
                <div className="rounded-lg border border-neutral-200 bg-white">
                  <div className="border-b border-neutral-200 px-4 py-3">
                    <h3 className="text-sm font-semibold">数据库信息</h3>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="bg-neutral-50 text-xs text-neutral-500">
                        <tr>
                          <th className="px-4 py-3 font-medium">表名</th>
                          <th className="px-4 py-3 font-medium">行数</th>
                          <th className="px-4 py-3 font-medium">字段</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(schemaMetadata.tables).map(([name, table]) => (
                          <tr key={name} className="border-t border-neutral-100">
                            <td className="px-4 py-3 font-medium">{name}</td>
                            <td className="px-4 py-3 tabular-nums">{formatNumber(table.row_count)}</td>
                            <td className="px-4 py-3 text-neutral-600">
                              {table.columns.map((column) => column.name).join(", ")}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {latestResult.preview && (
                <div className="rounded-lg border border-neutral-200 bg-white p-4">
                  <h3 className="text-sm font-semibold">数据预检</h3>
                  <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">提取行数</p>
                      <p className="mt-1 text-xl font-semibold">{formatNumber(latestResult.preview.row_count)}</p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">结局事件</p>
                      <p className="mt-1 text-xl font-semibold">{formatNumber(latestResult.preview.outcome?.positive)}</p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">暴露有效值</p>
                      <p className="mt-1 text-xl font-semibold">
                        {formatNumber(latestResult.preview.baseline?.exposure_value?.n)}
                      </p>
                    </div>
                  </div>
                </div>
              )}
              {latestResult.stats && (
                <div className="rounded-lg border border-neutral-200 bg-white p-4">
                  <h3 className="text-sm font-semibold">统计结果</h3>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">MR 方法</p>
                      <p className="mt-1 font-medium">{latestResult.stats.mr?.method ?? "NA"}</p>
                    </div>
                    <div className="rounded-md bg-neutral-50 p-3">
                      <p className="text-xs text-neutral-500">95% CI</p>
                      <p className="mt-1 font-medium">
                        {formatNumber(latestResult.stats.mr?.ci_low)} - {formatNumber(latestResult.stats.mr?.ci_high)}
                      </p>
                    </div>
                  </div>
                  {latestResult.stats.mr?.message && (
                    <p className="mt-3 text-sm text-amber-700">{latestResult.stats.mr.message}</p>
                  )}
                </div>
              )}

              {latestResult.sql && (
                <div className="rounded-lg border border-neutral-200 bg-white">
                  <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-3">
                    <h3 className="text-sm font-semibold">生成的 SQL</h3>
                    {latestResult.warnings && latestResult.warnings.length > 0 && (
                      <span className="text-xs text-amber-700">{latestResult.warnings[0]}</span>
                    )}
                  </div>
                  <pre className="max-h-[420px] overflow-auto bg-neutral-950 p-4 text-xs leading-5 text-neutral-50">
                    <code>{latestResult.sql}</code>
                  </pre>
                </div>
              )}

              <div className="rounded-lg border border-neutral-200 bg-white p-6">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium">图表</p>
                  {downloadUrl && (
                    <a href={downloadUrl} className="text-sm font-medium text-sky-700 hover:text-sky-900">
                      {downloadLabel}
                    </a>
                  )}
                </div>
                {latestResult.visualization_html ? (
                  <div
                    className="mt-4 overflow-hidden rounded-md border border-neutral-200 bg-white [&_img]:h-auto [&_img]:w-full"
                    dangerouslySetInnerHTML={{ __html: latestResult.visualization_html }}
                  />
                ) : (
                  <div className="mt-4 h-48 rounded-md border border-neutral-200 bg-[linear-gradient(135deg,#f8fafc_25%,#eef2f7_25%,#eef2f7_50%,#f8fafc_50%,#f8fafc_75%,#eef2f7_75%)] bg-[length:24px_24px]" />
                )}
              </div>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}








