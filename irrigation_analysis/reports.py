# -*- coding: utf-8 -*-
"""
报告生成模块
"""
import json
import csv
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional, Any
from pathlib import Path

from .config import OUTPUT_DIR, EXCEPTION_TYPES, RULE_VERSION
from .database import get_db
from .models import Anomaly, Batch, ReportCache, Parcel


class ReportGenerator:
    """报告生成器"""

    EXPECTED_ANOMALIES = {
        'OVER_PLAN': ('超计划用水', '样例数据中预期1-2条', '实际用水量超过计划的120%'),
        'METER_BACKWARD': ('倒表', '样例数据中预期1条', '读数小于上一次读数'),
        'MISSING_READING': ('漏采', '样例数据中预期1-2条', '间隔超过25小时无读数'),
        'DUPLICATE_REPORT': ('重复上报', '样例数据中预期1条', '同一地块同一时刻重复上报'),
        'UNKNOWN_PARCEL': ('未知地块', '样例数据中预期1条', '地块编号未在台账中登记'),
        'MISSING_PARCEL_ID': ('缺少地块编号', '样例数据中预期1条', '记录缺少地块编号'),
        'INVALID_DATE': ('日期格式错误', '样例数据中预期1条', '日期格式无法解析'),
        'READING_CONFLICT': ('读数冲突', '样例数据中预期1条', '同一时刻读数不一致'),
        'INVALID_REFERENCE': ('引用不存在地块', '样例数据中预期1-2条', '引用了不存在的地块编号'),
    }

    def __init__(self):
        self.output_dir = OUTPUT_DIR
        self.output_dir.mkdir(exist_ok=True)

    def _get_cached_report(self, report_type: str, report_key: str) -> Optional[Dict]:
        """获取缓存的报告"""
        with get_db() as db:
            cache = db.query(ReportCache).filter(
                ReportCache.report_type == report_type,
                ReportCache.report_key == report_key
            ).first()
            if cache:
                try:
                    return json.loads(cache.report_data)
                except (json.JSONDecodeError, TypeError):
                    return None
        return None

    def _cache_report(self, report_type: str, report_key: str, report_data: Dict) -> None:
        """缓存报告数据"""
        with get_db() as db:
            cache = db.query(ReportCache).filter(
                ReportCache.report_type == report_type,
                ReportCache.report_key == report_key
            ).first()
            data_str = json.dumps(report_data, ensure_ascii=False)
            if cache:
                cache.report_data = data_str
                cache.generated_at = datetime.now()
            else:
                cache = ReportCache(
                    report_type=report_type,
                    report_key=report_key,
                    report_data=data_str
                )
                db.add(cache)

    def generate_summary(self, use_cache: bool = True) -> Dict:
        """生成汇总统计"""
        cache_key = f'summary_{datetime.now().strftime("%Y%m%d")}'
        if use_cache:
            cached = self._get_cached_report('summary', cache_key)
            if cached:
                return cached

        with get_db() as db:
            anomalies = db.query(Anomaly).filter(Anomaly.is_rolled_back == False).all()

            by_type = defaultdict(int)
            by_parcel = defaultdict(int)
            by_rule_version = defaultdict(int)
            by_severity = defaultdict(int)
            by_review_status = {
                'total': len(anomalies),
                'reviewed': 0,
                'not_reviewed': 0,
                'false_positive': 0,
                'valid': 0,
                'needs_investigation': 0,
            }

            parcel_names = {}
            parcels = db.query(Parcel).all()
            for p in parcels:
                parcel_names[p.parcel_id] = p.parcel_name or p.parcel_id

            for a in anomalies:
                by_type[a.anomaly_code] += 1
                if a.parcel_id:
                    by_parcel[a.parcel_id] += 1
                by_rule_version[a.rule_version] += 1
                by_severity[a.severity] += 1

                if a.is_reviewed:
                    by_review_status['reviewed'] += 1
                    if a.review_result == 'false_positive':
                        by_review_status['false_positive'] += 1
                    elif a.review_result == 'valid':
                        by_review_status['valid'] += 1
                    elif a.review_result == 'needs_investigation':
                        by_review_status['needs_investigation'] += 1
                else:
                    by_review_status['not_reviewed'] += 1

            by_type_with_names = []
            for code, count in sorted(by_type.items(), key=lambda x: -x[1]):
                by_type_with_names.append({
                    'code': code,
                    'name': EXCEPTION_TYPES.get(code, code),
                    'count': count,
                    'expected': self.EXPECTED_ANOMALIES.get(code, ('', '', ''))[1],
                    'description': self.EXPECTED_ANOMALIES.get(code, ('', '', ''))[2],
                })

            by_parcel_with_names = []
            for pid, count in sorted(by_parcel.items(), key=lambda x: -x[1]):
                by_parcel_with_names.append({
                    'parcel_id': pid,
                    'parcel_name': parcel_names.get(pid, pid),
                    'count': count,
                })

            by_rule_version_list = []
            for version, count in sorted(by_rule_version.items(), key=lambda x: x[0]):
                by_rule_version_list.append({
                    'rule_version': version,
                    'count': count,
                })

            batch_count = db.query(Batch).filter(Batch.is_rolled_back == False).count()
            rolled_back_count = db.query(Batch).filter(Batch.is_rolled_back == True).count()

            result = {
                'generated_at': datetime.now().isoformat(),
                'rule_version': RULE_VERSION,
                'summary': {
                    'total_anomalies': len(anomalies),
                    'total_batches': batch_count,
                    'rolled_back_batches': rolled_back_count,
                    'review_status': by_review_status,
                    'severity_distribution': dict(by_severity),
                },
                'by_type': by_type_with_names,
                'by_parcel': by_parcel_with_names,
                'by_rule_version': by_rule_version_list,
                'expected_anomalies': self.EXPECTED_ANOMALIES,
            }

            self._cache_report('summary', cache_key, result)
            return result

    def generate_detailed_report(self, batch_id: Any = None, anomaly_type: str = None,
                                 parcel_id: str = None, use_cache: bool = True) -> Dict:
        """生成详细报告"""
        parts = ['detailed']
        if batch_id:
            parts.append(f'batch{batch_id}')
        if anomaly_type:
            parts.append(anomaly_type)
        if parcel_id:
            parts.append(parcel_id)
        cache_key = '_'.join(parts)

        if use_cache:
            cached = self._get_cached_report('detailed', cache_key)
            if cached:
                return cached

        with get_db() as db:
            query = db.query(Anomaly).filter(Anomaly.is_rolled_back == False)

            if batch_id:
                if isinstance(batch_id, int) or str(batch_id).isdigit():
                    query = query.filter(Anomaly.batch_id == int(batch_id))
                else:
                    batch = db.query(Batch).filter(Batch.batch_no == str(batch_id)).first()
                    if batch:
                        query = query.filter(Anomaly.batch_id == batch.id)

            if anomaly_type:
                query = query.filter(Anomaly.anomaly_code == anomaly_type)
            if parcel_id:
                query = query.filter(Anomaly.parcel_id == parcel_id)

            anomalies = query.order_by(Anomaly.detected_at.desc()).all()

            parcel_names = {}
            parcels = db.query(Parcel).all()
            for p in parcels:
                parcel_names[p.parcel_id] = p.parcel_name or p.parcel_id

            anomaly_list = []
            for a in anomalies:
                try:
                    extra_data = json.loads(a.extra_data) if a.extra_data else {}
                except (json.JSONDecodeError, TypeError):
                    extra_data = {'raw': a.extra_data}

                batch_no = None
                if a.batch_id:
                    batch = db.query(Batch).filter(Batch.id == a.batch_id).first()
                    if batch:
                        batch_no = batch.batch_no

                anomaly_list.append({
                    'id': a.id,
                    'anomaly_code': a.anomaly_code,
                    'anomaly_type': a.anomaly_type,
                    'description': a.description,
                    'parcel_id': a.parcel_id,
                    'parcel_name': parcel_names.get(a.parcel_id, a.parcel_id) if a.parcel_id else None,
                    'severity': a.severity,
                    'rule_version': a.rule_version,
                    'batch_no': batch_no,
                    'detected_at': a.detected_at.isoformat() if a.detected_at else None,
                    'is_reviewed': a.is_reviewed,
                    'review_result': a.review_result,
                    'is_false_positive': a.is_false_positive,
                    'review_comment': a.review_comment,
                    'extra_data': extra_data,
                })

            result = {
                'generated_at': datetime.now().isoformat(),
                'rule_version': RULE_VERSION,
                'filters': {
                    'batch_id': batch_id,
                    'anomaly_type': anomaly_type,
                    'parcel_id': parcel_id,
                },
                'total_count': len(anomaly_list),
                'anomalies': anomaly_list,
            }

            self._cache_report('detailed', cache_key, result)
            return result

    def export_html(self, output_path: str = None, **kwargs) -> str:
        """导出HTML报告"""
        summary = self.generate_summary(use_cache=False)
        detailed = self.generate_detailed_report(use_cache=False, **kwargs)

        if output_path is None:
            output_path = self.output_dir / f'report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'

        html_content = self._render_html(summary, detailed)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return str(output_path)

    def export_csv(self, output_path: str = None, **kwargs) -> str:
        """导出CSV报告"""
        detailed = self.generate_detailed_report(use_cache=False, **kwargs)

        if output_path is None:
            output_path = self.output_dir / f'report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)

            writer.writerow(['=== 农田灌溉用水异常分析报告 ==='])
            writer.writerow(['生成时间', detailed['generated_at']])
            writer.writerow(['规则版本', detailed['rule_version']])
            writer.writerow([])

            filters = detailed.get('filters', {})
            if any(filters.values()):
                writer.writerow(['筛选条件'])
                for k, v in filters.items():
                    if v:
                        writer.writerow([k, v])
                writer.writerow([])

            writer.writerow(['汇总统计'])
            writer.writerow(['异常总数', detailed['total_count']])
            writer.writerow([])

            writer.writerow([
                '异常ID', '异常代码', '异常类型', '描述', '地块编号', '地块名称',
                '严重程度', '规则版本', '批次号', '检测时间',
                '是否复核', '复核结果', '是否误报', '复核备注', '扩展信息'
            ])

            for a in detailed['anomalies']:
                writer.writerow([
                    a['id'],
                    a['anomaly_code'],
                    a['anomaly_type'],
                    a['description'],
                    a.get('parcel_id', ''),
                    a.get('parcel_name', ''),
                    a['severity'],
                    a['rule_version'],
                    a.get('batch_no', ''),
                    a.get('detected_at', ''),
                    '是' if a['is_reviewed'] else '否',
                    a.get('review_result', ''),
                    '是' if a.get('is_false_positive') else '否',
                    a.get('review_comment', ''),
                    json.dumps(a.get('extra_data', {}), ensure_ascii=False)
                ])

        return str(output_path)

    def _render_html(self, summary: Dict, detailed: Dict) -> str:
        """渲染HTML报告"""
        severity_colors = {
            'high': '#dc3545',
            'medium': '#ffc107',
            'low': '#28a745',
        }

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>农田灌溉用水异常分析报告</title>
    <style>
        body {{ font-family: "Microsoft YaHei", Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1400px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; border-left: 4px solid #3498db; padding-left: 15px; }}
        h3 {{ color: #34495e; margin-top: 20px; }}
        .info-bar {{ background: #e8f4fd; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .info-item {{ display: inline-block; margin-right: 30px; }}
        .info-label {{ color: #7f8c8d; font-size: 14px; }}
        .info-value {{ font-size: 18px; font-weight: bold; color: #2c3e50; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th {{ background: #3498db; color: white; padding: 12px; text-align: left; font-weight: normal; }}
        td {{ padding: 10px; border-bottom: 1px solid #ecf0f1; }}
        tr:hover {{ background: #f8f9fa; }}
        .severity-high {{ color: #dc3545; font-weight: bold; }}
        .severity-medium {{ color: #ffc107; font-weight: bold; }}
        .severity-low {{ color: #28a745; font-weight: bold; }}
        .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 12px; color: white; }}
        .badge-reviewed {{ background: #28a745; }}
        .badge-pending {{ background: #6c757d; }}
        .badge-false {{ background: #ffc107; color: #333; }}
        .summary-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; border-top: 4px solid #3498db; }}
        .card-value {{ font-size: 32px; font-weight: bold; color: #2c3e50; }}
        .card-label {{ color: #7f8c8d; font-size: 14px; margin-top: 5px; }}
        .expected-note {{ background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107; }}
        .detail-row {{ background: #fafafa; }}
        pre {{ background: #f8f9fa; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🌾 农田灌溉用水异常分析报告</h1>

        <div class="info-bar">
            <div class="info-item">
                <div class="info-label">生成时间</div>
                <div class="info-value">{summary['generated_at']}</div>
            </div>
            <div class="info-item">
                <div class="info-label">规则版本</div>
                <div class="info-value">{summary['rule_version']}</div>
            </div>
        </div>

        <h2>📊 总体汇总</h2>
        <div class="summary-cards">
            <div class="card">
                <div class="card-value">{summary['summary']['total_anomalies']}</div>
                <div class="card-label">异常总数</div>
            </div>
            <div class="card">
                <div class="card-value">{summary['summary']['total_batches']}</div>
                <div class="card-label">有效批次</div>
            </div>
            <div class="card">
                <div class="card-value">{summary['summary']['rolled_back_batches']}</div>
                <div class="card-label">已回滚批次</div>
            </div>
            <div class="card">
                <div class="card-value">{summary['summary']['review_status']['reviewed']}</div>
                <div class="card-label">已复核</div>
            </div>
            <div class="card">
                <div class="card-value">{summary['summary']['review_status']['not_reviewed']}</div>
                <div class="card-label">待复核</div>
            </div>
            <div class="card">
                <div class="card-value">{summary['summary']['review_status']['false_positive']}</div>
                <div class="card-label">误报数</div>
            </div>
        </div>

        <h2>📈 按异常类型汇总</h2>
        <table>
            <tr>
                <th>异常代码</th>
                <th>异常类型</th>
                <th>数量</th>
                <th>样例预期</th>
                <th>说明</th>
            </tr>
            {''.join(f'''
            <tr>
                <td><code>{item['code']}</code></td>
                <td><strong>{item['name']}</strong></td>
                <td style="font-size: 20px; font-weight: bold; color: #e74c3c;">{item['count']}</td>
                <td>{item['expected']}</td>
                <td>{item['description']}</td>
            </tr>
            ''' for item in summary['by_type'])}
        </table>

        <div class="expected-note">
            <strong>📝 样例数据说明：</strong> 本工具内置的样例数据包含所有9种异常类型的可复现场景。
            上表中"样例预期"列为使用样例数据时的预期异常数量范围。
        </div>

        <h2>📍 按地块汇总</h2>
        <table>
            <tr>
                <th>地块编号</th>
                <th>地块名称</th>
                <th>异常数量</th>
            </tr>
            {''.join(f'''
            <tr>
                <td><code>{item['parcel_id']}</code></td>
                <td>{item['parcel_name']}</td>
                <td style="font-weight: bold;">{item['count']}</td>
            </tr>
            ''' for item in summary['by_parcel'])}
        </table>

        <h2>📋 按规则版本汇总</h2>
        <table>
            <tr>
                <th>规则版本</th>
                <th>异常数量</th>
            </tr>
            {''.join(f'''
            <tr>
                <td><code>{item['rule_version']}</code></td>
                <td style="font-weight: bold;">{item['count']}</td>
            </tr>
            ''' for item in summary['by_rule_version'])}
        </table>

        <h2>🔍 异常明细</h2>
        <table>
            <tr>
                <th>ID</th>
                <th>异常类型</th>
                <th>地块</th>
                <th>严重程度</th>
                <th>规则版本</th>
                <th>批次号</th>
                <th>检测时间</th>
                <th>状态</th>
                <th>描述</th>
            </tr>
            {''.join(self._render_anomaly_row(a, severity_colors) for a in detailed['anomalies'])}
        </table>

        <h2>📄 详细信息</h2>
        {''.join(self._render_anomaly_detail(a) for a in detailed['anomalies'])}
    </div>
</body>
</html>"""
        return html

    def _render_anomaly_row(self, a: Dict, severity_colors: Dict) -> str:
        """渲染异常表格行"""
        severity_class = f'severity-{a["severity"]}'
        severity_name = {'high': '高', 'medium': '中', 'low': '低'}.get(a['severity'], a['severity'])

        if a['is_reviewed']:
            if a['is_false_positive']:
                status_badge = '<span class="badge badge-false">误报</span>'
            elif a['review_result'] == 'valid':
                status_badge = '<span class="badge badge-reviewed">确认有效</span>'
            else:
                status_badge = '<span class="badge badge-reviewed">待调查</span>'
        else:
            status_badge = '<span class="badge badge-pending">待复核</span>'

        return f'''
            <tr>
                <td>{a['id']}</td>
                <td><strong>{a['anomaly_type']}</strong><br><small style="color: #999;">{a['anomaly_code']}</small></td>
                <td>{a.get('parcel_name', '') or a.get('parcel_id', '-')}</td>
                <td class="{severity_class}">{severity_name}</td>
                <td><code>{a['rule_version']}</code></td>
                <td><code>{a.get('batch_no', '-')}</code></td>
                <td><small>{a.get('detected_at', '-')}</small></td>
                <td>{status_badge}</td>
                <td style="max-width: 300px;">{a['description']}</td>
            </tr>
        '''

    def _render_anomaly_detail(self, a: Dict) -> str:
        """渲染异常详情"""
        import json
        extra_str = json.dumps(a.get('extra_data', {}), ensure_ascii=False, indent=2)

        review_section = ''
        if a['is_reviewed']:
            review_section = f'''
            <p><strong>复核结果：</strong>{a.get('review_result', '')}</p>
            <p><strong>是否误报：</strong>{'是' if a.get('is_false_positive') else '否'}</p>
            {f'<p><strong>复核备注：</strong>{a.get("review_comment", "")}</p>' if a.get('review_comment') else ''}
            '''

        return f'''
        <div class="detail-row" style="padding: 15px; margin: 10px 0; border-radius: 5px;">
            <h3>#{a['id']} {a['anomaly_type']} <small style="color: #999;">({a['anomaly_code']})</small></h3>
            <p><strong>描述：</strong>{a['description']}</p>
            <p><strong>地块：</strong>{a.get('parcel_name', '') or a.get('parcel_id', '-')} ({a.get('parcel_id', '-')})</p>
            <p><strong>严重程度：</strong>{a['severity']}</p>
            <p><strong>检测时间：</strong>{a.get('detected_at', '-')}</p>
            <p><strong>规则版本：</strong>{a['rule_version']}</p>
            <p><strong>批次号：</strong>{a.get('batch_no', '-')}</p>
            {review_section}
            <details>
                <summary>查看扩展数据</summary>
                <pre>{extra_str}</pre>
            </details>
        </div>
        '''


report_generator = ReportGenerator()
