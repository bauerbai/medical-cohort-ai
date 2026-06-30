# UK Biobank 模拟队列数据库语义层 (Semantic Layer 3.0)

## 数据库概览
- **数据库名称**: medical_cohort
- **核心 Schema**: ukb_semantic
- **关联主键**: 所有表均通过 `patient_id` (BIGINT) 进行关联。
- **设计目标**: 专为 AI Agent 和临床科研设计，已清除脏数据，完成官方字典 100% 映射，支持生存分析与纵向研究。

## 核心数据表字典

### 1. patient_master_index (患者主索引与协变量)
- **业务含义**: 融合 UKB 基线人口学、社会经济地位及核心协变量。
- **核心字段**:
  - `patient_id` (BIGINT): 患者唯一标识。
  - `age_at_recruitment` (NUMERIC): 入组基线年龄。
  - `sex` (VARCHAR): 性别编码。
  - `townsend_deprivation_index` (NUMERIC): 汤森剥夺指数（衡量社会经济地位）。

### 2. unified_diagnoses (终极诊断表)
- **业务含义**: 利用 UKB 官方字典表进行 100% 精准映射，包含全科和住院数据。
- **核心字段**:
  - `patient_id` (BIGINT), `event_date` (DATE): 诊断发生日期。
  - `mapped_icd10` (VARCHAR): 标准 ICD-10 编码（AI 过滤疾病的首选字段）。
  - `icd10_description` (VARCHAR): 疾病标准官方描述。

### 3. unified_first_occurrences (首发疾病时间线)
- **业务含义**: 将 UKB 宽表行转列，AI 生存分析必备核心表。
- **核心字段**:
  - `patient_id` (BIGINT), `field_id` (TEXT): 疾病字段标识。
  - `first_occurrence_date` (DATE): 首次发病日期。

### 4. unified_hospitalizations (住院与重症事件)
- **业务含义**: 包含住院时长、出院状态等重症核心指标。
- **核心字段**:
  - `patient_id` (BIGINT), `admission_date` (DATE), `discharge_date` (DATE)。
  - `length_of_stay_days` (INT): 自动计算的住院天数。

### 5. unified_medications (药品处方表)
- **业务含义**: 整合全科处方记录，翻译为标准药品成分和治疗分类。
- **核心字段**:
  - `patient_id` (BIGINT), `prescription_date` (DATE)。
  - `chemical_substance` (VARCHAR): 药品化学成分。
  - `therapeutic_chapter` (VARCHAR): BNF 治疗学分类章节。

### 6. unified_vitals (生命体征)
- **业务含义**: 包含基线收缩压(取两次测量均值)。
- **核心字段**:
  - `patient_id` (BIGINT), `systolic_bp` (NUMERIC): 基线收缩压均值。