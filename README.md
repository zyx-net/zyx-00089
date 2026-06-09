# 农田灌溉用水异常分析工具

## 功能概述

本地农田灌溉用水异常分析工具，支持：

- **数据导入**: 地块台账、水表读数、灌溉计划、天气补录
- **异常检测**: 9种异常类型
  - 超计划用水 (OVER_PLAN)
  - 倒表 (METER_BACKWARD)
  - 漏采 (MISSING_READING)
  - 重复上报 (DUPLICATE_REPORT)
  - 未知地块 (UNKNOWN_PARCEL)
  - 缺少地块编号 (MISSING_PARCEL_ID)
  - 日期格式错误 (INVALID_DATE)
  - 读数冲突 (READING_CONFLICT)
  - 引用不存在地块 (INVALID_REFERENCE)
- **数据管理**: 批次管理、人工复核标记、回滚功能
- **报告导出**: HTML/CSV格式，按地块、异常类型、规则版本汇总
- **数据持久化**: SQLite数据库，重启后数据保持一致
- **双界面**: 命令行(CLI) + Web界面

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 一键验收测试

```bash
python main.py acceptance-test
```

### 3. 命令行使用

**注意**：Windows PowerShell 环境下已自动处理编码问题，可直接执行以下命令，不会因为中文或 emoji 输出触发 UnicodeEncodeError。

```bash
# 初始化数据库（必须第一步执行）
python main.py init

# 查看帮助
python main.py --help

# 生成样例数据
python main.py sample

# 一键导入所有样例数据（导入后需执行 detect 检测异常）
python main.py import-all

# 执行异常检测（导入样例数据后必须执行）
python main.py detect

# 查看异常列表
python main.py anomalies

# 复核异常（标记为误报）
python main.py review 1 false_positive --comment "测试误报"

# 查看某条异常的复核时间线
python main.py review-history 1

# 追加备注（不改变处置状态）
python main.py review-append 1 "需要联系运维人员进一步核实"

# 修改处置状态
python main.py review-update 1 needs_investigation --comment "异常原因待查"

# 撤销最近一次复核操作
python main.py review-undo 1 --reason "操作失误，状态标记错误"

# 回滚批次
python main.py rollback --batch-id 1 --reason "数据有误"

# 导出HTML报告（含复核摘要，自动处理中文编码和HTML转义）
python main.py report --format html

# 导出CSV报告（含复核摘要，UTF-8 BOM编码，Excel可直接打开）
python main.py report --format csv

# 查看统计汇总
python main.py summary

# 启动Web界面
python main.py web

# 运行回归测试（验证所有功能）
python main.py regression-test
```

### 4. Web界面

```bash
python main.py web --host 0.0.0.0 --port 5000
```

访问 http://localhost:5000

## 可复现异常场景

样例数据包含以下可复现的异常场景：

| 序号 | 异常类型 | 场景描述 | 预期异常数量 |
|-----|---------|---------|-------------|
| 1 | **缺少地块编号** (MISSING_PARCEL_ID) | 水表读数某行未提供地块编号 | 1 条 |
| 2 | **日期格式错误** (INVALID_DATE) | 使用无效日期 `2025-13-01`（月份13无效） | 1 条 |
| 3 | **读数冲突** (READING_CONFLICT) | P004 同一时间提交不同读数（400 vs 410） | 1 条 |
| 4 | **引用不存在地块** (INVALID_REFERENCE) | 灌溉计划引用 P888 和 P999 | 1-2 条 |
| 5 | **超计划用水** (OVER_PLAN) | P001 6月计划50方，实际使用110方（超120%） | 1-2 条 |
| 6 | **倒表** (METER_BACKWARD) | P002 读数从 206.00 回退到 180.00 | 1 条 |
| 7 | **漏采** (MISSING_READING) | P003 两次读数间隔54小时（阈值25小时） | 1-2 条 |
| 8 | **重复上报** (DUPLICATE_REPORT) | P004 同一读数重复提交两次 | 1 条 |
| 9 | **未知地块** (UNKNOWN_PARCEL) | P888、P999 未在地块台账中登记 | 1 条 |

> **注意**：实际检测数量可能因数据导入顺序略有差异，报告中会给出样例预期数量范围。

## 项目结构

