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

app = Flask(__name__)
app.secret_key = 'irrigation-analysis-secret-key'
app.config['UPLOAD_FOLDER'] = DATA_DIR
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

ALLOWED_EXTENSIONS = {'csv'}

init_db()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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
    return render_template_string(BASE_TEMPLATE + """
{% extends self %}
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

    return render_template_string(BASE_TEMPLATE + """
{% extends self %}
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
                            {% else %}
                            <span class="badge badge-pending">待复核</span>
                            {% endif %}
                        </td>
                        <td>
                            <button class="btn btn-sm btn-info" onclick="showDetail({{ a.id }})">
                                <i class="bi bi-eye"></i>
                            </button>
                            {% if not a.is_reviewed %}
                            <button class="btn btn-sm btn-success" onclick="reviewAnomaly({{ a.id }}, 'valid')">
                                <i class="bi bi-check"></i>
                            </button>
                            <button class="btn btn-sm btn-warning" onclick="reviewAnomaly({{ a.id }}, 'false_positive')">
                                <i class="bi bi-x"></i>
                            </button>
                            {% endif %}
                            {% if not a.is_rolled_back %}
                            <button class="btn btn-sm btn-danger" onclick="rollbackAnomaly({{ a.id }})">
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
                                {% if a.is_reviewed %}
                                <p class="mt-3"><strong>复核信息：</strong></p>
                                <ul>
                                    <li>结果：{{ a.review_result }}</li>
                                    <li>是否误报：{{ '是' if a.is_false_positive else '否' }}</li>
                                    {% if a.review_comment %}<li>备注：{{ a.review_comment }}</li>{% endif %}
                                    <li>复核人：{{ a.reviewed_by }}</li>
                                    <li>复核时间：{{ a.reviewed_at[:19] if a.reviewed_at else '-' }}</li>
                                </ul>
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


@app.route('/batches')
def batches():
    """批次列表"""
    batch_type = request.args.get('type')
    batch_list = batch_manager.list_batches(batch_type=batch_type, limit=100)

    return render_template_string(BASE_TEMPLATE + """
{% extends self %}
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

    return render_template_string(BASE_TEMPLATE + """
{% extends self %}
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
    return render_template_string(BASE_TEMPLATE + """
{% extends self %}
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

    return render_template_string(BASE_TEMPLATE + """
{% extends self %}
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
