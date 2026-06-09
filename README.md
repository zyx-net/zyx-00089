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

```bash
# 初始化数据库
python main.py init

# 生成样例数据
python main.py sample

# 一键导入所有样例数据并检测异常
python main.py import-all

# 执行异常检测
python main.py detect

# 查看异常列表
python main.py anomalies

# 复核异常（标记为误报）
python main.py review 1 false_positive --comment "测试误报"

# 回滚批次
python main.py rollback --batch-id 1 --reason "数据有误"

# 导出HTML报告
python main.py report --format html

# 查看统计汇总
python main.py summary

# 启动Web界面
python main.py web
```

### 4. Web界面

```bash
python main.py web --host 0.0.0.0 --port 5000
```

访问 http://localhost:5000

## 可复现异常场景

样例数据包含以下可复现的异常场景：

1. **缺少地块编号** - 水表读数某行未提供地块编号
2. **日期格式错误** - 使用不支持的日期格式 `2025.06.01`
3. **读数冲突** - P004 同一时间提交不同读数（400 vs 410）
4. **引用不存在地块** - 引用 P888 和 P999
5. **超计划用水** - P001 6月计划50方，实际使用75方
6. **倒表** - P002 读数从 206.00 回退到 180.00
7. **漏采** - P003 两次读数间隔30小时（阈值25小时）
8. **重复上报** - P004 同一读数重复提交两次
9. **未知地块** - P999 未在地块台账中登记

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
│   ├── reports.py           # 报告生成
│   ├── sample_data.py       # 样例数据生成
│   ├── cli.py               # 命令行接口
│   ├── web.py               # Web管理界面
│   └── acceptance_test.py   # 验收测试
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
python main.py acceptance-test
```

### 手动验收流程

1. **导入数据**
   ```bash
   python main.py sample
   python main.py import parcel data/sample_parcels.csv
   python main.py import plan data/sample_plans.csv
   python main.py import weather data/sample_weather.csv
   python main.py import meter data/sample_meters.csv
   ```

2. **检测异常**
   ```bash
   python main.py detect
   python main.py anomalies
   ```

3. **复核误报**
   ```bash
   python main.py review <anomaly_id> false_positive --comment "误报"
   ```

4. **回滚批次**
   ```bash
   python main.py rollback --batch-id <batch_id> --reason "回滚测试"
   ```

5. **导出报告**
   ```bash
   python main.py report --format html
   python main.py report --format csv
   ```

6. **验证重启一致性**
   ```bash
   python main.py summary
   # 关闭程序后重新打开
   python main.py summary  # 验证数据一致
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

| 异常代码 | 异常类型 | 检测规则 | 严重程度 |
|---------|---------|---------|---------|
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