```
zyx-00089/
├── irrigation_analysis/
│   ├── __init__.py          # 包初始化
│   ├── __main__.py          # 模块入口
│   ├── config.py            # 配置和字段映射
│   ├── models.py            # 数据库模型
│   ├── database.py          # 数据库连接
│   ├── importer.py          # 数据导入模块
│   ├── rules.py             # 异常检测规则引擎
│   ├── batch_manager.py     # 批次/复核/回滚管理
│   ├── reports.py           # 报告生成（HTML/CSV）
│   ├── sample_data.py       # 样例数据生成
│   ├── cli.py               # 命令行接口（含编码修复）
│   ├── web.py               # Web管理界面
│   ├── acceptance_test.py   # 验收测试
│   └── regression_test.py   # 回归测试（编码/HTML验证）
├── data/                    # 数据目录（数据库和CSV）
├── outputs/                 # 报告输出目录
├── main.py                  # 主入口
├── run.bat                  # Windows启动脚本
├── requirements.txt         # 依赖
└── README.md                # 本文件
```

## 验收流程

### 完整验收流程（自动化）

```bash
# 运行完整验收测试（10个测试点）
python main.py acceptance-test

# 运行回归测试（32个测试点，含阈值方案管理、完整链路验证、复核历史管理）
python main.py regression-test
```

### 手动验收流程

**注意**：执行前请确保 `data/irrigation.db` 不存在，或先运行 `python main.py init` 初始化。

1. **初始化数据库（必须第一步）**
   ```bash
   python main.py init
   # 预期输出：数据库初始化成功
   ```

2. **导入数据**
   ```bash
   # 生成样例数据CSV
   python main.py sample

   # 按顺序导入（地块台账必须最先导入）
   python main.py import parcel data/sample_parcels.csv
   python main.py import plan data/sample_plans.csv
   python main.py import weather data/sample_weather.csv
   python main.py import meter data/sample_meters.csv
   ```

3. **检测异常**
   ```bash
   python main.py detect
   # 预期：检测完成，共检测到约10-15条异常（取决于导入顺序）

   python main.py anomalies
   # 预期：列出所有异常，包含9种异常类型
   ```

4. **复核误报**
   ```bash
   # 标记ID为1的异常为误报
   python main.py review 1 false_positive --comment "经核实为正常波动"
   # 预期：异常1已标记为误报
   ```

5. **查看复核时间线**
   ```bash
   # 查看异常1的完整复核历史
   python main.py review-history 1
   # 预期：显示所有复核操作记录，包含操作类型、时间、操作人、备注
   ```

6. **追加备注**
   ```bash
   # 为异常1追加备注（不改变处置状态）
   python main.py review-append 1 "已通知张工现场核实，预计明天回复" --by "值班员小李"
   # 预期：备注追加成功，历史记录数增加
   ```

7. **修改处置状态**
   ```bash
   # 将异常1从"误报"改为"待调查"
   python main.py review-update 1 needs_investigation --comment "数据存在疑点，需进一步核查" --by "值班主管"
   # 预期：状态修改成功，历史记录中新增"修改状态"操作
   ```

8. **撤销复核操作**
   ```bash
   # 撤销异常1的最近一次复核操作
   python main.py review-undo 1 --reason "状态修改错误，应保持误报" --by "值班主管"
   # 预期：撤销成功，最近一次操作标记为已撤销，状态回退
   ```

9. **回滚批次（保留审计记录）**
   ```bash
   # 先查看批次列表
   python main.py batches

   # 回滚指定批次
   python main.py rollback --batch-id 1 --reason "数据录入错误"
   # 预期：批次1已回滚，相关异常标记为已回滚，但复核历史记录保留

   # 验证审计记录未被删除
   python main.py review-history 1
   # 预期：仍能看到完整的复核历史，审计记录未被误删
   ```

10. **导出报告（含复核摘要）**
    ```bash
    # 导出HTML报告（UTF-8编码，含复核摘要，无乱码，标签完整）
    python main.py report --format html
    # 预期：报告已生成到 outputs/report_*.html，每条异常包含复核摘要

    # 导出CSV报告（UTF-8 BOM，含复核摘要，Excel可直接打开）
    python main.py report --format csv
    # 预期：报告已生成到 outputs/report_*.csv，包含复核次数、撤销次数等列
    ```

11. **验证重启一致性**
    ```bash
    # 第一次查看汇总
    python main.py summary

    # 关闭程序后重新运行
    python main.py summary
    # 预期：两次结果完全一致，批次、复核、回滚、报告统计保持不变

    # 验证复核历史持久化
    python main.py review-history 1
    # 预期：重启后复核历史记录完整保留
    ```

