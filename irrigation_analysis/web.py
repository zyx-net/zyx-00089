# -*- coding: utf-8 -*-
"""
Web管理界面
"""
import json
import os
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify, send_file
from werkzeug.utils import secure_filename

from .database import init_db, get_db_session
from .batch_manager import batch_manager, review_manager, rollback_manager
from .reports import report_generator
from .importer import DataImporter
from .rules import RuleEngine
from .sample_data import sample_data_generator
from .config import OUTPUT_DIR, DATA_DIR, EXCEPTION_TYPES
from .sandbox_manager import sandbox_manager, SandboxError

app = Flask(__name__)
app.secret_key = 'irrigation-analysis-secret-key'
app.config['UPLOAD_FOLDER'] = DATA_DIR
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

ALLOWED_EXTENSIONS = {'csv'}

init_db()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def render_page(child_template, **context):
    """渲染页面，正确处理模板继承"""
    import re

    title_match = re.search(r'{% block title %}(.*?){% endblock %}', child_template, re.DOTALL)
    content_match = re.search(r'{% block content %}(.*?){% endblock %}', child_template, re.DOTALL)
    scripts_match = re.search(r'{% block scripts %}(.*?){% endblock %}', child_template, re.DOTALL)

    title = title_match.group(1).strip() if title_match else ''
    content = content_match.group(1).strip() if content_match else ''
    scripts = scripts_match.group(1).strip() if scripts_match else ''

    template = BASE_TEMPLATE
    template = template.replace('{% block title %}农田灌溉用水异常分析系统{% endblock %}', title)
    template = template.replace('{% block content %}{% endblock %}', content)
    template = template.replace('{% block scripts %}{% endblock %}', scripts)

    return render_template_string(template, **context)


BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}农田灌溉用水异常分析系统{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; }
        .navbar { background: linear-gradient(135deg, #1e88e5, #1565c0); }
        .navbar-brand { color: white !important; font-weight: bold; }
        .nav-link { color: rgba(255,255,255,0.9) !important; }
        .nav-link:hover, .nav-link.active { color: white !important; background: rgba(255,255,255,0.15); border-radius: 5px; }
        .card { border: none; box-shadow: 0 2px 10px rgba(0,0,0,0.08); margin-bottom: 20px; }
        .card-header { background: white; border-bottom: 2px solid #e3f2fd; font-weight: bold; color: #1565c0; }
        .stat-card { text-align: center; padding: 20px; }
        .stat-value { font-size: 32px; font-weight: bold; color: #1565c0; }
        .stat-label { color: #666; margin-top: 5px; }
        .severity-high { color: #dc3545; font-weight: bold; }
        .severity-medium { color: #ffc107; font-weight: bold; }
        .severity-low { color: #28a745; font-weight: bold; }
        .badge-reviewed { background: #28a745; }
        .badge-pending { background: #6c757d; }
        .badge-false { background: #ffc107; color: #333; }
        .table-hover tbody tr:hover { background-color: #f5f9ff; }
        .anomaly-detail { background: #f8f9fa; padding: 15px; border-radius: 5px; margin-top: 10px; }
        .extra-data { background: #fff; padding: 10px; border-radius: 3px; font-family: monospace; font-size: 12px; max-height: 200px; overflow-y: auto; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg">
        <div class="container">
            <a class="navbar-brand" href="{{ url_for('dashboard') }}">
                <i class="bi bi-moisture"></i> 农田灌溉用水异常分析系统
            </a>
            <div class="collapse navbar-collapse">
                <ul class="navbar-nav ms-auto">
                    <li class="nav-item">
                        <a class="nav-link {% if request.endpoint == 'dashboard' %}active{% endif %}" href="{{ url_for('dashboard') }}">
                            <i class="bi bi-speedometer2"></i> 仪表盘
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {% if request.endpoint == 'anomalies' %}active{% endif %}" href="{{ url_for('anomalies') }}">
                            <i class="bi bi-exclamation-triangle"></i> 异常管理
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {% if request.endpoint == 'batches' %}active{% endif %}" href="{{ url_for('batches') }}">
                            <i class="bi bi-box-seam"></i> 批次管理
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {% if request.endpoint == 'rollbacks' %}active{% endif %}" href="{{ url_for('rollbacks') }}">
                            <i class="bi bi-arrow-counterclockwise"></i> 回滚记录
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {% if request.endpoint == 'import_page' %}active{% endif %}" href="{{ url_for('import_page') }}">
                            <i class="bi bi-upload"></i> 数据导入
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {% if request.endpoint == 'reports' %}active{% endif %}" href="{{ url_for('reports') }}">
                            <i class="bi bi-file-earmark-bar-graph"></i> 报告中心
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {% if request.endpoint == 'sandboxes' %}active{% endif %}" href="{{ url_for('sandboxes') }}">
                            <i class="bi bi-flask"></i> 沙盒管理
                        </a>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }} alert-dismissible fade show">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {% block content %}{% endblock %}
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    {% block scripts %}{% endblock %}
</body>
</html>
"""


@app.route('/')
def dashboard():
    """仪表盘"""
    summary = report_generator.generate_summary(use_cache=False)
    return render_page("""
{% block title %}仪表盘 - 农田灌溉用水异常分析系统{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="bi bi-speedometer2"></i> 仪表盘</h2>
    <div>
        <button class="btn btn-primary me-2" onclick="location.href='{{ url_for('generate_sample') }}'">
            <i class="bi bi-file-earmark-plus"></i> 生成样例数据
        </button>
        <button class="btn btn-success me-2" onclick="location.href='{{ url_for('run_detection') }}'">
            <i class="bi bi-search"></i> 执行检测
        </button>
        <button class="btn btn-info" onclick="location.href='{{ url_for('reports') }}'">
            <i class="bi bi-download"></i> 导出报告
        </button>
    </div>
</div>

<div class="row">
    <div class="col-md-2">
        <div class="card stat-card">
            <div class="stat-value">{{ summary.summary.total_anomalies }}</div>
            <div class="stat-label">异常总数</div>
        </div>
    </div>
    <div class="col-md-2">
        <div class="card stat-card">
            <div class="stat-value text-success">{{ summary.summary.review_status.reviewed }}</div>
            <div class="stat-label">已复核</div>
        </div>
    </div>
    <div class="col-md-2">
        <div class="card stat-card">
            <div class="stat-value text-warning">{{ summary.summary.review_status.not_reviewed }}</div>
            <div class="stat-label">待复核</div>
        </div>
    </div>
    <div class="col-md-2">
        <div class="card stat-card">
            <div class="stat-value text-info">{{ summary.summary.review_status.false_positive }}</div>
            <div class="stat-label">误报数</div>
        </div>
    </div>
    <div class="col-md-2">
        <div class="card stat-card">
            <div class="stat-value text-primary">{{ summary.summary.total_batches }}</div>
            <div class="stat-label">有效批次</div>
        </div>
    </div>
    <div class="col-md-2">
        <div class="card stat-card">
            <div class="stat-value text-secondary">{{ summary.summary.rolled_back_batches }}</div>
            <div class="stat-label">已回滚</div>
        </div>
    </div>
</div>

<div class="row">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-bar-chart"></i> 按异常类型统计
            </div>
            <div class="card-body">
                <table class="table table-hover">
                    <thead>
                        <tr>
                            <th>异常类型</th>
                            <th>代码</th>
                            <th>数量</th>
                            <th>样例预期</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for item in summary.by_type %}
                        <tr>
                            <td><strong>{{ item.name }}</strong></td>
                            <td><code>{{ item.code }}</code></td>
                            <td><span class="badge bg-danger">{{ item.count }}</span></td>
                            <td><small class="text-muted">{{ item.expected }}</small></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-geo-alt"></i> 按地块统计
            </div>
            <div class="card-body">
                <table class="table table-hover">
                    <thead>
                        <tr>
                            <th>地块编号</th>
                            <th>地块名称</th>
                            <th>异常数量</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for item in summary.by_parcel %}
                        <tr>
                            <td><code>{{ item.parcel_id }}</code></td>
                            <td>{{ item.parcel_name }}</td>
                            <td><span class="badge bg-primary">{{ item.count }}</span></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>

<div class="row">
    <div class="col-md-12">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-info-circle"></i> 可复现异常场景说明
            </div>
            <div class="card-body">
                <div class="alert alert-info">
                    <p><strong>样例数据包含以下可复现的异常场景：</strong></p>
                    <ul class="mb-0">
                        <li><strong>缺少地块编号</strong> - 水表读数中某行未提供地块编号</li>
                        <li><strong>日期格式错误</strong> - 使用了不支持的日期格式 2025.06.01</li>
                        <li><strong>读数冲突</strong> - 同一地块同一时间提交了不同的读数</li>
                        <li><strong>引用不存在地块</strong> - 引用了 P888 和 P999 等不存在的地块</li>
                        <li><strong>超计划用水</strong> - P001 6月实际用水远超计划</li>
                        <li><strong>倒表</strong> - P002 出现读数回退现象</li>
                        <li><strong>漏采</strong> - P003 两次读数间隔超过25小时</li>
                        <li><strong>重复上报</strong> - P004 同一读数被重复提交</li>
                        <li><strong>未知地块</strong> - P999 未在地块台账中登记</li>
                    </ul>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""", summary=summary)


@app.route('/anomalies')
def anomalies():
    """异常列表"""
    batch_id = request.args.get('batch_id')
    anomaly_type = request.args.get('type')
    is_reviewed = request.args.get('reviewed')
    parcel_id = request.args.get('parcel_id')

    reviewed_param = None
    if is_reviewed == '1':
        reviewed_param = True
    elif is_reviewed == '0':
        reviewed_param = False

    anomaly_list = review_manager.list_anomalies(
        batch_id=batch_id,
        anomaly_type=anomaly_type,
        is_reviewed=reviewed_param,
        parcel_id=parcel_id,
        limit=1000
    )

    batches = batch_manager.list_batches()

    return render_page("""
{% block title %}异常管理 - 农田灌溉用水异常分析系统{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="bi bi-exclamation-triangle"></i> 异常管理</h2>
    <button class="btn btn-success" onclick="location.href='{{ url_for('run_detection') }}'">
        <i class="bi bi-search"></i> 执行检测
    </button>
</div>

<div class="card mb-4">
    <div class="card-body">
        <form class="row g-3" method="get">
            <div class="col-md-3">
                <label class="form-label">批次</label>
                <select class="form-select" name="batch_id">
                    <option value="">全部</option>
                    {% for b in batches %}
                    <option value="{{ b.id }}" {% if request.args.get('batch_id') == b.id|string %}selected{% endif %}>
                        {{ b.batch_no }}
                    </option>
                    {% endfor %}
                </select>
            </div>
            <div class="col-md-3">
                <label class="form-label">异常类型</label>
                <select class="form-select" name="type">
                    <option value="">全部</option>
                    {% for code, name in exception_types.items() %}
                    <option value="{{ code }}" {% if request.args.get('type') == code %}selected{% endif %}>
                        {{ name }}
                    </option>
                    {% endfor %}
                </select>
            </div>
            <div class="col-md-2">
                <label class="form-label">复核状态</label>
                <select class="form-select" name="reviewed">
                    <option value="">全部</option>
                    <option value="1" {% if request.args.get('reviewed') == '1' %}selected{% endif %}>已复核</option>
                    <option value="0" {% if request.args.get('reviewed') == '0' %}selected{% endif %}>待复核</option>
                </select>
            </div>
            <div class="col-md-2">
                <label class="form-label">地块编号</label>
                <input type="text" class="form-control" name="parcel_id" value="{{ request.args.get('parcel_id', '') }}">
            </div>
            <div class="col-md-2 d-flex align-items-end">
                <button type="submit" class="btn btn-primary w-100">
                    <i class="bi bi-filter"></i> 筛选
                </button>
            </div>
        </form>
    </div>
</div>

<div class="card">
    <div class="card-header">
        异常列表 (共 {{ anomalies|length }} 条)
    </div>
    <div class="card-body">
        {% if anomalies %}
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>异常类型</th>
                        <th>地块</th>
                        <th>严重程度</th>
                        <th>规则版本</th>
                        <th>检测时间</th>
                        <th>状态</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    {% for a in anomalies %}
                    <tr>
                        <td><strong>{{ a.id }}</strong></td>
                        <td>
                            <div>{{ a.anomaly_type }}</div>
                            <small class="text-muted"><code>{{ a.anomaly_code }}</code></small>
                        </td>
                        <td>{{ a.parcel_id or '-' }}</td>
                        <td class="severity-{{ a.severity }}">
                            {{ {'high': '高', 'medium': '中', 'low': '低'}[a.severity] }}
                        </td>
                        <td><code>{{ a.rule_version }}</code></td>
                        <td><small>{{ a.detected_at[:19] if a.detected_at else '-' }}</small></td>
                        <td>
                            {% if a.is_reviewed %}
                                {% if a.is_false_positive %}
                                <span class="badge badge-false">误报</span>
                                {% elif a.review_result == 'valid' %}
                                <span class="badge badge-reviewed">有效</span>
                                {% else %}
                                <span class="badge badge-reviewed">待调查</span>
                                {% endif %}
                                {% if a.review_summary and a.review_summary.review_count > 1 %}
                                <span class="badge bg-info ms-1">{{ a.review_summary.review_count }}次</span>
                                {% endif %}
                            {% else %}
                            <span class="badge badge-pending">待复核</span>
                            {% endif %}
                        </td>
                        <td>
                            <button class="btn btn-sm btn-info" onclick="showDetail({{ a.id }})" title="查看详情">
                                <i class="bi bi-eye"></i>
                            </button>
                            {% if not a.is_reviewed %}
                            <button class="btn btn-sm btn-success" onclick="reviewAnomaly({{ a.id }}, 'valid')" title="确认有效">
                                <i class="bi bi-check"></i>
                            </button>
                            <button class="btn btn-sm btn-warning" onclick="reviewAnomaly({{ a.id }}, 'false_positive')" title="标记误报">
                                <i class="bi bi-x"></i>
                            </button>
                            {% else %}
                            <button class="btn btn-sm btn-secondary" onclick="updateStatus({{ a.id }})" title="修改状态">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn btn-sm btn-primary" onclick="appendComment({{ a.id }})" title="追加备注">
                                <i class="bi bi-chat-dots"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger" onclick="undoReview({{ a.id }})" title="撤销最近复核">
                                <i class="bi bi-arrow-undo"></i>
                            </button>
                            {% endif %}
                            {% if not a.is_rolled_back %}
                            <button class="btn btn-sm btn-danger" onclick="rollbackAnomaly({{ a.id }})" title="回滚异常">
                                <i class="bi bi-arrow-counterclockwise"></i>
                            </button>
                            {% endif %}
                        </td>
                    </tr>
                    <tr id="detail-{{ a.id }}" style="display: none;">
                        <td colspan="8">
                            <div class="anomaly-detail">
                                <p><strong>描述：</strong>{{ a.description }}</p>
                                {% if a.extra_data %}
                                <p><strong>扩展数据：</strong></p>
                                <div class="extra-data">{{ a.extra_data|tojson(indent=2) }}</div>
                                {% endif %}

                                {% if a.review_summary %}
                                <div class="card mt-3">
                                    <div class="card-header d-flex justify-content-between align-items-center">
                                        <span><i class="bi bi-clock-history"></i> 复核摘要</span>
                                        <span class="badge bg-secondary">
                                            共 {{ a.review_summary.review_count }} 次操作, 撤销 {{ a.review_summary.undo_count }} 次
                                        </span>
                                    </div>
                                    <div class="card-body">
                                        {% if a.review_summary.last_review_at %}
                                        <p class="mb-1">
                                            <strong>最近复核：</strong>
                                            {{ a.review_summary.last_review_by }} 于
                                            {{ a.review_summary.last_review_at[:19] }}
                                            标记为
                                            {% if a.review_summary.last_review_result == 'valid' %}
                                            <span class="badge badge-reviewed">有效</span>
                                            {% elif a.review_summary.last_review_result == 'false_positive' %}
                                            <span class="badge badge-false">误报</span>
                                            {% elif a.review_summary.last_review_result == 'needs_investigation' %}
                                            <span class="badge bg-info">待调查</span>
                                            {% endif %}
                                        </p>
                                        {% endif %}
                                        {% if a.review_summary.all_comments %}
                                        <p class="mb-0"><strong>历史备注：</strong></p>
                                        <ul class="mb-0">
                                            {% for comment in a.review_summary.all_comments %}
                                            <li>{{ comment }}</li>
                                            {% endfor %}
                                        </ul>
                                        {% endif %}
                                    </div>
                                </div>
                                {% endif %}

                                {% if a.review_history %}
                                <div class="card mt-3">
                                    <div class="card-header">
                                        <i class="bi bi-list-ul"></i> 复核时间线
                                    </div>
                                    <div class="card-body p-0">
                                        <div class="list-group list-group-flush">
                                            {% for h in a.review_history %}
                                            <div class="list-group-item {% if h.is_undone %}list-group-item-light text-muted{% endif %}">
                                                <div class="d-flex w-100 justify-content-between">
                                                    <h6 class="mb-1">
                                                        {% if h.is_undone %}
                                                        <del>
                                                        {% endif %}
                                                        <span class="badge
                                                            {% if h.action_type == 'review' %}bg-success
                                                            {% elif h.action_type == 'update_status' %}bg-info
                                                            {% elif h.action_type == 'append_comment' %}bg-warning text-dark
                                                            {% elif h.action_type == 'undo' %}bg-secondary{% endif %}
                                                            me-2">
                                                            {{ h.action_type_name }}
                                                        </span>
                                                        {% if h.review_result_name %}
                                                        <span class="badge
                                                            {% if h.review_result == 'valid' %}bg-success
                                                            {% elif h.review_result == 'false_positive' %}bg-warning text-dark
                                                            {% elif h.review_result == 'needs_investigation' %}bg-info{% endif %}">
                                                            {{ h.review_result_name }}
                                                        </span>
                                                        {% endif %}
                                                        {% if h.is_undone %}
                                                        </del>
                                                        <span class="badge bg-danger ms-2">已撤销</span>
                                                        {% endif %}
                                                    </h6>
                                                    <small>{{ h.reviewed_at[:19] if h.reviewed_at else '-' }}</small>
                                                </div>
                                                <p class="mb-1">操作人：{{ h.reviewed_by }}</p>
                                                {% if h.review_comment %}
                                                <p class="mb-1">
                                                    <i class="bi bi-chat-text"></i> {{ h.review_comment }}
                                                </p>
                                                {% endif %}
                                                {% if h.is_undone %}
                                                <small class="text-muted">
                                                    于 {{ h.undone_at[:19] if h.undone_at else '-' }} 由 {{ h.undone_by }} 撤销
                                                    {% if h.undo_reason %}，原因：{{ h.undo_reason }}{% endif %}
                                                </small>
                                                {% endif %}
                                            </div>
                                            {% endfor %}
                                        </div>
                                    </div>
                                </div>
                                {% endif %}
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <div class="text-center py-5 text-muted">
            <i class="bi bi-inbox" style="font-size: 48px;"></i>
            <p class="mt-3">暂无异常数据</p>
        </div>
        {% endif %}
    </div>
</div>

<div class="modal fade" id="reviewModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">复核异常</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form method="post" action="{{ url_for('review_anomaly_action') }}">
                <div class="modal-body">
                    <input type="hidden" name="anomaly_id" id="reviewAnomalyId">
                    <input type="hidden" name="result" id="reviewResult">
                    <div class="mb-3">
                        <label class="form-label">复核结果</label>
                        <p id="reviewResultText" class="form-control-plaintext"></p>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">复核备注</label>
                        <textarea class="form-control" name="comment" rows="3"></textarea>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="submit" class="btn btn-primary">确认</button>
                </div>
            </form>
        </div>
    </div>
</div>

<div class="modal fade" id="rollbackModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">回滚异常</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form method="post" action="{{ url_for('rollback_anomaly_action') }}">
                <div class="modal-body">
                    <input type="hidden" name="anomaly_id" id="rollbackAnomalyId">
                    <div class="mb-3">
                        <label class="form-label">回滚原因</label>
                        <textarea class="form-control" name="reason" rows="3" required></textarea>
                    </div>
                    <div class="alert alert-warning">
                        <i class="bi bi-exclamation-triangle"></i> 回滚后该异常将被标记为已回滚，不再出现在统计中。
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="submit" class="btn btn-danger">确认回滚</button>
                </div>
            </form>
        </div>
    </div>
</div>

<div class="modal fade" id="updateStatusModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">修改处置状态</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form method="post" action="{{ url_for('update_review_status_action') }}">
                <div class="modal-body">
                    <input type="hidden" name="anomaly_id" id="updateStatusAnomalyId">
                    <div class="mb-3">
                        <label class="form-label">新状态</label>
                        <select class="form-select" name="new_status" required>
                            <option value="valid">确认有效</option>
                            <option value="false_positive">误报</option>
                            <option value="needs_investigation">待调查</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">修改说明（可选）</label>
                        <textarea class="form-control" name="comment" rows="2"></textarea>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="submit" class="btn btn-primary">确认修改</button>
                </div>
            </form>
        </div>
    </div>
</div>

<div class="modal fade" id="appendCommentModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">追加备注</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form method="post" action="{{ url_for('append_comment_action') }}">
                <div class="modal-body">
                    <input type="hidden" name="anomaly_id" id="appendCommentAnomalyId">
                    <div class="mb-3">
                        <label class="form-label">备注内容</label>
                        <textarea class="form-control" name="comment" rows="3" required></textarea>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="submit" class="btn btn-primary">确认追加</button>
                </div>
            </form>
        </div>
    </div>
</div>

<div class="modal fade" id="undoReviewModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">撤销最近复核</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form method="post" action="{{ url_for('undo_review_action') }}">
                <div class="modal-body">
                    <input type="hidden" name="anomaly_id" id="undoReviewAnomalyId">
                    <div class="mb-3">
                        <label class="form-label">撤销原因（可选）</label>
                        <textarea class="form-control" name="reason" rows="2"></textarea>
                    </div>
                    <div class="alert alert-warning">
                        <i class="bi bi-exclamation-triangle"></i> 撤销最近一次复核操作，状态将回退到上一次操作前的状态。
                        操作历史将被保留，用于审计追溯。
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="submit" class="btn btn-danger">确认撤销</button>
                </div>
            </form>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
function showDetail(id) {
    var row = document.getElementById('detail-' + id);
    if (row.style.display === 'none') {
        row.style.display = 'table-row';
    } else {
        row.style.display = 'none';
    }
}

function reviewAnomaly(id, result) {
    document.getElementById('reviewAnomalyId').value = id;
    document.getElementById('reviewResult').value = result;
    var text = {
        'valid': '确认有效',
        'false_positive': '误报',
        'needs_investigation': '待调查'
    };
    document.getElementById('reviewResultText').textContent = text[result];
    var modal = new bootstrap.Modal(document.getElementById('reviewModal'));
    modal.show();
}

function updateStatus(id) {
    document.getElementById('updateStatusAnomalyId').value = id;
    var modal = new bootstrap.Modal(document.getElementById('updateStatusModal'));
    modal.show();
}

function appendComment(id) {
    document.getElementById('appendCommentAnomalyId').value = id;
    var modal = new bootstrap.Modal(document.getElementById('appendCommentModal'));
    modal.show();
}

function undoReview(id) {
    document.getElementById('undoReviewAnomalyId').value = id;
    var modal = new bootstrap.Modal(document.getElementById('undoReviewModal'));
    modal.show();
}

function rollbackAnomaly(id) {
    document.getElementById('rollbackAnomalyId').value = id;
    var modal = new bootstrap.Modal(document.getElementById('rollbackModal'));
    modal.show();
}
</script>
{% endblock %}
""", anomalies=anomaly_list, batches=batches, exception_types=EXCEPTION_TYPES)


@app.route('/anomalies/review', methods=['POST'])
def review_anomaly_action():
    """复核异常处理"""
    anomaly_id = int(request.form['anomaly_id'])
    result = request.form['result']
    comment = request.form.get('comment', '')

    try:
        review_manager.review_anomaly(anomaly_id, result, comment, 'web')
        result_names = {'valid': '确认有效', 'false_positive': '误报', 'needs_investigation': '待调查'}
        flash(f'异常 #{anomaly_id} 已标记为「{result_names[result]}」', 'success')
    except Exception as e:
        flash(f'复核失败: {str(e)}', 'danger')

    return redirect(url_for('anomalies', **request.args.to_dict()))


@app.route('/anomalies/rollback', methods=['POST'])
def rollback_anomaly_action():
    """回滚异常处理"""
    anomaly_id = int(request.form['anomaly_id'])
    reason = request.form['reason']

    try:
        rollback_manager.rollback_anomaly(anomaly_id, reason, 'web')
        flash(f'异常 #{anomaly_id} 已回滚', 'success')
    except Exception as e:
        flash(f'回滚失败: {str(e)}', 'danger')

    return redirect(url_for('anomalies', **request.args.to_dict()))


@app.route('/anomalies/update-status', methods=['POST'])
def update_review_status_action():
    """修改处置状态"""
    anomaly_id = int(request.form['anomaly_id'])
    new_status = request.form['new_status']
    comment = request.form.get('comment', '')

    try:
        review_manager.update_review_status(anomaly_id, new_status, comment, 'web')
        result_names = {'valid': '确认有效', 'false_positive': '误报', 'needs_investigation': '待调查'}
        flash(f'异常 #{anomaly_id} 状态已修改为「{result_names[new_status]}」', 'success')
    except Exception as e:
        flash(f'修改状态失败: {str(e)}', 'danger')

    return redirect(url_for('anomalies', **request.args.to_dict()))


@app.route('/anomalies/append-comment', methods=['POST'])
def append_comment_action():
    """追加备注"""
    anomaly_id = int(request.form['anomaly_id'])
    comment = request.form['comment']

    try:
        review_manager.append_comment(anomaly_id, comment, 'web')
        flash(f'已为异常 #{anomaly_id} 追加备注', 'success')
    except Exception as e:
        flash(f'追加备注失败: {str(e)}', 'danger')

    return redirect(url_for('anomalies', **request.args.to_dict()))


@app.route('/anomalies/undo-review', methods=['POST'])
def undo_review_action():
    """撤销最近复核"""
    anomaly_id = int(request.form['anomaly_id'])
    reason = request.form.get('reason', '')

    try:
        review_manager.undo_last_review(anomaly_id, reason, 'web')
        flash(f'已撤销异常 #{anomaly_id} 的最近一次复核', 'success')
    except Exception as e:
        flash(f'撤销失败: {str(e)}', 'danger')

    return redirect(url_for('anomalies', **request.args.to_dict()))


@app.route('/api/anomalies/<int:anomaly_id>/review-history')
def api_anomaly_review_history(anomaly_id):
    """API: 获取异常复核历史"""
    try:
        history = review_manager.get_review_history(anomaly_id)
        return jsonify({
            'success': True,
            'anomaly_id': anomaly_id,
            'total': len(history),
            'data': history
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400


@app.route('/api/anomalies/<int:anomaly_id>/review-summary')
def api_anomaly_review_summary(anomaly_id):
    """API: 获取异常复核摘要"""
    try:
        summary = review_manager.get_review_summary(anomaly_id)
        return jsonify({
            'success': True,
            'data': summary
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400


@app.route('/batches')
def batches():
    """批次列表"""
    batch_type = request.args.get('type')
    batch_list = batch_manager.list_batches(batch_type=batch_type, limit=100)

    return render_page("""
{% block title %}批次管理 - 农田灌溉用水异常分析系统{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="bi bi-box-seam"></i> 批次管理</h2>
</div>

<div class="card">
    <div class="card-header">
        批次列表 (共 {{ batches|length }} 个批次)
    </div>
    <div class="card-body">
        {% if batches %}
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>批次号</th>
                        <th>类型</th>
                        <th>描述</th>
                        <th>规则版本</th>
                        <th>异常数</th>
                        <th>创建时间</th>
                        <th>状态</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    {% for b in batches %}
                    <tr class="{% if b.is_rolled_back %}table-light text-muted{% endif %}">
                        <td><strong>{{ b.id }}</strong></td>
                        <td><code>{{ b.batch_no }}</code></td>
                        <td>
                            {{ {'parcel': '地块台账', 'meter': '水表读数', 'plan': '灌溉计划', 'weather': '天气补录'}[b.batch_type] }}
                        </td>
                        <td>{{ b.description or '-' }}</td>
                        <td>{{ b.rule_version }}</td>
                        <td>
                            {% if b.anomaly_count %}
                            <span class="badge bg-danger">{{ b.anomaly_count }}</span>
                            {% else %}
                            -
                            {% endif %}
                        </td>
                        <td><small>{{ b.created_at[:19] if b.created_at else '-' }}</small></td>
                        <td>
                            {% if b.is_rolled_back %}
                            <span class="badge bg-warning">已回滚</span>
                            {% else %}
                            <span class="badge bg-success">正常</span>
                            {% endif %}
                        </td>
                        <td>
                            <a class="btn btn-sm btn-primary" href="{{ url_for('anomalies', batch_id=b.id) }}">
                                <i class="bi bi-list"></i> 异常
                            </a>
                            {% if not b.is_rolled_back %}
                            <button class="btn btn-sm btn-danger" onclick="rollbackBatch({{ b.id }}, '{{ b.batch_no }}')">
                                <i class="bi bi-arrow-counterclockwise"></i> 回滚
                            </button>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <div class="text-center py-5 text-muted">
            <i class="bi bi-inbox" style="font-size: 48px;"></i>
            <p class="mt-3">暂无批次数据</p>
        </div>
        {% endif %}
    </div>
</div>

<div class="modal fade" id="rollbackBatchModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">回滚批次</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form method="post" action="{{ url_for('rollback_batch_action') }}">
                <div class="modal-body">
                    <input type="hidden" name="batch_id" id="rollbackBatchId">
                    <div class="mb-3">
                        <label class="form-label">批次号</label>
                        <p id="rollbackBatchNo" class="form-control-plaintext"></p>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">回滚原因</label>
                        <textarea class="form-control" name="reason" rows="3" required></textarea>
                    </div>
                    <div class="alert alert-warning">
                        <i class="bi bi-exclamation-triangle"></i> 回滚批次将删除该批次导入的所有数据（水表读数、灌溉计划、天气记录），
                        并将相关异常标记为已回滚。此操作不可撤销！
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="submit" class="btn btn-danger">确认回滚</button>
                </div>
            </form>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
function rollbackBatch(id, batchNo) {
    document.getElementById('rollbackBatchId').value = id;
    document.getElementById('rollbackBatchNo').textContent = batchNo;
    var modal = new bootstrap.Modal(document.getElementById('rollbackBatchModal'));
    modal.show();
}
</script>
{% endblock %}
""", batches=batch_list)


@app.route('/batches/rollback', methods=['POST'])
def rollback_batch_action():
    """回滚批次处理"""
    batch_id = int(request.form['batch_id'])
    reason = request.form['reason']

    try:
        result = rollback_manager.rollback_batch(batch_id, reason, 'web')
        flash(f'批次 {result["batch_no"]} 已回滚，回滚异常 {result["anomalies_rolled_back"]} 条', 'success')
    except Exception as e:
        flash(f'回滚失败: {str(e)}', 'danger')

    return redirect(url_for('batches'))


@app.route('/rollbacks')
def rollbacks():
    """回滚记录"""
    rollback_list = rollback_manager.list_rollbacks(limit=100)

    return render_page("""
{% block title %}回滚记录 - 农田灌溉用水异常分析系统{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="bi bi-arrow-counterclockwise"></i> 回滚记录</h2>
</div>

<div class="card">
    <div class="card-header">
        回滚记录 (共 {{ rollbacks|length }} 条)
    </div>
    <div class="card-body">
        {% if rollbacks %}
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>回滚号</th>
                        <th>批次号</th>
                        <th>原因</th>
                        <th>异常数</th>
                        <th>操作人</th>
                        <th>操作时间</th>
                    </tr>
                </thead>
                <tbody>
                    {% for r in rollbacks %}
                    <tr>
                        <td><strong>{{ r.id }}</strong></td>
                        <td><code>{{ r.rollback_no }}</code></td>
                        <td><code>{{ r.batch_no if r.batch_no else '-' }}</code></td>
                        <td>{{ r.reason }}</td>
                        <td>
                            {% if r.anomaly_count %}
                            <span class="badge bg-info">{{ r.anomaly_count }}</span>
                            {% else %}
                            -
                            {% endif %}
                        </td>
                        <td>{{ r.created_by }}</td>
                        <td><small>{{ r.created_at[:19] if r.created_at else '-' }}</small></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <div class="text-center py-5 text-muted">
            <i class="bi bi-inbox" style="font-size: 48px;"></i>
            <p class="mt-3">暂无回滚记录</p>
        </div>
        {% endif %}
    </div>
</div>
{% endblock %}
""", rollbacks=rollback_list)


@app.route('/import')
def import_page():
    """数据导入页面"""
    return render_page("""
{% block title %}数据导入 - 农田灌溉用水异常分析系统{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="bi bi-upload"></i> 数据导入</h2>
    <button class="btn btn-primary" onclick="location.href='{{ url_for('generate_sample') }}'">
        <i class="bi bi-file-earmark-plus"></i> 生成并导入样例数据
    </button>
</div>

<div class="row">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-upload"></i> 上传CSV文件
            </div>
            <div class="card-body">
                <form method="post" action="{{ url_for('upload_file') }}" enctype="multipart/form-data">
                    <div class="mb-3">
                        <label class="form-label">数据类型</label>
                        <select class="form-select" name="data_type" required>
                            <option value="">请选择数据类型</option>
                            <option value="parcel">地块台账</option>
                            <option value="meter">水表读数</option>
                            <option value="plan">灌溉计划</option>
                            <option value="weather">天气补录</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">CSV文件</label>
                        <input type="file" class="form-control" name="file" accept=".csv" required>
                        <small class="text-muted">支持UTF-8或GBK编码的CSV文件</small>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">批次描述</label>
                        <input type="text" class="form-control" name="description">
                    </div>
                    <button type="submit" class="btn btn-primary w-100">
                        <i class="bi bi-upload"></i> 导入数据
                    </button>
                </form>
            </div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-info-circle"></i> 字段映射说明
            </div>
            <div class="card-body">
                <p class="text-muted">系统将自动识别以下字段（不区分大小写）：</p>
                <h6>地块台账</h6>
                <ul class="small">
                    <li><code>地块编号</code> - 地块唯一标识（必填）</li>
                    <li><code>地块名称</code> - 地块名称</li>
                    <li><code>面积(亩)</code> - 地块面积</li>
                    <li><code>作物类型</code> - 种植作物</li>
                    <li><code>位置</code> - 地块位置</li>
                </ul>
                <h6>水表读数</h6>
                <ul class="small">
                    <li><code>地块编号</code> - 地块编号（必填）</li>
                    <li><code>读数日期</code> - 读数日期（必填，支持YYYY-MM-DD等格式）</li>
                    <li><code>读数时间</code> - 读数时间（HH:MM格式）</li>
                    <li><code>水表读数</code> - 读数数值（必填）</li>
                    <li><code>操作员</code> - 操作员姓名</li>
                </ul>
                <h6>灌溉计划</h6>
                <ul class="small">
                    <li><code>地块编号</code> - 地块编号（必填）</li>
                    <li><code>计划日期</code> - 计划日期（必填）</li>
                    <li><code>计划用水量(方)</code> - 计划用水量（必填）</li>
                    <li><code>灌溉类型</code> - 灌溉类型</li>
                </ul>
                <h6>天气补录</h6>
                <ul class="small">
                    <li><code>记录日期</code> - 记录日期（必填）</li>
                    <li><code>降雨量(mm)</code> - 降雨量</li>
                    <li><code>气温(℃)</code> - 气温</li>
                    <li><code>湿度(%)</code> - 湿度</li>
                    <li><code>天气类型</code> - 天气类型</li>
                </ul>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""")


@app.route('/import/upload', methods=['POST'])
def upload_file():
    """处理文件上传"""
    if 'file' not in request.files:
        flash('请选择要上传的文件', 'danger')
        return redirect(url_for('import_page'))

    file = request.files['file']
    data_type = request.form['data_type']
    description = request.form.get('description', '')

    if file.filename == '':
        flash('请选择要上传的文件', 'danger')
        return redirect(url_for('import_page'))

    if not allowed_file(file.filename):
        flash('只支持CSV格式的文件', 'danger')
        return redirect(url_for('import_page'))

    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        importer = DataImporter()
        type_names = {
            'parcel': '地块台账',
            'meter': '水表读数',
            'plan': '灌溉计划',
            'weather': '天气补录',
        }

        if data_type == 'parcel':
            result = importer.import_parcels(filepath, description)
        elif data_type == 'meter':
            result = importer.import_meters(filepath, description)
        elif data_type == 'plan':
            result = importer.import_plans(filepath, description)
        elif data_type == 'weather':
            result = importer.import_weather(filepath, description)
        else:
            raise ValueError('无效的数据类型')

        msg = f'{type_names[data_type]}导入成功：成功 {result["success_count"]}/{result["total_count"]} 条'
        if result['error_count'] > 0:
            msg += f'，错误 {result["error_count"]} 条'
            flash(msg, 'warning')
            for err in result['errors'][:5]:
                flash(f'  - {err}', 'warning')
        else:
            flash(msg, 'success')

        flash(f'批次号: {result["batch_no"]}', 'info')

    except Exception as e:
        flash(f'导入失败: {str(e)}', 'danger')

    return redirect(url_for('import_page'))


@app.route('/sample/generate')
def generate_sample():
    """生成并导入样例数据"""
    try:
        files = sample_data_generator.generate_all()
        importer = DataImporter()

        importer.import_parcels(files['parcels'], '样例数据')
        importer.import_plans(files['plans'], '样例数据')
        importer.import_weather(files['weather'], '样例数据')
        result = importer.import_meters(files['meters'], '样例数据')

        engine = RuleEngine()
        engine.detect_all()

        flash('样例数据已生成并导入，异常检测已完成', 'success')
        if result['errors']:
            flash(f'导入时有 {len(result["errors"])} 条错误（这些错误会被检测为异常）', 'warning')

    except Exception as e:
        flash(f'生成样例数据失败: {str(e)}', 'danger')

    return redirect(url_for('dashboard'))


@app.route('/detect/run')
def run_detection():
    """执行异常检测"""
    try:
        engine = RuleEngine()
        anomalies = engine.detect_all()
        report_generator.generate_summary(use_cache=False)
        flash(f'异常检测完成，新发现 {len(anomalies)} 条异常', 'success')
    except Exception as e:
        flash(f'检测失败: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('dashboard'))


@app.route('/reports')
def reports():
    """报告中心"""
    summary = report_generator.generate_summary(use_cache=False)

    return render_page("""
{% block title %}报告中心 - 农田灌溉用水异常分析系统{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="bi bi-file-earmark-bar-graph"></i> 报告中心</h2>
</div>

<div class="row">
    <div class="col-md-4">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-file-earmark-code"></i> HTML报告
            </div>
            <div class="card-body">
                <p>生成包含汇总统计、图表和详细信息的HTML格式报告，可在浏览器中查看和打印。</p>
                <form method="get" action="{{ url_for('download_report', format='html') }}">
                    <button type="submit" class="btn btn-primary w-100">
                        <i class="bi bi-download"></i> 导出HTML报告
                    </button>
                </form>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-file-earmark-spreadsheet"></i> CSV报告
            </div>
            <div class="card-body">
                <p>生成CSV格式报告，可导入Excel等工具进行进一步分析和处理。</p>
                <form method="get" action="{{ url_for('download_report', format='csv') }}">
                    <button type="submit" class="btn btn-success w-100">
                        <i class="bi bi-download"></i> 导出CSV报告
                    </button>
                </form>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-gear"></i> 报告选项
            </div>
            <div class="card-body">
                <form method="get" action="{{ url_for('download_report') }}">
                    <div class="mb-2">
                        <label class="form-label small">格式</label>
                        <select class="form-select form-select-sm" name="format">
                            <option value="html">HTML</option>
                            <option value="csv">CSV</option>
                        </select>
                    </div>
                    <div class="mb-2">
                        <label class="form-label small">异常类型</label>
                        <select class="form-select form-select-sm" name="type">
                            <option value="">全部</option>
                            {% for code, name in exception_types.items() %}
                            <option value="{{ code }}">{{ name }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="mb-2">
                        <label class="form-label small">地块编号</label>
                        <input type="text" class="form-control form-control-sm" name="parcel_id">
                    </div>
                    <button type="submit" class="btn btn-info btn-sm w-100">
                        <i class="bi bi-filter"></i> 筛选导出
                    </button>
                </form>
            </div>
        </div>
    </div>
</div>

<div class="card mt-4">
    <div class="card-header">
        <i class="bi bi-bar-chart-line"></i> 当前统计
    </div>
    <div class="card-body">
        <div class="row">
            <div class="col-md-3 text-center">
                <div class="stat-value">{{ summary.summary.total_anomalies }}</div>
                <div class="stat-label">异常总数</div>
            </div>
            <div class="col-md-3 text-center">
                <div class="stat-value text-success">{{ summary.summary.review_status.reviewed }}</div>
                <div class="stat-label">已复核</div>
            </div>
            <div class="col-md-3 text-center">
                <div class="stat-value text-warning">{{ summary.summary.review_status.not_reviewed }}</div>
                <div class="stat-label">待复核</div>
            </div>
            <div class="col-md-3 text-center">
                <div class="stat-value text-info">{{ summary.summary.review_status.false_positive }}</div>
                <div class="stat-label">误报数</div>
            </div>
        </div>
    </div>
</div>

<div class="card mt-4">
    <div class="card-header">
        <i class="bi bi-list-check"></i> 样例数据预期异常数量
    </div>
    <div class="card-body">
        <table class="table table-sm">
            <thead>
                <tr>
                    <th>异常代码</th>
                    <th>异常类型</th>
                    <th>预期数量</th>
                    <th>当前数量</th>
                    <th>说明</th>
                </tr>
            </thead>
            <tbody>
                {% for code, (name, expected, desc) in expected_anomalies.items() %}
                <tr>
                    <td><code>{{ code }}</code></td>
                    <td>{{ name }}</td>
                    <td><span class="badge bg-secondary">{{ expected }}</span></td>
                    <td>
                        {% set current = summary.by_type | selectattr('code', 'equalto', code) | list %}
                        {% if current %}
                        <span class="badge bg-danger">{{ current[0].count }}</span>
                        {% else %}
                        <span class="badge bg-secondary">0</span>
                        {% endif %}
                    </td>
                    <td><small class="text-muted">{{ desc }}</small></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
""", summary=summary, exception_types=EXCEPTION_TYPES,
       expected_anomalies=report_generator.EXPECTED_ANOMALIES)


@app.route('/reports/download')
def download_report():
    """下载报告"""
    report_format = request.args.get('format', 'html')
    batch_id = request.args.get('batch_id')
    anomaly_type = request.args.get('type')
    parcel_id = request.args.get('parcel_id')

    try:
        if report_format == 'html':
            path = report_generator.export_html(
                batch_id=batch_id,
                anomaly_type=anomaly_type,
                parcel_id=parcel_id
            )
            mimetype = 'text/html'
        else:
            path = report_generator.export_csv(
                batch_id=batch_id,
                anomaly_type=anomaly_type,
                parcel_id=parcel_id
            )
            mimetype = 'text/csv'

        return send_file(path, as_attachment=True, download_name=os.path.basename(path), mimetype=mimetype)

    except Exception as e:
        flash(f'生成报告失败: {str(e)}', 'danger')
        return redirect(url_for('reports'))


@app.route('/api/anomalies')
def api_anomalies():
    """API: 获取异常列表"""
    batch_id = request.args.get('batch_id')
    anomaly_type = request.args.get('type')

    anomalies = review_manager.list_anomalies(
        batch_id=batch_id,
        anomaly_type=anomaly_type,
        limit=1000
    )

    return jsonify({
        'success': True,
        'total': len(anomalies),
        'data': anomalies
    })


@app.route('/api/summary')
def api_summary():
    """API: 获取统计汇总"""
    summary = report_generator.generate_summary(use_cache=False)
    return jsonify({
        'success': True,
        'data': summary
    })


@app.route('/sandboxes')
def sandboxes():
    """沙盒列表页"""
    sandboxes = sandbox_manager.list_sandboxes()
    return render_page("""
{% block title %}沙盒管理 - 农田灌溉用水异常分析系统{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="bi bi-flask"></i> 沙盒管理</h2>
    <div>
        <button class="btn btn-success me-2" onclick="showCreateModal()">
            <i class="bi bi-plus-circle"></i> 新建沙盒
        </button>
        <button class="btn btn-outline-primary me-2" onclick="showImportModal()">
            <i class="bi bi-upload"></i> 导入沙盒包
        </button>
    </div>
</div>

<div class="card">
    <div class="card-body">
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>状态</th>
                        <th>名称</th>
                        <th>描述</th>
                        <th>样例</th>
                        <th>规则</th>
                        <th>试跑</th>
                        <th>创建人</th>
                        <th>创建时间</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    {% for s in sandboxes %}
                    <tr>
                        <td>{{ s.id }}</td>
                        <td>
                            {% set status_map = {'draft': ('草稿', 'bg-secondary'), 'testing': ('测试中', 'bg-info'), 'approved': ('已审批', 'bg-primary'), 'applied': ('已应用', 'bg-success'), 'archived': ('已归档', 'bg-warning'), 'rolled_back': ('已回滚', 'bg-danger')} %}
                            {% set status = status_map.get(s.status, (s.status, 'bg-secondary')) %}
                            <span class="badge {{ status[1] }}">{{ status[0] }}</span>
                        </td>
                        <td><strong>{{ s.name }}</strong></td>
                        <td>{{ s.description[:30] if s.description else '-' }}</td>
                        <td><span class="badge bg-info">{{ s.get('sample_count', 0) }}</span></td>
                        <td><span class="badge bg-primary">{{ s.get('rule_count', 0) }}</span></td>
                        <td><span class="badge bg-secondary">{{ s.get('trial_count', 0) }}</span></td>
                        <td>{{ s.created_by }}</td>
                        <td><small class="text-muted">{{ s.created_at[:19] if s.created_at else '' }}</small></td>
                        <td>
                            <div class="btn-group btn-group-sm">
                                <a href="{{ url_for('sandbox_detail', sandbox_id=s.id) }}" class="btn btn-outline-primary" title="查看详情">
                                    <i class="bi bi-eye"></i>
                                </a>
                                <a href="{{ url_for('sandbox_export', sandbox_id=s.id) }}" class="btn btn-outline-success" title="导出">
                                    <i class="bi bi-download"></i>
                                </a>
                                <button class="btn btn-outline-danger" onclick="confirmDelete({{ s.id }}, '{{ s.name }}')" title="删除">
                                    <i class="bi bi-trash"></i>
                                </button>
                            </div>
                        </td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="10" class="text-center text-muted py-4">
                            <i class="bi bi-inbox" style="font-size: 48px;"></i>
                            <p class="mt-2">暂无沙盒，点击"新建沙盒"创建第一个沙盒</p>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>

<div class="modal fade" id="createModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <form method="POST" action="{{ url_for('sandbox_create') }}">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="bi bi-plus-circle"></i> 新建沙盒</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">沙盒名称 <span class="text-danger">*</span></label>
                        <input type="text" class="form-control" name="name" required placeholder="例如：6月水表读数修正">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">描述</label>
                        <textarea class="form-control" name="description" rows="3" placeholder="描述这个沙盒的用途..."></textarea>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">创建人</label>
                        <input type="text" class="form-control" name="by" value="web">
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="submit" class="btn btn-primary">创建</button>
                </div>
            </form>
        </div>
    </div>
</div>

<div class="modal fade" id="importModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <form method="POST" action="{{ url_for('sandbox_import_package') }}" enctype="multipart/form-data">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="bi bi-upload"></i> 导入沙盒包</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">选择沙盒包文件 <span class="text-danger">*</span></label>
                        <input type="file" class="form-control" name="file" accept=".zip" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">重命名（可选）</label>
                        <input type="text" class="form-control" name="rename" placeholder="留空则使用原名称">
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="submit" class="btn btn-primary">导入</button>
                </div>
            </form>
        </div>
    </div>
</div>

<script>
function showCreateModal() {
    new bootstrap.Modal(document.getElementById('createModal')).show();
}
function showImportModal() {
    new bootstrap.Modal(document.getElementById('importModal')).show();
}
function confirmDelete(id, name) {
    if (confirm('确定要删除沙盒 "' + name + '" 吗？此操作不可撤销！')) {
        location.href = "{{ url_for('sandbox_delete', sandbox_id=0) }}".replace('/0', '/' + id);
    }
}
</script>
{% endblock %}
""", sandboxes=sandboxes)


@app.route('/sandboxes/create', methods=['POST'])
def sandbox_create():
    """创建沙盒"""
    try:
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        by = request.form.get('by', 'web')

        if not name:
            flash('沙盒名称不能为空', 'danger')
            return redirect(url_for('sandboxes'))

        sandbox = sandbox_manager.create_sandbox(
            name=name,
            description=description,
            created_by=by
        )

        flash(f'沙盒 "{name}" 创建成功', 'success')
        return redirect(url_for('sandbox_detail', sandbox_id=sandbox['id']))

    except Exception as e:
        flash(f'创建失败: {str(e)}', 'danger')
        return redirect(url_for('sandboxes'))


@app.route('/sandboxes/<sandbox_id>/delete')
def sandbox_delete(sandbox_id):
    """删除沙盒"""
    try:
        sandbox = sandbox_manager.get_sandbox(sandbox_id)
        if not sandbox:
            flash('沙盒不存在', 'danger')
            return redirect(url_for('sandboxes'))

        sandbox_manager.delete_sandbox(sandbox_id, operator='web')
        flash(f'沙盒 "{sandbox["name"]}" 已删除', 'success')

    except Exception as e:
        flash(f'删除失败: {str(e)}', 'danger')

    return redirect(url_for('sandboxes'))


@app.route('/sandboxes/<sandbox_id>')
def sandbox_detail(sandbox_id):
    """沙盒详情页"""
    sandbox = sandbox_manager.get_sandbox(sandbox_id, include_details=True)
    if not sandbox:
        flash('沙盒不存在', 'danger')
        return redirect(url_for('sandboxes'))

    samples = sandbox_manager.list_samples(sandbox_id)
    rules = sandbox_manager.list_rules(sandbox_id)
    trials = sandbox_manager.list_trials(sandbox_id)

    return render_page("""
{% block title %}{{ sandbox.name }} - 沙盒详情{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <div>
        <nav aria-label="breadcrumb">
            <ol class="breadcrumb mb-1">
                <li class="breadcrumb-item"><a href="{{ url_for('sandboxes') }}">沙盒管理</a></li>
                <li class="breadcrumb-item active" aria-current="page">{{ sandbox.name }}</li>
            </ol>
        </nav>
        <h2 class="mb-0"><i class="bi bi-flask"></i> {{ sandbox.name }}</h2>
    </div>
    <div>
        <button class="btn btn-outline-secondary me-2" onclick="location.href='{{ url_for('sandboxes') }}'">
            <i class="bi bi-arrow-left"></i> 返回列表
        </button>
        <button class="btn btn-primary me-2" onclick="showSampleModal()">
            <i class="bi bi-upload"></i> 导入样例
        </button>
        <button class="btn btn-success me-2" onclick="showRuleModal()">
            <i class="bi bi-plus-circle"></i> 添加规则
        </button>
        {% if rules and samples %}
        <button class="btn btn-warning me-2" onclick="runTrial()">
            <i class="bi bi-play-circle"></i> 执行试跑
        </button>
        {% endif %}
        <button class="btn btn-info" onclick="location.href='{{ url_for('sandbox_export', sandbox_id=sandbox.id) }}'">
            <i class="bi bi-download"></i> 导出
        </button>
    </div>
</div>

<div class="row mb-4">
    <div class="col-md-3">
        <div class="card stat-card">
            <div class="stat-value text-info">{{ sandbox.get('sample_count', 0) }}</div>
            <div class="stat-label">样例数据</div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card stat-card">
            <div class="stat-value text-primary">{{ sandbox.get('rule_count', 0) }}</div>
            <div class="stat-label">激活规则</div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card stat-card">
            <div class="stat-value text-secondary">{{ sandbox.get('trial_count', 0) }}</div>
            <div class="stat-label">试跑次数</div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card stat-card">
            <div class="stat-value text-muted">{{ sandbox.get('log_count', 0) }}</div>
            <div class="stat-label">操作日志</div>
        </div>
    </div>
</div>

<div class="card mb-4">
    <div class="card-body">
        <div class="row">
            <div class="col-md-6">
                <strong>沙盒编号：</strong> {{ sandbox.sandbox_no }}<br>
                <strong>状态：</strong>
                {% set status_map = {'draft': ('草稿', 'bg-secondary'), 'testing': ('测试中', 'bg-info'), 'approved': ('已审批', 'bg-primary'), 'applied': ('已应用', 'bg-success'), 'archived': ('已归档', 'bg-warning'), 'rolled_back': ('已回滚', 'bg-danger')} %}
                {% set status = status_map.get(sandbox.status, (sandbox.status, 'bg-secondary')) %}
                <span class="badge {{ status[1] }}">{{ status[0] }}</span><br>
                <strong>创建人：</strong> {{ sandbox.created_by }}<br>
                <strong>创建时间：</strong> {{ sandbox.created_at[:19] if sandbox.created_at else '' }}
            </div>
            <div class="col-md-6">
                <strong>描述：</strong> {{ sandbox.description or '无' }}<br>
                {% if sandbox.get('last_trial') %}
                <strong>最近试跑：</strong> 影响 {{ sandbox.last_trial.affected_rows }} 行，{{ sandbox.last_trial.total_rows }} 总行
                {% endif %}
            </div>
        </div>
    </div>
</div>

<ul class="nav nav-tabs mb-4" id="sandboxTabs" role="tablist">
    <li class="nav-item">
        <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#samples-tab">
            <i class="bi bi-file-earmark-spreadsheet"></i> 样例数据 ({{ samples|length }})
        </button>
    </li>
    <li class="nav-item">
        <button class="nav-link" data-bs-toggle="tab" data-bs-target="#rules-tab">
            <i class="bi bi-sliders"></i> 修正规则 ({{ rules|length }})
        </button>
    </li>
    <li class="nav-item">
        <button class="nav-link" data-bs-toggle="tab" data-bs-target="#trials-tab">
            <i class="bi bi-bar-chart"></i> 试跑记录 ({{ trials|length }})
        </button>
    </li>
</ul>

<div class="tab-content">
    <div class="tab-pane fade show active" id="samples-tab">
        <div class="card">
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>类型</th>
                                <th>名称</th>
                                <th>行数</th>
                                <th>创建人</th>
                                <th>创建时间</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for s in samples %}
                            <tr>
                                <td>{{ s.id }}</td>
                                <td>
                                    {% set type_map = {'parcel': '地块台账', 'meter': '水表读数', 'plan': '灌溉计划', 'weather': '天气补录'} %}
                                    {{ type_map.get(s.source_type, s.source_type) }}
                                </td>
                                <td>{{ s.sample_name }}</td>
                                <td><span class="badge bg-info">{{ s.row_count }}</span></td>
                                <td>{{ s.created_by }}</td>
                                <td><small class="text-muted">{{ s.created_at[:19] if s.created_at else '' }}</small></td>
                                <td>
                                    <button class="btn btn-sm btn-outline-primary" onclick="viewSample({{ s.id }})">
                                        <i class="bi bi-eye"></i> 查看
                                    </button>
                                </td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="7" class="text-center text-muted py-4">
                                    暂无样例数据，点击"导入样例"上传CSV或JSON文件
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <div class="tab-pane fade" id="rules-tab">
        <div class="card">
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>优先级</th>
                                <th>类型</th>
                                <th>名称</th>
                                <th>目标字段</th>
                                <th>条件</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for r in rules %}
                            <tr>
                                <td>{{ r.id }}</td>
                                <td><span class="badge bg-secondary">{{ r.priority }}</span></td>
                                <td>
                                    {% set type_map = {'field_mapping': ('字段映射', 'info'), 'missing_fill': ('缺失值填补', 'success'), 'outlier_replace': ('异常值改写', 'warning'), 'custom': ('自定义', 'primary')} %}
                                    {% set t = type_map.get(r.rule_type, (r.rule_type, 'secondary')) %}
                                    <span class="badge bg-{{ t[1] }}">{{ t[0] }}</span>
                                </td>
                                <td><strong>{{ r.rule_name }}</strong></td>
                                <td>{{ r.target_field or '-' }}</td>
                                <td><code class="small">{{ r.condition[:30] if r.condition else '-' }}</code></td>
                                <td>
                                    <div class="btn-group btn-group-sm">
                                        <button class="btn btn-outline-primary" onclick="editRule({{ r.id }})">
                                            <i class="bi bi-pencil"></i>
                                        </button>
                                        <button class="btn btn-outline-danger" onclick="deleteRule({{ r.id }})">
                                            <i class="bi bi-trash"></i>
                                        </button>
                                    </div>
                                </td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="7" class="text-center text-muted py-4">
                                    暂无规则，点击"添加规则"创建第一条规则
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <div class="tab-pane fade" id="trials-tab">
        <div class="card">
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>状态</th>
                                <th>总行数</th>
                                <th>影响行数</th>
                                <th>未变化</th>
                                <th>错误</th>
                                <th>执行人</th>
                                <th>执行时间</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for t in trials %}
                            <tr>
                                <td>{{ t.id }}</td>
                                <td>
                                    {% set status_map = {'completed': ('已完成', 'bg-success'), 'failed': ('失败', 'bg-danger'), 'running': ('运行中', 'bg-info')} %}
                                    {% set s = status_map.get(t.status, (t.status, 'bg-secondary')) %}
                                    <span class="badge {{ s[1] }}">{{ s[0] }}</span>
                                </td>
                                <td>{{ t.total_rows }}</td>
                                <td><strong class="text-warning">{{ t.affected_rows }}</strong></td>
                                <td>{{ t.unchanged_rows }}</td>
                                <td>{% if t.error_count %}<span class="text-danger">{{ t.error_count }}</span>{% else %}0{% endif %}</td>
                                <td>{{ t.executed_by }}</td>
                                <td><small class="text-muted">{{ t.executed_at[:19] if t.executed_at else '' }}</small></td>
                                <td>
                                    <div class="btn-group btn-group-sm">
                                        <a href="{{ url_for('trial_results', trial_id=t.id) }}" class="btn btn-outline-primary">
                                            <i class="bi bi-eye"></i> 查看差异
                                        </a>
                                        {% if t.status == 'completed' and t.affected_rows > 0 %}
                                        <button class="btn btn-outline-success" onclick="promoteTrial({{ t.id }})">
                                            <i class="bi bi-rocket-takeoff"></i> 提升
                                        </button>
                                        {% endif %}
                                    </div>
                                </td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="9" class="text-center text-muted py-4">
                                    暂无试跑记录，请先导入样例和添加规则后执行试跑
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>

<div class="modal fade" id="sampleModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <form method="POST" action="{{ url_for('sandbox_import_sample', sandbox_id=sandbox.id) }}" enctype="multipart/form-data">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="bi bi-upload"></i> 导入样例数据</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">数据类型 <span class="text-danger">*</span></label>
                        <select class="form-select" name="source_type" required>
                            <option value="meter">水表读数</option>
                            <option value="parcel">地块台账</option>
                            <option value="plan">灌溉计划</option>
                            <option value="weather">天气补录</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">选择文件 <span class="text-danger">*</span></label>
                        <input type="file" class="form-control" name="file" accept=".csv,.json" required>
                        <div class="form-text">支持 CSV 和 JSON 格式</div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">样例名称（可选）</label>
                        <input type="text" class="form-control" name="sample_name" placeholder="留空则使用文件名">
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="submit" class="btn btn-primary">导入</button>
                </div>
            </form>
        </div>
    </div>
</div>

<div class="modal fade" id="ruleModal" tabindex="-1">
    <div class="modal-dialog modal-lg">
        <div class="modal-content">
            <form method="POST" action="{{ url_for('sandbox_add_rule', sandbox_id=sandbox.id) }}">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="bi bi-plus-circle"></i> 添加修正规则</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="row">
                        <div class="col-md-6">
                            <div class="mb-3">
                                <label class="form-label">规则类型 <span class="text-danger">*</span></label>
                                <select class="form-select" name="rule_type" id="ruleType" required onchange="updateRuleForm()">
                                    <option value="field_mapping">字段映射</option>
                                    <option value="missing_fill">缺失值填补</option>
                                    <option value="outlier_replace">异常值改写</option>
                                    <option value="custom">自定义规则</option>
                                </select>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="mb-3">
                                <label class="form-label">优先级</label>
                                <input type="number" class="form-control" name="priority" value="0">
                                <div class="form-text">数字越大越先执行</div>
                            </div>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">规则名称 <span class="text-danger">*</span></label>
                        <input type="text" class="form-control" name="rule_name" required placeholder="例如：修正缺失的操作员">
                    </div>
                    <div class="row">
                        <div class="col-md-6">
                            <div class="mb-3" id="sourceFieldDiv">
                                <label class="form-label">源字段名</label>
                                <input type="text" class="form-control" name="source_field" placeholder="例如：操作员姓名">
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="mb-3">
                                <label class="form-label">目标字段名 <span class="text-danger">*</span></label>
                                <input type="text" class="form-control" name="target_field" required placeholder="例如：operator">
                            </div>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">条件表达式</label>
                        <input type="text" class="form-control" name="condition" placeholder="例如：value > 1000 或 pd.isna(value)">
                        <div class="form-text">可用变量：row（当前行数据字典）、value（目标字段值）、pd（pandas模块）</div>
                    </div>
                    <div class="mb-3" id="replacementDiv">
                        <label class="form-label">替换值/表达式</label>
                        <input type="text" class="form-control" name="replacement" placeholder="例如：100 或 row['其他字段']">
                    </div>
                    <div class="mb-3" id="fillValueDiv">
                        <label class="form-label">填补值</label>
                        <input type="text" class="form-control" name="fill_value" placeholder="例如：未知操作员">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">映射数据 (JSON)</label>
                        <input type="text" class="form-control" name="mapping" placeholder='例如：{"旧值1": "新值1", "旧值2": "新值2"}'>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="submit" class="btn btn-primary">添加</button>
                </div>
            </form>
        </div>
    </div>
</div>

<script>
function showSampleModal() {
    new bootstrap.Modal(document.getElementById('sampleModal')).show();
}
function showRuleModal() {
    new bootstrap.Modal(document.getElementById('ruleModal')).show();
}
function updateRuleForm() {
    const type = document.getElementById('ruleType').value;
    document.getElementById('sourceFieldDiv').style.display = type === 'field_mapping' ? 'block' : 'none';
    document.getElementById('replacementDiv').style.display = (type === 'outlier_replace' || type === 'custom') ? 'block' : 'none';
    document.getElementById('fillValueDiv').style.display = type === 'missing_fill' ? 'block' : 'none';
}
function runTrial() {
    if (confirm('确定要执行试跑吗？这将应用所有规则到样例数据上。')) {
        location.href = "{{ url_for('sandbox_run_trial', sandbox_id=sandbox.id) }}";
    }
}
function promoteTrial(trialId) {
    location.href = "{{ url_for('promote_confirm', trial_id=0) }}".replace('/0', '/' + trialId);
}
function editRule(ruleId) {
    alert('规则编辑功能请使用CLI命令：python main.py sandbox update-rule ' + ruleId);
}
function deleteRule(ruleId) {
    if (confirm('确定要删除此规则吗？')) {
        location.href = "{{ url_for('sandbox_delete_rule', sandbox_id=sandbox.id, rule_id=0) }}".replace('/0', '/' + ruleId);
    }
}
function viewSample(sampleId) {
    window.open("{{ url_for('view_sample', sample_id=0) }}".replace('/0', '/' + sampleId), '_blank');
}
updateRuleForm();
</script>
{% endblock %}
""", sandbox=sandbox, samples=samples, rules=rules, trials=trials)


@app.route('/sandboxes/<sandbox_id>/import-sample', methods=['POST'])
def sandbox_import_sample(sandbox_id):
    """导入样例数据"""
    try:
        if 'file' not in request.files:
            flash('请选择文件', 'danger')
            return redirect(url_for('sandbox_detail', sandbox_id=sandbox_id))

        file = request.files['file']
        if file.filename == '':
            flash('请选择文件', 'danger')
            return redirect(url_for('sandbox_detail', sandbox_id=sandbox_id))

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            source_type = request.form.get('source_type', 'meter')
            sample_name = request.form.get('sample_name') or filename

            sandbox_manager.import_sample(
                sandbox_id_or_no=sandbox_id,
                file_path=filepath,
                source_type=source_type,
                sample_name=sample_name,
                operator='web'
            )

            os.remove(filepath)
            flash('样例数据导入成功', 'success')

    except Exception as e:
        flash(f'导入失败: {str(e)}', 'danger')

    return redirect(url_for('sandbox_detail', sandbox_id=sandbox_id))


@app.route('/sandboxes/<sandbox_id>/add-rule', methods=['POST'])
def sandbox_add_rule(sandbox_id):
    """添加规则"""
    try:
        rule_type = request.form.get('rule_type', '')
        rule_name = request.form.get('rule_name', '').strip()
        source_field = request.form.get('source_field') or None
        target_field = request.form.get('target_field') or None
        condition = request.form.get('condition') or None
        replacement = request.form.get('replacement') or None
        fill_value = request.form.get('fill_value') or None
        priority = int(request.form.get('priority', '0'))
        mapping_str = request.form.get('mapping') or None

        mapping_data = None
        if mapping_str:
            import json
            mapping_data = json.loads(mapping_str)

        if not rule_name:
            flash('规则名称不能为空', 'danger')
            return redirect(url_for('sandbox_detail', sandbox_id=sandbox_id))

        sandbox_manager.add_rule(
            sandbox_id_or_no=sandbox_id,
            rule_type=rule_type,
            rule_name=rule_name,
            source_field=source_field,
            target_field=target_field,
            condition=condition,
            replacement=replacement,
            fill_value=fill_value,
            mapping_data=mapping_data,
            priority=priority,
            operator='web'
        )

        flash('规则添加成功', 'success')

    except Exception as e:
        flash(f'添加失败: {str(e)}', 'danger')

    return redirect(url_for('sandbox_detail', sandbox_id=sandbox_id))


@app.route('/sandboxes/<sandbox_id>/delete-rule/<rule_id>')
def sandbox_delete_rule(sandbox_id, rule_id):
    """删除规则"""
    try:
        sandbox_manager.delete_rule(int(rule_id), operator='web')
        flash('规则已删除', 'success')
    except Exception as e:
        flash(f'删除失败: {str(e)}', 'danger')

    return redirect(url_for('sandbox_detail', sandbox_id=sandbox_id))


@app.route('/sandboxes/<sandbox_id>/run-trial')
def sandbox_run_trial(sandbox_id):
    """执行试跑"""
    try:
        trial = sandbox_manager.run_trial(sandbox_id, operator='web')
        flash(f'试跑完成，影响 {trial["affected_rows"]} 行', 'success')
        return redirect(url_for('trial_results', trial_id=trial['id']))
    except Exception as e:
        flash(f'试跑失败: {str(e)}', 'danger')
        return redirect(url_for('sandbox_detail', sandbox_id=sandbox_id))


@app.route('/trials/<trial_id>')
def trial_results(trial_id):
    """试跑结果详情页"""
    trial = sandbox_manager.get_trial(trial_id, include_results=True, limit_results=100)
    if not trial:
        flash('试跑记录不存在', 'danger')
        return redirect(url_for('sandboxes'))

    sandbox = sandbox_manager.get_sandbox(trial['sandbox_id'])

    return render_page("""
{% block title %}试跑结果 - {{ sandbox.name }}{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <div>
        <nav aria-label="breadcrumb">
            <ol class="breadcrumb mb-1">
                <li class="breadcrumb-item"><a href="{{ url_for('sandboxes') }}">沙盒管理</a></li>
                <li class="breadcrumb-item"><a href="{{ url_for('sandbox_detail', sandbox_id=sandbox.id) }}">{{ sandbox.name }}</a></li>
                <li class="breadcrumb-item active" aria-current="page">试跑 #{{ trial.id }}</li>
            </ol>
        </nav>
        <h2 class="mb-0"><i class="bi bi-bar-chart"></i> 试跑结果</h2>
    </div>
    <div>
        <button class="btn btn-outline-secondary me-2" onclick="location.href='{{ url_for('sandbox_detail', sandbox_id=sandbox.id) }}'">
            <i class="bi bi-arrow-left"></i> 返回沙盒
        </button>
        {% if trial.status == 'completed' and trial.affected_rows > 0 %}
        <button class="btn btn-success" onclick="location.href='{{ url_for('promote_confirm', trial_id=trial.id) }}'">
            <i class="bi bi-rocket-takeoff"></i> 提升为正式修正
        </button>
        {% endif %}
    </div>
</div>

<div class="row mb-4">
    <div class="col-md-2">
        <div class="card stat-card">
            <div class="stat-value">{{ trial.total_rows }}</div>
            <div class="stat-label">总行数</div>
        </div>
    </div>
    <div class="col-md-2">
        <div class="card stat-card">
            <div class="stat-value text-warning">{{ trial.affected_rows }}</div>
            <div class="stat-label">影响行数</div>
        </div>
    </div>
    <div class="col-md-2">
        <div class="card stat-card">
            <div class="stat-value text-success">{{ trial.unchanged_rows }}</div>
            <div class="stat-label">未变化</div>
        </div>
    </div>
    <div class="col-md-2">
        <div class="card stat-card">
            <div class="stat-value text-danger">{{ trial.error_count }}</div>
            <div class="stat-label">错误</div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card">
            <div class="card-body">
                <strong>状态：</strong>
                {% set status_map = {'completed': ('已完成', 'bg-success'), 'failed': ('失败', 'bg-danger'), 'running': ('运行中', 'bg-info')} %}
                {% set s = status_map.get(trial.status, (trial.status, 'bg-secondary')) %}
                <span class="badge {{ s[1] }}">{{ s[0] }}</span><br>
                <strong>执行人：</strong> {{ trial.executed_by }}<br>
                <strong>执行时间：</strong> {{ trial.executed_at[:19] if trial.executed_at else '' }}
            </div>
        </div>
    </div>
</div>

{% if trial.get('by_change_type') %}
<div class="card mb-4">
    <div class="card-header">
        <i class="bi bi-pie-chart"></i> 变更类型统计
    </div>
    <div class="card-body">
        <div class="row">
            {% for ct, count in trial.by_change_type.items() %}
            {% set ct_map = {'modified': ('修改', 'warning'), 'added': ('新增', 'success'), 'deleted': ('删除', 'danger'), 'error': ('错误', 'danger')} %}
            {% set c = ct_map.get(ct, (ct, 'secondary')) %}
            <div class="col-md-3">
                <div class="d-flex justify-content-between align-items-center p-3 border rounded">
                    <span class="text-{{ c[1] }}"><i class="bi bi-pencil-square"></i> {{ c[0] }}</span>
                    <span class="badge bg-{{ c[1] }} fs-6">{{ count }}</span>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
</div>
{% endif %}

<div class="card">
    <div class="card-header">
        <i class="bi bi-list-check"></i> 详细差异
        <span class="badge bg-secondary ms-2">显示前 {{ trial.results|length }} 条</span>
    </div>
    <div class="card-body">
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>行号</th>
                        <th>类型</th>
                        <th>字段</th>
                        <th>旧值</th>
                        <th>新值</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    {% for r in trial.results %}
                    <tr>
                        <td>{{ r.row_index }}</td>
                        <td>
                            {% set ct_map = {'modified': ('修改', 'warning'), 'added': ('新增', 'success'), 'deleted': ('删除', 'danger'), 'error': ('错误', 'danger')} %}
                            {% set ct = ct_map.get(r.change_type, (r.change_type, 'secondary')) %}
                            <span class="badge bg-{{ ct[1] }}">{{ ct[0] }}</span>
                        </td>
                        <td><code>{{ r.field_name }}</code></td>
                        <td class="text-danger"><del>{{ r.old_value }}</del></td>
                        <td class="text-success"><strong>{{ r.new_value }}</strong></td>
                        <td>
                            <button class="btn btn-sm btn-outline-primary" onclick="showRowDiff({{ loop.index0 }})">
                                <i class="bi bi-eye"></i> 查看行
                            </button>
                        </td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="6" class="text-center text-muted py-4">
                            没有差异数据
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>

<script>
function showRowDiff(index) {
    const results = {{ trial.results | tojson | safe }};
    const r = results[index];
    alert('行 ' + r.row_index + ' 变更详情：\\n\\n变更前：\\n' + JSON.stringify(r.row_data_before, null, 2) + '\\n\\n变更后：\\n' + JSON.stringify(r.row_data_after, null, 2));
}
</script>
{% endblock %}
""", trial=trial, sandbox=sandbox)


@app.route('/promote/<trial_id>/confirm')
def promote_confirm(trial_id):
    """提升确认页"""
    trial = sandbox_manager.get_trial(trial_id)
    if not trial:
        flash('试跑记录不存在', 'danger')
        return redirect(url_for('sandboxes'))

    sandbox = sandbox_manager.get_sandbox(trial['sandbox_id'])
    batches = batch_manager.list_batches(limit=50)

    return render_page("""
{% block title %}提升确认 - {{ sandbox.name }}{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <div>
        <nav aria-label="breadcrumb">
            <ol class="breadcrumb mb-1">
                <li class="breadcrumb-item"><a href="{{ url_for('sandboxes') }}">沙盒管理</a></li>
                <li class="breadcrumb-item"><a href="{{ url_for('sandbox_detail', sandbox_id=sandbox.id) }}">{{ sandbox.name }}</a></li>
                <li class="breadcrumb-item"><a href="{{ url_for('trial_results', trial_id=trial.id) }}">试跑 #{{ trial.id }}</a></li>
                <li class="breadcrumb-item active" aria-current="page">提升确认</li>
            </ol>
        </nav>
        <h2 class="mb-0"><i class="bi bi-rocket-takeoff"></i> 提升为正式修正</h2>
    </div>
    <div>
        <button class="btn btn-outline-secondary" onclick="location.href='{{ url_for('trial_results', trial_id=trial.id) }}'">
            <i class="bi bi-arrow-left"></i> 返回
        </button>
    </div>
</div>

<div class="row">
    <div class="col-md-7">
        <div class="card">
            <div class="card-header bg-warning text-dark">
                <i class="bi bi-exclamation-triangle"></i> 应用前请确认以下信息
            </div>
            <div class="card-body">
                <h5>影响摘要</h5>
                <div class="alert alert-info">
                    <ul class="mb-0">
                        <li><strong>试跑 #{{ trial.id }}</strong> 将应用以下变更到正式数据</li>
                        <li>影响行数：<strong class="text-warning">{{ trial.affected_rows }}</strong> 行</li>
                        <li>总处理行数：{{ trial.total_rows }} 行</li>
                        <li>未变化：{{ trial.unchanged_rows }} 行</li>
                        <li>错误：{{ trial.error_count }} 行</li>
                    </ul>
                </div>

                <form method="POST" action="{{ url_for('promote_apply', trial_id=trial.id) }}">
                    <div class="mb-3">
                        <label class="form-label">目标批次 <span class="text-danger">*</span></label>
                        <select class="form-select" name="target_batch_id" required>
                            {% if sandbox.source_batch_id %}
                            <option value="{{ sandbox.source_batch_id }}">关联批次 #{{ sandbox.source_batch_id }}</option>
                            {% endif %}
                            {% for b in batches %}
                            {% if not b.is_rolled_back %}
                            <option value="{{ b.id }}">
                                #{{ b.id }} - {{ b.batch_no }} ({{ b.batch_type }}, {{ b.created_at[:10] }})
                            </option>
                            {% endif %}
                            {% endfor %}
                        </select>
                    </div>

                    <div class="mb-3">
                        <label class="form-label">
                            <input type="checkbox" name="force" value="1">
                            强制应用，忽略冲突检测
                        </label>
                        <div class="form-text text-warning">
                            <i class="bi bi-exclamation-triangle"></i> 勾选后将强制覆盖已有数据，可能导致数据不一致
                        </div>
                    </div>

                    <div class="d-grid gap-2">
                        <button type="submit" class="btn btn-success btn-lg">
                            <i class="bi bi-check-circle"></i> 确认应用
                        </button>
                    </div>
                </form>
            </div>
        </div>
    </div>
    <div class="col-md-5">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-info-circle"></i> 操作说明
            </div>
            <div class="card-body">
                <div class="alert alert-warning">
                    <h6><i class="bi bi-exclamation-triangle"></i> 注意事项</h6>
                    <ul class="small">
                        <li>此操作将修改正式数据库中的数据</li>
                        <li>系统会自动检测与现有数据的冲突</li>
                        <li>检测到冲突时会阻止应用（除非勾选强制）</li>
                        <li>应用后可以通过"回滚"功能恢复</li>
                        <li>所有操作都会记录到审计日志</li>
                    </ul>
                </div>
                <div class="alert alert-info">
                    <h6><i class="bi bi-info-circle"></i> 冲突检测</h6>
                    <p class="small mb-0">系统会检查目标字段是否已被其他人修改过。如果现有值与原值不同，则视为冲突。</p>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""", trial=trial, sandbox=sandbox, batches=batches)


@app.route('/promote/<trial_id>/apply', methods=['POST'])
def promote_apply(trial_id):
    """执行提升"""
    try:
        target_batch_id = request.form.get('target_batch_id')
        force = request.form.get('force') == '1'

        trial = sandbox_manager.get_trial(trial_id)
        if not trial:
            flash('试跑记录不存在', 'danger')
            return redirect(url_for('sandboxes'))

        promotion = sandbox_manager.promote_to_production(
            sandbox_id_or_no=trial['sandbox_id'],
            trial_id=int(trial_id),
            target_batch_id=target_batch_id,
            force=force,
            operator='web'
        )

        flash(f'修正已成功应用！影响 {promotion["applied_rows"]} 行', 'success')
        return redirect(url_for('promotion_detail', promotion_id=promotion['id']))

    except Exception as e:
        flash(f'应用失败: {str(e)}', 'danger')
        return redirect(url_for('promote_confirm', trial_id=trial_id))


@app.route('/promotions/<promotion_id>')
def promotion_detail(promotion_id):
    """提升记录详情"""
    promotion = sandbox_manager.get_promotion(promotion_id)
    if not promotion:
        flash('提升记录不存在', 'danger')
        return redirect(url_for('sandboxes'))

    sandbox = sandbox_manager.get_sandbox(promotion['sandbox_id'])
    trial = sandbox_manager.get_trial(promotion['trial_id'])

    return render_page("""
{% block title %}提升记录 #{{ promotion.id }}{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <div>
        <nav aria-label="breadcrumb">
            <ol class="breadcrumb mb-1">
                <li class="breadcrumb-item"><a href="{{ url_for('sandboxes') }}">沙盒管理</a></li>
                <li class="breadcrumb-item"><a href="{{ url_for('sandbox_detail', sandbox_id=sandbox.id) }}">{{ sandbox.name }}</a></li>
                <li class="breadcrumb-item active" aria-current="page">提升记录 #{{ promotion.id }}</li>
            </ol>
        </nav>
        <h2 class="mb-0"><i class="bi bi-rocket-takeoff"></i> 提升记录详情</h2>
    </div>
    <div>
        <button class="btn btn-outline-secondary me-2" onclick="location.href='{{ url_for('sandbox_detail', sandbox_id=sandbox.id) }}'">
            <i class="bi bi-arrow-left"></i> 返回沙盒
        </button>
        {% if not promotion.is_rolled_back %}
        <button class="btn btn-danger" onclick="confirmRollback({{ promotion.id }})">
            <i class="bi bi-arrow-counterclockwise"></i> 回滚
        </button>
        {% else %}
        <span class="badge bg-danger">已回滚</span>
        {% endif %}
    </div>
</div>

<div class="card mb-4">
    <div class="card-body">
        <div class="row">
            <div class="col-md-6">
                <strong>提升编号：</strong> {{ promotion.promotion_no }}<br>
                <strong>状态：</strong>
                {% if promotion.is_rolled_back %}
                <span class="badge bg-danger">已回滚</span>
                {% else %}
                <span class="badge bg-success">已应用</span>
                {% endif %}<br>
                <strong>目标批次：</strong> #{{ promotion.target_batch_id }}<br>
                <strong>应用行数：</strong> {{ promotion.applied_rows }}<br>
                <strong>冲突数量：</strong> {{ promotion.conflict_count }}
            </div>
            <div class="col-md-6">
                <strong>操作人：</strong> {{ promotion.applied_by }}<br>
                <strong>应用时间：</strong> {{ promotion.applied_at[:19] if promotion.applied_at else '' }}<br>
                {% if promotion.is_rolled_back %}
                <strong>回滚人：</strong> {{ promotion.rolled_back_by }}<br>
                <strong>回滚时间：</strong> {{ promotion.rolled_back_at[:19] if promotion.rolled_back_at else '' }}<br>
                <strong>回滚原因：</strong> {{ promotion.rollback_note }}
                {% endif %}
            </div>
        </div>
    </div>
</div>

{% if promotion.get('conflicts') %}
<div class="card">
    <div class="card-header">
        <i class="bi bi-exclamation-triangle"></i> 冲突记录 ({{ promotion.conflicts|length }})
    </div>
    <div class="card-body">
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>类型</th>
                        <th>表</th>
                        <th>字段</th>
                        <th>现有值</th>
                        <th>提议值</th>
                        <th>解决状态</th>
                    </tr>
                </thead>
                <tbody>
                    {% for c in promotion.conflicts %}
                    <tr>
                        <td>{{ c.id }}</td>
                        <td>{{ c.conflict_type }}</td>
                        <td>{{ c.target_table }}</td>
                        <td><code>{{ c.field_name }}</code></td>
                        <td class="text-danger">{{ c.existing_value }}</td>
                        <td class="text-success">{{ c.proposed_value }}</td>
                        <td>
                            {% set res_map = {'pending': ('待处理', 'bg-warning'), 'overwritten': ('已覆盖', 'bg-info'), 'rolled_back': ('已回滚', 'bg-danger')} %}
                            {% set r = res_map.get(c.resolution, (c.resolution, 'bg-secondary')) %}
                            <span class="badge {{ r[1] }}">{{ r[0] }}</span>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endif %}

<script>
function confirmRollback(id) {
    const reason = prompt('请输入回滚原因：');
    if (reason && reason.trim()) {
        if (confirm('确定要回滚此提升记录吗？数据将恢复到应用前的状态。')) {
            location.href = "{{ url_for('rollback_promotion', promotion_id=0) }}".replace('/0', '/' + id) + '?reason=' + encodeURIComponent(reason);
        }
    }
}
</script>
{% endblock %}
""", promotion=promotion, sandbox=sandbox, trial=trial)


@app.route('/promotions/<promotion_id>/rollback')
def rollback_promotion(promotion_id):
    """回滚提升记录"""
    try:
        reason = request.args.get('reason', '未填写原因')
        promotion = sandbox_manager.rollback_promotion(
            promotion_id=int(promotion_id),
            reason=reason,
            operator='web'
        )
        flash('回滚成功，数据已恢复', 'success')
    except Exception as e:
        flash(f'回滚失败: {str(e)}', 'danger')

    return redirect(url_for('promotion_detail', promotion_id=promotion_id))


@app.route('/sandboxes/<sandbox_id>/export')
def sandbox_export(sandbox_id):
    """导出沙盒包"""
    try:
        output_path = sandbox_manager.export_sandbox_package(sandbox_id)
        return send_file(output_path, as_attachment=True, download_name=os.path.basename(output_path))
    except Exception as e:
        flash(f'导出失败: {str(e)}', 'danger')
        return redirect(url_for('sandbox_detail', sandbox_id=sandbox_id))


@app.route('/sandboxes/import-package', methods=['POST'])
def sandbox_import_package():
    """导入沙盒包"""
    try:
        if 'file' not in request.files:
            flash('请选择文件', 'danger')
            return redirect(url_for('sandboxes'))

        file = request.files['file']
        if file.filename == '':
            flash('请选择文件', 'danger')
            return redirect(url_for('sandboxes'))

        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            rename = request.form.get('rename') or None

            sandbox = sandbox_manager.import_sandbox_package(
                file_path=filepath,
                rename=rename,
                operator='web'
            )

            os.remove(filepath)
            flash(f'沙盒包导入成功，创建了沙盒 "{sandbox["name"]}"', 'success')
            return redirect(url_for('sandbox_detail', sandbox_id=sandbox['id']))

    except Exception as e:
        flash(f'导入失败: {str(e)}', 'danger')

    return redirect(url_for('sandboxes'))


@app.route('/samples/<sample_id>/view')
def view_sample(sample_id):
    """查看样例数据"""
    sample = sandbox_manager.get_sample(int(sample_id))
    if not sample:
        return '样例不存在', 404

    data = sample.get('data', [])
    return render_page("""
{% block title %}{{ sample.sample_name }} - 样例数据{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="bi bi-file-earmark-spreadsheet"></i> {{ sample.sample_name }}</h2>
    <button class="btn btn-outline-secondary" onclick="window.close()">
        <i class="bi bi-x-lg"></i> 关闭
    </button>
</div>

<div class="card">
    <div class="card-header">
        共 {{ data|length }} 行数据
    </div>
    <div class="card-body p-0">
        <div class="table-responsive" style="max-height: 500px; overflow-y: auto;">
            <table class="table table-sm table-hover mb-0">
                <thead class="table-light sticky-top">
                    <tr>
                        <th>#</th>
                        {% if data %}
                        {% for key in data[0].keys() %}
                        <th>{{ key }}</th>
                        {% endfor %}
                        {% endif %}
                    </tr>
                </thead>
                <tbody>
                    {% for row in data %}
                    <tr>
                        <td>{{ loop.index }}</td>
                        {% for key, value in row.items() %}
                        <td>{{ value if value is not none else '' }}</td>
                        {% endfor %}
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}
""", sample=sample, data=data)


@app.route('/api/sandboxes')
def api_sandboxes():
    """API: 获取沙盒列表"""
    sandboxes = sandbox_manager.list_sandboxes()
    return jsonify({
        'success': True,
        'total': len(sandboxes),
        'data': sandboxes
    })


@app.route('/api/sandboxes/<sandbox_id>')
def api_sandbox_detail(sandbox_id):
    """API: 获取沙盒详情"""
    sandbox = sandbox_manager.get_sandbox(sandbox_id, include_details=True)
    if not sandbox:
        return jsonify({'success': False, 'message': '沙盒不存在'}), 404
    return jsonify({
        'success': True,
        'data': sandbox
    })


@app.route('/api/sandboxes/<sandbox_id>/trials/<trial_id>')
def api_trial_detail(sandbox_id, trial_id):
    """API: 获取试跑详情"""
    trial = sandbox_manager.get_trial(int(trial_id), include_results=True)
    if not trial:
        return jsonify({'success': False, 'message': '试跑记录不存在'}), 404
    return jsonify({
        'success': True,
        'data': trial
    })


@app.route('/api/promotions/<promotion_id>')
def api_promotion_detail(promotion_id):
    """API: 获取提升详情"""
    promotion = sandbox_manager.get_promotion(int(promotion_id))
    if not promotion:
        return jsonify({'success': False, 'message': '提升记录不存在'}), 404
    return jsonify({
        'success': True,
        'data': promotion
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
