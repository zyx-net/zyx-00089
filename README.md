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