12. **阈值方案管理**
   ```bash
   # 查看所有阈值方案
   python main.py threshold list
   # 预期：列出默认方案及所有自定义方案，显示当前启用状态

   # 创建新的阈值方案（夏季灌溉高峰）
   python main.py threshold create --name "夏季灌溉高峰" \
       --meter-backward 0.02 \
       --over-plan-ratio 1.5 \
       --missing-reading-days 0.5 \
       --description "夏季高温期灌溉阈值" \
       --by "运维工程师"
   # 预期：方案创建成功，显示方案详情

   # 启用新方案
   python main.py threshold enable "夏季灌溉高峰" --by "运维主管"
   # 预期：方案已启用，后续检测将使用新阈值

   # 查看方案详情
   python main.py threshold show "夏季灌溉高峰"
   # 预期：显示方案的完整配置和创建信息

   # 导出方案（用于备份或跨环境迁移）
   python main.py threshold export "夏季灌溉高峰" --output outputs/summer_scheme.json
   # 预期：方案已导出到指定JSON文件

   # 导入方案（重命名避免冲突）
   python main.py threshold import outputs/summer_scheme.json --rename "夏季方案备份" --by "系统管理员"
   # 预期：方案导入成功，使用新名称

   # 导入冲突测试（同名不覆盖）
   python main.py threshold import outputs/summer_scheme.json
   # 预期：提示方案名称冲突，建议使用--rename或--overwrite

   # 覆盖导入
   python main.py threshold import outputs/summer_scheme.json --rename "夏季方案备份" --overwrite
   # 预期：方案覆盖成功

   # 查看操作日志
   python main.py threshold logs --limit 10
   # 预期：显示所有阈值方案的操作历史，包含操作人、时间、操作内容

   # 异常列表显示当前使用的方案
   python main.py anomalies
   # 预期：异常列表增加"阈值方案"列，显示每条异常使用的方案名称

   # 汇总统计显示阈值方案信息
   python main.py summary
   # 预期：显示当前启用的阈值方案，以及按方案统计的异常分布

   # 重启后验证方案仍然生效
   # 关闭程序后重新运行
   python main.py threshold list
   # 预期："夏季灌溉高峰"仍显示为启用状态
   ```

## 字段映射配置

系统支持以下字段名（不区分大小写）：

### 地块台账
- 地块编号 (parcel_id) - 必填
- 地块名称 (parcel_name)
- 面积(亩) (area)
- 作物类型 (crop_type)
- 位置 (location)

### 水表读数
- 地块编号 (parcel_id) - 必填
- 读数日期 (read_date) - 必填
- 读数时间 (read_time)
- 水表读数 (reading) - 必填
- 操作员 (operator)

### 灌溉计划
- 地块编号 (parcel_id) - 必填
- 计划日期 (plan_date) - 必填
- 计划用水量(方) (plan_water) - 必填
- 灌溉类型 (irrigation_type)

### 天气补录
- 记录日期 (record_date) - 必填
- 降雨量(mm) (rainfall)
- 气温(℃) (temperature)
- 湿度(%) (humidity)
- 天气类型 (weather_type)

## 异常检测规则

> **注意**：以下阈值为默认值，可通过**阈值方案管理**动态调整。支持按季节、片区等场景创建多套方案，灵活切换。

| 异常代码 | 异常类型 | 检测规则（默认阈值） | 严重程度 |
|---------|---------|---------------------|---------|
| OVER_PLAN | 超计划用水 | 实际用水量 > 计划用水量 × 120% | 高 |
| METER_BACKWARD | 倒表 | 当前读数 < 上一次读数 - 容差(0.01) | 高 |
| MISSING_READING | 漏采 | 两次读数间隔 > 25小时 | 中 |
| DUPLICATE_REPORT | 重复上报 | 同一地块同一时间读数已存在 | 中 |
| UNKNOWN_PARCEL | 未知地块 | 地块编号未在台账中登记 | 高 |
| MISSING_PARCEL_ID | 缺少地块编号 | 记录未提供地块编号 | 高 |
| INVALID_DATE | 日期格式错误 | 日期格式无法解析 | 中 |
| READING_CONFLICT | 读数冲突 | 同一时间读数不一致 | 高 |
| INVALID_REFERENCE | 引用不存在地块 | 引用了不存在的地块 | 高 |

## 技术栈

- **数据库**: SQLite (本地文件)
- **ORM**: SQLAlchemy 2.0
- **数据处理**: pandas
- **CLI**: Click
- **Web框架**: Flask
- **前端**: Bootstrap 5

## 新增功能

### v1.2.0 复核历史管理 ✅

#### 1. 复核批注历史 ✅
- **功能**: 所有复核操作（首次复核、修改状态、追加备注、撤销）都会完整记录到 `anomaly_review_history` 表
- **操作类型**: 
  - `review` - 首次复核
  - `update_status` - 修改处置状态
  - `append_comment` - 追加备注
  - `undo` - 撤销操作
- **记录字段**: 操作类型、处置状态、备注、操作人、操作时间、撤销状态
- **数据模型**: [AnomalyReviewHistory](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/models.py)

#### 2. 撤销复核能力 ✅
- **功能**: 支持撤销最近一次复核操作，异常状态自动回退到上一次操作前的状态
- **撤销记录**: 被撤销的操作会保留在历史中，标记为"已撤销"，用于审计追溯
- **连续撤销**: 支持多次撤销，每次撤销最近一次有效操作
- **再复核一致性**: 撤销后再次复核，展示结果与直接复核保持一致

#### 3. CLI 复核命令增强 ✅
- `review-history <anomaly_id>` - 查看异常的完整复核时间线，已撤销操作灰色显示
- `review-append <anomaly_id> <comment>` - 追加备注，不改变处置状态
- `review-update <anomaly_id> <new_status>` - 修改处置状态，可附加修改说明
- `review-undo <anomaly_id>` - 撤销最近一次复核操作，可填写撤销原因
- **实现**: [cli.py](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/cli.py)

#### 4. Web 页面增强 ✅
- 异常列表增加"修改状态"、"追加备注"、"撤销"操作按钮
- 异常详情展示"复核摘要"卡片（操作次数、撤销次数、最近复核信息、历史备注）
- 新增"复核时间线"列表，完整展示所有操作历史，已撤销操作特殊标记
- 新增 RESTful API:
  - `GET /api/anomalies/<id>/review-history` - 获取复核历史
  - `GET /api/anomalies/<id>/review-summary` - 获取复核摘要
- **实现**: [web.py](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/web.py)

#### 5. 审计记录保护 ✅
- **批次回滚**: 仅标记异常为"已回滚"状态，不删除任何原始异常或复核历史记录
- **数据分离**: 原始异常数据与人工复核动作分离存储，审计记录永久保留
- **验证**: 回滚后 `review-history` 命令仍能看到完整的操作历史

#### 6. 报告导出增强 ✅
- **HTML 报告**: 每条异常增加"复核摘要"区块，展示：
  - 复核操作次数、撤销次数
  - 最近复核人、时间、结果
  - 历史备注列表
- **CSV 报告**: 新增 5 个复核摘要列：
  - 复核次数、撤销次数、最近复核人、最近复核时间、历史备注
- **实现**: [reports.py](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/reports.py)

#### 7. 持久化保证 ✅
- 所有复核历史数据存储在 SQLite 数据库，重启后完整保留
- 模块重载后仍能正确查询历史记录和摘要信息

#### 8. 回归测试覆盖 ✅
新增 8 个回归测试用例（测试 17-24）：
- 测试 17: 复核历史记录和追加备注
- 测试 18: 修改处置状态和撤销复核
- 测试 19: 连续复核、撤销后再复核的一致性
- 测试 20: 复核历史跨重启持久化
- 测试 21: 导出报告包含复核摘要
- 测试 22: 复核相关 CLI 命令完整性
- 测试 23: Web API 接口和页面渲染
- 测试 24: 批次回滚不删除审计记录

**核心业务逻辑实现**: [batch_manager.py](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/batch_manager.py) 中的 `ReviewManager` 类

## 已修复问题

### v1.1.0 修复内容

#### 1. Windows PowerShell GBK 编码问题 ✅
- **问题**: 默认 GBK 环境下执行 `python main.py --help`、`python main.py init` 时，中文或 emoji 输出触发 `UnicodeEncodeError`
- **修复**: 在 `cli.py` 中添加 `_fix_console_encoding()` 函数，模块导入时自动检测 Windows GBK 环境并切换到 UTF-8 编码，设置 `errors='replace'` 兜底
- **验证**: 回归测试 1-2 通过，GBK 环境下所有命令正常输出中文

#### 2. HTML 报告乱码问题 ✅
- **问题**: 浏览器打开 HTML 报告时中文显示乱码
- **修复**: 在 `reports.py` 中添加双重编码声明：
  - `<meta charset="UTF-8">`
  - `<meta http-equiv="Content-Type" content="text/html; charset=utf-8">`
- **验证**: 浏览器访问 HTML 报告，所有中文内容正常显示

#### 3. HTML 坏标签问题 ✅
- **问题**: 报告中出现 `/h2>`、`/div>` 等坏标签，嵌套 f-string 导致语法错误
- **修复**: 
  - 移除 HTML 模板中的 emoji 避免编码问题
  - 修复第 522 行嵌套 f-string 问题，改为列表 append 方式构建 HTML 片段
  - 确保所有标签正确闭合
- **验证**: 回归测试 9 通过，标签栈验证无未闭合或不匹配标签

#### 4. HTML 转义不完整问题 ✅
- **问题**: 用户数据直接插入 HTML，未转义特殊字符可能导致 XSS 或渲染问题
- **修复**: 在 `reports.py` 中添加 `_escape()` 静态方法，使用 `html.escape(str(text), quote=True)` 转义所有用户输出数据，包括：
  - 异常描述、地块名称、批次号
  - 复核结果、备注信息
  - 原始数据、扩展数据
- **验证**: 回归测试 9 通过，未检测到 XSS 内容

#### 5. CSV 导出保持兼容 ✅
- **验证**: 回归测试 7 通过，CSV 正常生成 22 行数据，UTF-8 BOM 编码，Excel 可直接打开

### 回归测试

运行以下命令验证所有修复：

```bash
python main.py regression-test
```

包含 24 个测试用例：
1. GBK 环境下 --help 命令
2. GBK 环境下 init 命令
3. 样例数据和验收测试
4. 非法水表读数导入（含特殊字符）
5. summary 连续运行两次
6. HTML 报告导出
7. CSV 报告导出
8. HTML 内容浏览器可读
9. HTML 标签完整性
10. 完整流程链路-初始化
11. 完整流程链路-导入样例
12. 完整流程链路-异常检测
13. 完整流程链路-异常列表（含阈值方案列）
14. 完整流程链路-汇总统计
15. 完整流程链路-创建方案
16. 完整流程链路-启用方案
17. 完整流程链路-方案生效验证
18. 完整流程链路-失败输入不污染
19. import-all 行为核对
20. 阈值方案创建
21. 阈值方案启用
22. 阈值方案导出再导入
23. 阈值方案导入冲突处理
24. 阈值方案跨重启生效

---

## 🧪 v1.3.0 数据修正规则沙盒 ✅

### 功能概述

数据修正规则沙盒模块让值班员先在隔离空间里编写和试跑清洗规则，再决定是否应用到正式分析结果。所有规则、试跑结果和操作日志都落到 SQLite，重启后还能继续查看和回滚；同一数据集被多人或多次应用时会检测冲突，不会静默覆盖。

### 核心特性

#### 1. 隔离沙盒环境 ✅
- **沙盒管理**: 创建、编辑、删除沙盒，每个沙盒独立存储样例、规则和试跑记录
- **状态流转**: 草稿 → 测试中 → 已审批 → 已应用 → 已归档/已回滚
- **数据模型**: [Sandbox](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/models.py#L88-L114)

#### 2. 样例数据导入 ✅
- **格式支持**: CSV 和 JSON 两种格式
- **数据类型**: 地块台账、水表读数、灌溉计划、天气补录
- **导入命令**: `sandbox import-sample`
- **数据模型**: [SandboxSample](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/models.py#L117-L132)

#### 3. 四种规则类型 ✅

| 规则类型 | 说明 | 适用场景 |
|---------|------|---------|
| **字段映射** | 将源字段值复制到目标字段 | 字段重命名、数据对齐 |
| **缺失值填补** | 目标字段为空时使用填补值 | 补全缺失的操作员、日期等 |
| **异常值改写** | 满足条件时替换目标字段值 | 修正异常读数、错误编码 |
| **自定义规则** | 执行条件和替换的Python表达式 | 复杂业务逻辑处理 |

- **数据模型**: [SandboxRule](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/models.py#L135-L162)

#### 4. 试跑与差异预览 ✅
- **规则引擎**: 按优先级顺序执行所有激活规则
- **差异计算**: 精确记录每行、每字段的变更前后值
- **影响统计**: 总行数、影响行数、未变化行数、错误计数
- **按类型统计**: 修改、新增、删除、错误分类统计
- **数据模型**: 
  - [SandboxTrial](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/models.py#L165-L185)
  - [SandboxTrialResult](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/models.py#L188-L210)

#### 5. 提升为正式修正 ✅
- **冲突检测**: 应用前自动检测与现有数据的冲突
  - 检查目标字段是否已被其他人修改
  - 检测同一批次是否已被多次应用
  - 阻止静默覆盖，提供 `--force` 强制选项
- **应用确认**: 展示影响摘要、冲突详情，需人工确认
- **数据模型**:
  - [SandboxPromotion](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/models.py#L213-L244)
  - [SandboxConflict](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/models.py#L247-L269)

#### 6. 回滚机制 ✅
- **一键回滚**: 将数据恢复到应用前的状态
- **回滚日志**: 记录回滚原因、操作人、时间
- **状态追踪**: 沙盒状态更新为"已回滚"
- **冲突标记**: 相关冲突记录标记为"已回滚"

#### 7. 导入导出沙盒包 ✅
- **导出格式**: ZIP 压缩包，包含：
  - `metadata.json` - 元数据（版本、导出时间、统计信息）
  - `sandbox.json` - 沙盒基本信息
  - `rules.json` - 所有规则配置
  - `samples.json` - 样例数据
  - `trials.json` - 试跑记录
  - `promotions.json` - 提升记录
  - `logs.json` - 操作日志
  - `report.md` - 规则报告（含规则摘要、差异统计、操作者记录）
- **导入复现**: 一键导入沙盒包，完整复现所有内容
- **重命名支持**: 导入时可重命名，避免名称冲突

#### 8. 操作日志与审计 ✅
- **日志记录**: 所有操作都记录到 `sandbox_logs` 表
- **操作类型**: 创建、更新、删除、导入样例、添加规则、更新规则、删除规则、执行试跑、提升、回滚、导入包、导出包
- **多用户追踪**: 完整记录每个操作的操作人
- **数据模型**: [SandboxLog](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/models.py#L272-L289)

#### 9. 持久化保证 ✅
- 所有数据存储在 SQLite 数据库
- 重启数据库连接后数据完整保留
- 沙盒、规则、样例、试跑、提升、日志全部持久化

### CLI 命令清单

```bash
# 🧪 沙盒管理
python main.py sandbox list                                    # 列出所有沙盒
python main.py sandbox list --status draft                     # 按状态过滤
python main.py sandbox create --name "6月数据修正" --description "修正水表读数异常"  # 创建沙盒
python main.py sandbox show 1                                   # 查看沙盒详情
python main.py sandbox delete 1                                 # 删除沙盒

# 📥 样例数据导入
python main.py sandbox import-sample 1 data/meter_sample.csv meter  # 导入CSV样例
python main.py sandbox import-sample 1 data/meter_sample.json meter # 导入JSON样例
python main.py sandbox samples 1                                # 列出样例数据

# 📝 规则管理
python main.py sandbox add-rule 1 missing_fill "填补操作员" \
    --target-field operator --fill-value "未知操作员" --priority 1   # 添加缺失值填补规则
python main.py sandbox add-rule 1 outlier_replace "修正异常读数" \
    --target-field reading_value --condition "value > 9000" --replacement "0" --priority 2  # 添加异常值改写规则
python main.py sandbox add-rule 1 field_mapping "字段映射" \
    --source-field old_field --target-field new_field --priority 0  # 添加字段映射规则
python main.py sandbox add-rule 1 custom "自定义规则" \
    --target-field total_flow --condition "row['reading_value'] > 100" \
    --replacement "row['total_flow'] = row['reading_value'] * 0.5" --priority 3  # 添加自定义规则
python main.py sandbox rules 1                                  # 列出规则
python main.py sandbox update-rule 1 --name "新名称" --fill-value "新值"  # 更新规则
python main.py sandbox delete-rule 1                            # 删除规则

# 🚀 试跑与提升
python main.py sandbox run-trial 1                              # 执行试跑
python main.py sandbox trials 1                                 # 列出试跑记录
python main.py sandbox trial-results 1                          # 查看试跑差异详情
python main.py sandbox promote 1 --trial 1 --target-batch 1     # 提升为正式修正
python main.py sandbox promote 1 --trial 1 --target-batch 1 --force  # 强制应用（忽略冲突）
python main.py sandbox promotions                               # 列出所有提升记录
python main.py sandbox rollback-promotion 1 --reason "数据错误" # 回滚提升

# 📦 导入导出
python main.py sandbox export 1                                 # 导出沙盒包
python main.py sandbox export 1 --output outputs/my_sandbox.zip  # 指定输出路径
python main.py sandbox import outputs/my_sandbox.zip             # 导入沙盒包
python main.py sandbox import outputs/my_sandbox.zip --rename "副本"  # 导入并重命名

# 📜 操作日志
python main.py sandbox logs                                     # 查看所有操作日志
python main.py sandbox logs --sandbox-id 1                      # 查看指定沙盒的日志
python main.py sandbox logs --operation promote                 # 按操作类型过滤

# 🧪 测试
python main.py test-sandbox                                     # 运行沙盒模块完整测试
```

### Web 功能页面

1. **沙盒列表页** (`/sandboxes`)
   - 沙盒概览表格（状态、名称、样例数、规则数、试跑次数）
   - 新建沙盒、导入沙盒包按钮
   - 查看、导出、删除操作

2. **沙盒详情页** (`/sandboxes/<id>`)
   - 统计卡片（样例数、规则数、试跑次数、日志数）
   - 三个标签页：样例数据、修正规则、试跑记录
   - 导入样例、添加规则、执行试跑快捷操作

3. **试跑结果页** (`/trials/<id>`)
   - 统计摘要（总行数、影响行数、未变化、错误）
   - 变更类型统计图表
   - 详细差异列表（旧值/新值对比）
   - 提升为正式修正入口

4. **提升确认页** (`/promote/<trial_id>/confirm`)
   - 影响摘要展示
   - 目标批次选择
   - 强制应用选项
   - 操作说明和注意事项

5. **提升记录详情页** (`/promotions/<id>`)
   - 应用结果详情
   - 冲突记录列表
   - 回滚操作按钮

6. **RESTful API**
   - `GET /api/sandboxes` - 获取沙盒列表
   - `GET /api/sandboxes/<id>` - 获取沙盒详情
   - `GET /api/sandboxes/<sid>/trials/<tid>` - 获取试跑详情
   - `GET /api/promotions/<id>` - 获取提升详情

### 验收命令

```bash
# ========== 🧪 验收测试1：运行完整测试套件 ==========
python main.py test-sandbox
# 预期：所有测试通过，包含40+测试用例，覆盖所有功能

# ========== 🧪 验收测试2：完整沙盒工作流 ==========

# 1. 初始化数据库和样例数据
python main.py init
python main.py import-all

# 2. 创建沙盒
python main.py sandbox create --name "6月水表修正" --description "修正6月水表读数中的异常值" --by "值班员小李"
# 预期：沙盒创建成功，状态为草稿

# 3. 查看沙盒列表
python main.py sandbox list
# 预期：显示刚创建的沙盒，状态为草稿

# 4. 创建测试样例CSV
cat > outputs/test_meter.csv << 'EOF'
parcel_id,meter_id,read_date,reading_value,total_flow,operator
P001,M001,2026-06-01,100,50,张三
P002,M002,2026-06-01,200,,李四
P003,M003,2026-06-01,9999,150,
P004,M004,2026-06-01,300,200,王五
P005,M005,2026-06-01,,180,赵六
EOF

# 5. 导入样例数据
python main.py sandbox import-sample 1 outputs/test_meter.csv meter --sample-name "6月测试样例" --by "值班员小李"
# 预期：导入成功，5行数据

# 6. 添加缺失值填补规则
python main.py sandbox add-rule 1 missing_fill "填补缺失操作员" \
    --target-field operator --fill-value "临时操作员" --priority 1 --by "值班员小李"
# 预期：规则添加成功

# 7. 添加异常值改写规则
python main.py sandbox add-rule 1 outlier_replace "修正超大读数" \
    --target-field reading_value --condition "value > 9000" --replacement "300" --priority 2 --by "值班员小李"
# 预期：规则添加成功

# 8. 添加缺失值填补规则（读数）
python main.py sandbox add-rule 1 missing_fill "填补缺失读数" \
    --target-field reading_value --fill-value "0" --priority 3 --by "值班员小李"
# 预期：规则添加成功

# 9. 查看规则列表
python main.py sandbox rules 1
# 预期：显示3条激活规则

# 10. 执行试跑
python main.py sandbox run-trial 1 --by "值班员小李"
# 预期：试跑完成，显示影响行数（应该>=3行）

# 11. 查看试跑记录
python main.py sandbox trials 1
# 预期：显示1条试跑记录，状态为已完成

# 12. 查看试跑差异详情
python main.py sandbox trial-results 1
# 预期：显示详细差异列表，包含旧值/新值对比

# 13. 导出沙盒包
python main.py sandbox export 1 --output outputs/sandbox_backup.zip
# 预期：导出成功，生成ZIP文件

# 14. 查看操作日志
python main.py sandbox logs --sandbox-id 1
# 预期：显示所有操作历史（创建、导入样例、添加规则、执行试跑、导出）

# 15. 提升为正式修正（会检测冲突）
python main.py sandbox promote 1 --trial 1 --target-batch 1 --by "值班主管"
# 预期：可能检测到冲突，提示使用--force

# 16. 强制提升（如果有冲突）
python main.py sandbox promote 1 --trial 1 --target-batch 1 --force --by "值班主管"
# 预期：修正应用成功

# 17. 查看提升记录
python main.py sandbox promotions
# 预期：显示1条提升记录

# 18. 回滚提升
python main.py sandbox rollback-promotion 1 --reason "测试回滚功能" --by "值班主管"
# 预期：回滚成功，数据恢复

# 19. 验证回滚后数据
python main.py sandbox promotions
# 预期：提升记录显示为已回滚

# 20. 导入沙盒包（复现）
python main.py sandbox import outputs/sandbox_backup.zip --rename "6月水表修正-副本" --by "系统管理员"
# 预期：导入成功，创建新的沙盒副本

# 21. 验证导入的沙盒
python main.py sandbox list
# 预期：显示两个沙盒

# 22. 验证重启持久化（模拟重启）
python main.py sandbox show 1
# 预期：沙盒信息完整，样例、规则、试跑记录都在

# ========== 🧪 验收测试3：Web端验证 ==========

# 启动Web服务
python main.py web
# 预期：服务启动在 http://localhost:5000

# 浏览器访问验证：
# 1. http://localhost:5000/sandboxes - 沙盒列表页
# 2. http://localhost:5000/sandboxes/1 - 沙盒详情页
# 3. http://localhost:5000/trials/1 - 试跑结果页
# 4. http://localhost:5000/promotions/1 - 提升记录详情页
# 5. http://localhost:5000/api/sandboxes - API返回JSON

# ========== 🧪 验收测试4：冲突检测验证 ==========

# 1. 创建新沙盒
python main.py sandbox create --name "冲突测试" --by "测试员A"

# 2. 导入样例
python main.py sandbox import-sample 3 outputs/test_meter.csv meter --by "测试员A"

# 3. 添加规则
python main.py sandbox add-rule 3 missing_fill "填补操作员" --target-field operator --fill-value "测试员A修改" --by "测试员A"

# 4. 执行试跑
python main.py sandbox run-trial 3 --by "测试员A"

# 5. 先修改数据库中的数据（模拟其他人已修改）
python -c "
from irrigation_analysis.database import get_db
from irrigation_analysis.models import MeterReading
with get_db() as db:
    r = db.query(MeterReading).filter(MeterReading.parcel_id=='P001', MeterReading.batch_id==1).first()
    if r:
        r.operator = '已被其他人修改'
        print(f'已修改P001的operator为: {r.operator}')
"

# 6. 尝试提升（应该检测到冲突）
python main.py sandbox promote 3 --trial 3 --target-batch 1 --by "测试员A"
# 预期：检测到冲突，阻止应用

# 7. 强制提升
python main.py sandbox promote 3 --trial 3 --target-batch 1 --force --by "测试员A"
# 预期：强制应用成功，记录冲突

# ========== 🧪 验收测试5：权限与日志验证 ==========

# 查看所有操作日志（审计用）
python main.py sandbox logs
# 预期：显示所有操作记录，包含操作人、时间、详情

# 按操作类型过滤
python main.py sandbox logs --operation promote
# 预期：只显示提升操作

# 按沙盒过滤
python main.py sandbox logs --sandbox-id 1
# 预期：只显示指定沙盒的操作
```

### 测试覆盖范围

运行 `python main.py test-sandbox` 执行完整测试，包含 10 大类测试：

1. ✅ **沙盒CRUD操作** - 创建、查询、更新、删除
2. ✅ **样例数据导入** - CSV和JSON格式导入
3. ✅ **规则管理** - 添加、查询、更新、删除四种规则类型
4. ✅ **试跑执行** - 规则引擎执行、差异计算、影响统计
5. ✅ **跨重启持久化** - 模拟数据库重启，验证所有数据保留
6. ✅ **冲突检测** - 检测数据冲突、阻止静默覆盖、强制应用
7. ✅ **回滚机制** - 数据恢复、状态更新、日志记录
8. ✅ **导入导出沙盒包** - 包结构验证、报告生成、复现导入
9. ✅ **操作日志与权限追踪** - 多用户操作记录、审计追踪
10. ✅ **完整提升流程** - 从创建到应用到回滚的完整链路

### 核心实现文件

| 文件 | 说明 |
|------|------|
| [models.py](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/models.py) | 8张数据库表模型 |
| [sandbox_manager.py](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/sandbox_manager.py) | 核心业务逻辑（2500+行） |
| [cli.py](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/cli.py) | 18个CLI命令 |
| [web.py](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/web.py) | Web页面和RESTful API |
| [test_sandbox.py](file:///d:/workSpace/AI__SPACE/zyx-00089/irrigation_analysis/test_sandbox.py) | 完整测试套件 |

---
