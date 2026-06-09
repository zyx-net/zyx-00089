# -*- coding: utf-8 -*-
"""
命令行接口
"""
import sys
import io
import os
import json
from datetime import datetime
from typing import Optional
import click

from .database import init_db
from .importer import DataImporter, ImportError
from .rules import RuleEngine
from .batch_manager import batch_manager, review_manager, rollback_manager
from .reports import report_generator
from .sample_data import sample_data_generator
from .config import EXCEPTION_TYPES
from .threshold_manager import (
    threshold_manager, ThresholdSchemeError,
    ThresholdSchemeNotFoundError, ThresholdSchemeNameConflictError,
    ThresholdSchemeValidationError, ThresholdSchemeImportError
)


def _fix_console_encoding() -> None:
    """修复Windows控制台编码问题，避免GBK环境下UnicodeEncodeError"""
    if sys.platform != 'win32':
        return

    try:
        def _safe_write(stream, text):
            if isinstance(text, bytes):
                text = text.decode('utf-8', errors='replace')
            try:
                stream.buffer.write(text.encode('utf-8'))
                stream.flush()
            except Exception:
                try:
                    stream.buffer.write(text.encode(sys.stdout.encoding or 'gbk', errors='replace'))
                    stream.flush()
                except Exception:
                    pass

        if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() in ('cp936', 'gbk', 'gb2312'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr and sys.stderr.encoding and sys.stderr.encoding.lower() in ('cp936', 'gbk', 'gb2312'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')

        os.environ.setdefault('PYTHONIOENCODING', 'utf-8:replace')

    except Exception:
        pass


_fix_console_encoding()


class CliErrorHandler:
    """CLI错误处理"""

    @staticmethod
    def handle_error(e: Exception, ctx: Optional[click.Context] = None) -> None:
        """处理错误并输出友好信息"""
        if isinstance(e, ImportError):
            click.secho(f'❌ 导入错误: {str(e)}', fg='red', bold=True)
        elif isinstance(e, ThresholdSchemeNotFoundError):
            click.secho(f'❌ 方案不存在: {str(e)}', fg='red', bold=True)
        elif isinstance(e, ThresholdSchemeNameConflictError):
            click.secho(f'❌ 方案名称冲突: {str(e)}', fg='yellow', bold=True)
        elif isinstance(e, ThresholdSchemeValidationError):
            click.secho(f'❌ 验证错误: {str(e)}', fg='red', bold=True)
        elif isinstance(e, ThresholdSchemeImportError):
            click.secho(f'❌ 导入错误: {str(e)}', fg='red', bold=True)
        elif isinstance(e, ThresholdSchemeError):
            click.secho(f'❌ 阈值方案错误: {str(e)}', fg='red', bold=True)
        elif isinstance(e, ValueError):
            click.secho(f'❌ 参数错误: {str(e)}', fg='red', bold=True)
        elif isinstance(e, FileNotFoundError):
            click.secho(f'❌ 文件不存在: {str(e)}', fg='red', bold=True)
        else:
            click.secho(f'❌ 错误: {str(e)}', fg='red', bold=True)

        if ctx:
            click.echo(ctx.get_help())

        sys.exit(1)


@click.group(help='🌾 农田灌溉用水异常分析工具')
@click.version_option(version='1.0.0', prog_name='irrigation-analysis')
def cli():
    """命令行接口主入口"""
    try:
        init_db()
    except Exception as e:
        click.secho(f'⚠️  数据库初始化警告: {e}', fg='yellow')


@cli.command('init', help='初始化数据库')
def init_database():
    """初始化数据库"""
    try:
        init_db()
        click.secho('✅ 数据库初始化成功', fg='green', bold=True)
    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('sample', help='生成样例数据')
@click.option('--print-expected', is_flag=True, help='打印预期异常数量')
def generate_sample(print_expected):
    """生成样例数据"""
    try:
        if print_expected:
            sample_data_generator.print_expected_anomalies()
            return

        files = sample_data_generator.generate_all()
        click.secho('✅ 样例数据生成成功', fg='green', bold=True)
        click.echo('生成的文件:')
        for name, path in files.items():
            click.echo(f'  {name}: {path}')

        click.echo()
        sample_data_generator.print_expected_anomalies()
    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('import', help='导入数据')
@click.argument('data_type', type=click.Choice(['parcel', 'meter', 'plan', 'weather']))
@click.argument('file_path', type=click.Path(exists=True, readable=True))
@click.option('--description', '-d', default='', help='批次描述')
def import_data(data_type, file_path, description):
    """
    导入数据

    DATA_TYPE: 数据类型 (parcel/meter/plan/weather)
    FILE_PATH: CSV文件路径
    """
    try:
        importer = DataImporter()
        type_names = {
            'parcel': '地块台账',
            'meter': '水表读数',
            'plan': '灌溉计划',
            'weather': '天气补录',
        }

        click.echo(f'📥 正在导入{type_names[data_type]}...')

        if data_type == 'parcel':
            result = importer.import_parcels(file_path, description)
        elif data_type == 'meter':
            result = importer.import_meters(file_path, description)
        elif data_type == 'plan':
            result = importer.import_plans(file_path, description)
        elif data_type == 'weather':
            result = importer.import_weather(file_path, description)
        else:
            raise ValueError(f'不支持的数据类型: {data_type}')

        click.secho(f'✅ 导入完成', fg='green', bold=True)
        click.echo(f'  批次号: {result["batch_no"]}')
        click.echo(f'  成功: {result["success_count"]}/{result["total_count"]} 条')
        if result['error_count'] > 0:
            click.secho(f'  错误: {result["error_count"]} 条', fg='yellow')
            if result['errors']:
                click.echo('\n错误详情:')
                for err in result['errors']:
                    click.secho(f'    - {err}', fg='red')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('import-all', help='一键导入所有样例数据')
def import_all_sample():
    """一键导入所有样例数据"""
    try:
        click.echo('📥 正在生成并导入样例数据...')
        files = sample_data_generator.generate_all()

        importer = DataImporter()

        click.echo('\n1. 导入地块台账...')
        result = importer.import_parcels(files['parcels'], '样例数据')
        click.echo(f'   批次号: {result["batch_no"]}, 成功: {result["success_count"]}/{result["total_count"]}')

        click.echo('\n2. 导入灌溉计划...')
        result = importer.import_plans(files['plans'], '样例数据')
        click.echo(f'   批次号: {result["batch_no"]}, 成功: {result["success_count"]}/{result["total_count"]}')

        click.echo('\n3. 导入天气补录...')
        result = importer.import_weather(files['weather'], '样例数据')
        click.echo(f'   批次号: {result["batch_no"]}, 成功: {result["success_count"]}/{result["total_count"]}')

        click.echo('\n4. 导入水表读数...')
        result = importer.import_meters(files['meters'], '样例数据')
        click.echo(f'   批次号: {result["batch_no"]}, 成功: {result["success_count"]}/{result["total_count"]}')
        if result['errors']:
            click.secho(f'   错误: {result["error_count"]} 条', fg='yellow')
            for err in result['errors']:
                click.secho(f'     - {err}', fg='red')

        click.secho('\n✅ 所有样例数据导入完成', fg='green', bold=True)
        sample_data_generator.print_expected_anomalies()

    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('detect', help='执行异常检测')
@click.option('--batch-id', '-b', default=None, help='指定批次ID或批次号')
@click.option('--parcel-id', '-p', default=None, help='指定地块编号')
def detect_anomalies(batch_id, parcel_id):
    """执行异常检测"""
    try:
        click.echo('🔍 正在执行异常检测...')
        engine = RuleEngine()
        anomalies = engine.detect_all(batch_id=batch_id, parcel_id=parcel_id)

        click.secho(f'✅ 检测完成，新发现 {len(anomalies)} 条异常', fg='green', bold=True)

        if anomalies:
            click.echo('\n异常列表:')
            for a in anomalies:
                anomaly_id = a.get('id', '?')
                anomaly_code = a.get('anomaly_code') or 'UNKNOWN'
                description = a.get('description') or '无描述'
                severity_color = {'high': 'red', 'medium': 'yellow', 'low': 'green'}
                color = severity_color.get(a.get('severity', 'medium'))
                click.secho(
                    f'  #{anomaly_id:>3} [{anomaly_code}] {description[:60]}...',
                    fg=color
                )
        else:
            click.echo('没有发现新异常。')

        summary = report_generator.generate_summary(use_cache=False)
        click.echo(f'\n📊 当前异常统计:')
        for item in summary['by_type']:
            click.echo(f'  {item["name"]}: {item["count"]} 条')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('batches', help='查看批次列表')
@click.option('--type', '-t', default=None, help='按类型过滤')
@click.option('--limit', '-n', default=20, help='显示数量')
def list_batches(type, limit):
    """查看批次列表"""
    try:
        batches = batch_manager.list_batches(batch_type=type, limit=limit)

        click.echo(f'📦 批次列表 (共 {len(batches)} 个批次):')
        click.echo('-' * 80)
        click.echo(f'{"ID":>4} {"批次号":<25} {"类型":<10} {"规则":<10} {"状态":<10} {"异常数":>6} {"创建时间":<20}')
        click.echo('-' * 80)

        for b in batches:
            status = '已回滚' if b['is_rolled_back'] else '正常'
            status_color = 'yellow' if b['is_rolled_back'] else 'green'
            anomaly_count = b.get('anomaly_count', 0) if b.get('anomaly_count', 0) is not None else 0
            click.secho(
                f'{b["id"]:>4} {b["batch_no"]:<25} {b["batch_type"]:<10} {b["rule_version"]:<10} ',
                nl=False
            )
            click.secho(f'{status:<10} ', fg=status_color, nl=False)
            click.secho(f'{anomaly_count:>6} ', nl=False)
            click.echo(f'{b["created_at"][:19] if b["created_at"] else "":<20}')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.group('anomalies', help='🔍 异常管理', invoke_without_command=True)
@click.option('--batch-id', '-b', default=None, help='按批次过滤')
@click.option('--type', '-t', default=None, help='按异常类型过滤')
@click.option('--reviewed/--not-reviewed', default=None, help='按复核状态过滤')
@click.option('--parcel-id', '-p', default=None, help='按地块过滤')
@click.option('--limit', '-n', default=50, help='显示数量')
@click.pass_context
def anomalies(ctx, batch_id, type, reviewed, parcel_id, limit):
    """异常管理命令组"""
    if ctx.invoked_subcommand is None:
        _list_anomalies(batch_id, type, reviewed, parcel_id, limit)


def _list_anomalies(batch_id, type, reviewed, parcel_id, limit):
    """查看异常列表"""
    try:
        anomalies = review_manager.list_anomalies(
            batch_id=batch_id,
            anomaly_type=type,
            is_reviewed=reviewed,
            parcel_id=parcel_id,
            limit=limit,
        )

        click.echo(f'🔍 异常列表 (共 {len(anomalies)} 条异常):')
        click.echo('-' * 120)
        click.echo(f'{"ID":>4} {"类型":<18} {"地块":<10} {"严重程度":<8} {"状态":<8} {"规则":<8} {"方案":<15} {"描述"}')
        click.echo('-' * 120)

        for a in anomalies:
            parcel_id = a.get('parcel_id') or '-'
            anomaly_type = a.get('anomaly_type') or '未知异常'
            severity = a.get('severity') or 'medium'
            rule_version = a.get('rule_version') or '-'
            scheme_name = a.get('threshold_scheme_name') or '-'
            description = a.get('description') or '无描述'
            desc = description[:40] + '...' if len(description) > 40 else description

            severity_color = {'high': 'red', 'medium': 'yellow', 'low': 'green'}
            color = severity_color.get(severity, 'yellow')
            if a['is_reviewed']:
                if a['is_false_positive']:
                    status = '误报'
                    status_color = 'yellow'
                elif a.get('review_result') == 'valid':
                    status = '有效'
                    status_color = 'green'
                else:
                    status = '待调查'
                    status_color = 'cyan'
            else:
                status = '待复核'
                status_color = 'white'

            scheme_display = scheme_name if len(scheme_name) <= 12 else scheme_name[:12] + '..'

            click.echo(f'{a["id"]:>4} ', nl=False)
            click.secho(f'{anomaly_type:<18} ', fg=color, nl=False)
            click.echo(f'{parcel_id:<10} ', nl=False)
            click.secho(f'{severity:<6} ', fg=color, nl=False)
            click.secho(f'{status:<8} ', fg=status_color, nl=False)
            click.echo(f'{rule_version:<8} ', nl=False)
            click.secho(f'{scheme_display:<15} ', fg='cyan', nl=False)
            click.echo(desc)

    except Exception as e:
        CliErrorHandler.handle_error(e)


@anomalies.command('list', help='查看异常列表')
@click.option('--batch-id', '-b', default=None, help='按批次过滤')
@click.option('--type', '-t', default=None, help='按异常类型过滤')
@click.option('--reviewed/--not-reviewed', default=None, help='按复核状态过滤')
@click.option('--parcel-id', '-p', default=None, help='按地块过滤')
@click.option('--limit', '-n', default=50, help='显示数量')
def anomalies_list(batch_id, type, reviewed, parcel_id, limit):
    """查看异常列表"""
    _list_anomalies(batch_id, type, reviewed, parcel_id, limit)


@anomalies.command('get', help='获取单个异常详情（JSON格式）')
@click.argument('anomaly_id', type=int)
def anomalies_get(anomaly_id):
    """
    获取单个异常的详细信息，输出JSON格式

    ANOMALY_ID: 异常ID
    """
    try:
        anomaly = review_manager.get_anomaly(anomaly_id)
        if not anomaly:
            raise ValueError(f'异常不存在: {anomaly_id}')

        import json
        click.echo(json.dumps(anomaly, ensure_ascii=False, indent=2))

    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('review', help='复核异常')
@click.argument('anomaly_id', type=int)
@click.argument('result', type=click.Choice(['valid', 'false_positive', 'needs_investigation']))
@click.option('--comment', '-c', default='', help='复核备注')
@click.option('--by', '-u', default='cli', help='复核人')
def review_anomaly(anomaly_id, result, comment, by):
    """
    复核异常

    ANOMALY_ID: 异常ID

    RESULT: 复核结果 (valid/false_positive/needs_investigation)
    """
    try:
        result_names = {
            'valid': '确认有效',
            'false_positive': '误报',
            'needs_investigation': '待调查',
        }

        click.echo(f'📝 正在复核异常 #{anomaly_id}...')

        anomaly = review_manager.review_anomaly(
            anomaly_id=anomaly_id,
            review_result=result,
            review_comment=comment,
            reviewed_by=by
        )

        click.secho(f'✅ 复核完成', fg='green', bold=True)
        click.echo(f'  异常ID: {anomaly_id}')
        click.echo(f'  异常类型: {anomaly["anomaly_type"]}')
        click.echo(f'  复核结果: {result_names[result]}')
        if comment:
            click.echo(f'  复核备注: {comment}')
        click.echo(f'  历史记录数: {anomaly["review_summary"]["review_count"]}')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('review-history', help='查看异常复核时间线')
@click.argument('anomaly_id', type=int)
def review_history(anomaly_id):
    """
    查看某条异常的复核时间线

    ANOMALY_ID: 异常ID
    """
    try:
        click.echo(f'📜 异常 #{anomaly_id} 的复核时间线')
        click.echo('=' * 100)

        anomaly = review_manager.get_anomaly(anomaly_id)
        if not anomaly:
            raise ValueError(f'异常不存在: {anomaly_id}')

        history = review_manager.get_review_history(anomaly_id)

        click.echo(f'异常描述: {anomaly["description"]}')
        click.echo(f'异常类型: {anomaly["anomaly_type"]} ({anomaly["anomaly_code"]})')
        click.echo(f'当前状态: {"已复核" if anomaly["is_reviewed"] else "待复核"}')
        if anomaly["is_reviewed"]:
            result_name = {'valid': '确认有效', 'false_positive': '误报', 'needs_investigation': '待调查'}.get(anomaly["review_result"], anomaly["review_result"])
            click.echo(f'当前结果: {result_name}')
        click.echo(f'复核次数: {anomaly["review_summary"]["review_count"]} (撤销次数: {anomaly["review_summary"]["undo_count"]})')
        click.echo()

        if not history:
            click.echo('暂无复核记录')
        else:
            click.echo(f'{"序号":<6} {"操作类型":<12} {"处置状态":<10} {"操作人":<10} {"操作时间":<20} {"备注"}')
            click.echo('-' * 100)

            for h in history:
                seq = h['sequence']
                action = h['action_type_name']
                result = h['review_result_name'] or '-'
                operator = h['reviewed_by']
                time_str = h['reviewed_at'][:19] if h['reviewed_at'] else '-'
                comment = (h['review_comment'] or '')[:40]

                if h['is_undone']:
                    prefix = '↩️  '
                    action_color = 'white'
                    strike = True
                else:
                    prefix = '   '
                    action_color = {'review': 'green', 'update_status': 'cyan', 'append_comment': 'yellow', 'undo': 'magenta'}.get(h['action_type'], 'white')
                    strike = False

                display_seq = f'{prefix}#{seq}'
                display_action = click.style(action, fg=action_color, dim=h['is_undone'])
                display_result = click.style(result, dim=h['is_undone'])
                display_comment = click.style(comment, dim=h['is_undone'])

                if strike:
                    display_seq = click.style(display_seq, fg='white', dim=True)

                click.echo(f'{display_seq:<10} {display_action:<16} {display_result:<10} {operator:<10} {time_str:<20} {display_comment}')
                if h['is_undone']:
                    undo_info = f'         于 {h["undone_at"][:19] if h["undone_at"] else "-"} 由 {h["undone_by"]} 撤销'
                    if h['undo_reason']:
                        undo_info += f'，原因: {h["undo_reason"]}'
                    click.echo(click.style(undo_info, fg='white', dim=True))

        click.echo()
        click.echo('说明: ↩️ 表示该操作已被撤销，显示为灰色')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('review-append', help='追加复核备注')
@click.argument('anomaly_id', type=int)
@click.argument('comment', type=str)
@click.option('--by', '-u', default='cli', help='操作人')
def review_append(anomaly_id, comment, by):
    """
    为异常追加备注（不改变处置状态）

    ANOMALY_ID: 异常ID

    COMMENT: 备注内容
    """
    try:
        click.echo(f'📝 为异常 #{anomaly_id} 追加备注...')

        anomaly = review_manager.append_comment(
            anomaly_id=anomaly_id,
            comment=comment,
            reviewed_by=by
        )

        click.secho(f'✅ 备注追加成功', fg='green', bold=True)
        click.echo(f'  异常ID: {anomaly_id}')
        click.echo(f'  备注内容: {comment}')
        click.echo(f'  历史记录数: {anomaly["review_summary"]["review_count"]}')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('review-update', help='修改异常处置状态')
@click.argument('anomaly_id', type=int)
@click.argument('new_status', type=click.Choice(['valid', 'false_positive', 'needs_investigation']))
@click.option('--comment', '-c', default='', help='修改说明（可选）')
@click.option('--by', '-u', default='cli', help='操作人')
def review_update(anomaly_id, new_status, comment, by):
    """
    修改异常的处置状态

    ANOMALY_ID: 异常ID

    NEW_STATUS: 新的处置状态 (valid/false_positive/needs_investigation)
    """
    try:
        result_names = {
            'valid': '确认有效',
            'false_positive': '误报',
            'needs_investigation': '待调查',
        }

        click.echo(f'🔄 正在修改异常 #{anomaly_id} 的处置状态...')

        anomaly = review_manager.update_review_status(
            anomaly_id=anomaly_id,
            new_status=new_status,
            comment=comment,
            reviewed_by=by
        )

        click.secho(f'✅ 状态修改成功', fg='green', bold=True)
        click.echo(f'  异常ID: {anomaly_id}')
        click.echo(f'  新状态: {result_names[new_status]}')
        if comment:
            click.echo(f'  修改说明: {comment}')
        click.echo(f'  历史记录数: {anomaly["review_summary"]["review_count"]}')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('review-undo', help='撤销最近一次复核操作')
@click.argument('anomaly_id', type=int)
@click.option('--reason', '-r', default='', help='撤销原因')
@click.option('--by', '-u', default='cli', help='操作人')
def review_undo(anomaly_id, reason, by):
    """
    撤销异常最近一次复核操作

    ANOMALY_ID: 异常ID
    """
    try:
        click.echo(f'⏪ 正在撤销异常 #{anomaly_id} 的最近一次复核...')

        anomaly = review_manager.undo_last_review(
            anomaly_id=anomaly_id,
            undo_reason=reason,
            undone_by=by
        )

        click.secho(f'✅ 撤销成功', fg='green', bold=True)
        click.echo(f'  异常ID: {anomaly_id}')
        if reason:
            click.echo(f'  撤销原因: {reason}')

        if anomaly["is_reviewed"]:
            result_name = {'valid': '确认有效', 'false_positive': '误报', 'needs_investigation': '待调查'}.get(anomaly["review_result"], anomaly["review_result"])
            click.echo(f'  当前状态: 已复核 - {result_name}')
        else:
            click.echo(f'  当前状态: 待复核')

        click.echo(f'  撤销次数: {anomaly["review_summary"]["undo_count"]}')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('rollback', help='回滚批次或异常')
@click.option('--batch-id', '-b', default=None, help='批次ID或批次号')
@click.option('--anomaly-id', '-a', type=int, default=None, help='异常ID')
@click.option('--reason', '-r', required=True, help='回滚原因')
@click.option('--by', '-u', default='cli', help='操作人')
def rollback(batch_id, anomaly_id, reason, by):
    """回滚批次或异常"""
    try:
        if batch_id and anomaly_id:
            raise ValueError('不能同时指定批次ID和异常ID，请二选一')

        if batch_id:
            click.echo(f'⏪ 正在回滚批次 {batch_id}...')
            result = rollback_manager.rollback_batch(batch_id, reason, by)
            click.secho(f'✅ 批次回滚完成', fg='green', bold=True)
            click.echo(f'  回滚号: {result["rollback_no"]}')
            click.echo(f'  批次号: {result["batch_no"]}')
            click.echo(f'  回滚异常数: {result["anomalies_rolled_back"]}')
            click.echo(f'  删除读数: {result["meters_deleted"]} 条读数, {result["plans_deleted"]} 条计划, {result["weather_deleted"]} 条天气')
            click.echo(f'  原因: {reason}')

        elif anomaly_id:
            click.echo(f'⏪ 正在回滚异常 #{anomaly_id}...')
            result = rollback_manager.rollback_anomaly(anomaly_id, reason, by)
            click.secho(f'✅ 异常回滚完成', fg='green', bold=True)
            click.echo(f'  回滚号: {result["rollback_no"]}')
            click.echo(f'  原因: {reason}')

        else:
            raise ValueError('请指定 --batch-id 或 --anomaly-id')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('rollbacks', help='查看回滚记录')
@click.option('--limit', '-n', default=20, help='显示数量')
def list_rollbacks(limit):
    """查看回滚记录"""
    try:
        rollbacks = rollback_manager.list_rollbacks(limit=limit)

        click.echo(f'⏪ 回滚记录 (共 {len(rollbacks)} 条):')
        click.echo('-' * 80)
        click.echo(f'{"ID":>4} {"回滚号":<25} {"批次号":<25} {"异常数":>6} {"操作人":<10} {"时间":<20}')
        click.echo('-' * 80)

        for r in rollbacks:
            click.echo(
                f'{r["id"]:>4} {r["rollback_no"]:<25} {r.get("batch_no", ""):<25} '
                f'{r.get("anomaly_count", 0):>6} {r["created_by"]:<10} {r["created_at"][:19] if r["created_at"] else "":<20}'
            )

    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('report', help='生成报告')
@click.option('--format', '-f', type=click.Choice(['html', 'csv']), default='html', help='报告格式')
@click.option('--output', '-o', default=None, help='输出文件路径')
@click.option('--batch-id', '-b', default=None, help='按批次过滤')
@click.option('--type', '-t', default=None, help='按异常类型过滤')
@click.option('--parcel-id', '-p', default=None, help='按地块过滤')
def generate_report(format, output, batch_id, type, parcel_id):
    """生成报告"""
    try:
        click.echo(f'📄 正在生成{format.upper()}报告...')

        if format == 'html':
            path = report_generator.export_html(
                output_path=output,
                batch_id=batch_id,
                anomaly_type=type,
                parcel_id=parcel_id
            )
        else:
            path = report_generator.export_csv(
                output_path=output,
                batch_id=batch_id,
                anomaly_type=type,
                parcel_id=parcel_id
            )

        click.secho(f'✅ 报告生成成功', fg='green', bold=True)
        click.echo(f'  输出路径: {path}')

        summary = report_generator.generate_summary(use_cache=False)
        click.echo(f'\n📊 报告统计:')
        click.echo(f'  异常总数: {summary["summary"]["total_anomalies"]}')
        click.echo(f'  已复核: {summary["summary"]["review_status"]["reviewed"]}')
        click.echo(f'  待复核: {summary["summary"]["review_status"]["not_reviewed"]}')
        click.echo(f'  误报: {summary["summary"]["review_status"]["false_positive"]}')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('summary', help='显示统计汇总')
def show_summary():
    """显示统计汇总"""
    try:
        summary = report_generator.generate_summary(use_cache=False)

        click.echo('📊 异常分析统计汇总')
        click.echo('=' * 60)
        click.echo(f'生成时间: {summary["generated_at"]}')
        click.echo(f'规则版本: {summary["rule_version"]}')

        scheme = summary.get('active_threshold_scheme', {})
        click.echo()
        click.secho('🎛️  当前阈值方案:', fg='cyan', bold=True)
        click.echo(f'  方案名称: {scheme.get("name", "-")}')
        click.echo(f'  水表倒退容差: {scheme.get("meter_backward_tolerance", "-")}')
        click.echo(f'  超计划比例: {scheme.get("over_plan_ratio", "-")}')
        click.echo(f'  漏读天数: {scheme.get("missing_reading_days", "-")} (约 {scheme.get("missing_reading_hours", "-")} 小时)')

        click.echo('-' * 60)

        s = summary['summary']
        click.echo(f'异常总数: {s["total_anomalies"]}')
        click.echo(f'有效批次: {s["total_batches"]}')
        click.echo(f'已回滚批次: {s["rolled_back_batches"]}')
        click.echo()
        click.echo('复核状态:')
        click.echo(f'  已复核: {s["review_status"]["reviewed"]}')
        click.echo(f'  待复核: {s["review_status"]["not_reviewed"]}')
        click.echo(f'  确认有效: {s["review_status"]["valid"]}')
        click.echo(f'  误报: {s["review_status"]["false_positive"]}')
        click.echo(f'  待调查: {s["review_status"]["needs_investigation"]}')
        click.echo()

        click.echo('按异常类型统计:')
        for item in summary['by_type']:
            click.echo(f'  {item["name"]:<15} ({item["code"]}): {item["count"]:>3} 条')

        click.echo()
        click.echo('按地块统计:')
        for item in summary['by_parcel'][:10]:
            click.echo(f'  {item["parcel_name"]:<15} ({item["parcel_id"]}): {item["count"]:>3} 条')

        click.echo()
        click.echo('按规则版本统计:')
        for item in summary['by_rule_version']:
            click.echo(f'  版本 {item["rule_version"]}: {item["count"]} 条')

        if summary.get('by_threshold_scheme'):
            click.echo()
            click.echo('按阈值方案统计:')
            for item in summary['by_threshold_scheme']:
                click.echo(f'  {item["threshold_scheme_name"]:<15}: {item["count"]:>3} 条')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('web', help='启动Web管理界面')
@click.option('--host', '-h', default='127.0.0.1', help='监听地址')
@click.option('--port', '-p', default=5000, type=int, help='监听端口')
@click.option('--debug/--no-debug', default=False, help='调试模式')
def start_web(host, port, debug):
    """启动Web管理界面"""
    try:
        from .web import app

        click.secho(f'🌐 启动Web服务 http://{host}:{port}', fg='green', bold=True)
        click.echo('按 Ctrl+C 停止服务')
        app.run(host=host, port=port, debug=debug)

    except ImportError as e:
        click.secho('⚠️  缺少Web依赖，请先安装 flask', fg='yellow')
        CliErrorHandler.handle_error(e)
    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('acceptance-test', help='运行验收测试')
def acceptance_test():
    """运行完整的验收测试流程"""
    try:
        from .acceptance_test import run_acceptance_test
        run_acceptance_test()
    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('regression-test', help='运行回归测试')
def regression_test():
    """运行回归测试，验证编码、HTML报告等修复"""
    try:
        from .regression_test import run_regression_tests
        run_regression_tests()
    except Exception as e:
        CliErrorHandler.handle_error(e)


@cli.command('field-mapping', help='查看字段映射配置')
def show_field_mapping():
    """查看字段映射配置"""
    from .config import FIELD_MAPPINGS

    click.echo('📋 字段映射配置')
    click.echo('=' * 60)

    for source_type, mapping in FIELD_MAPPINGS.items():
        type_names = {
            'parcel': '地块台账',
            'meter': '水表读数',
            'plan': '灌溉计划',
            'weather': '天气补录',
        }
        click.echo(f'\n{type_names.get(source_type, source_type)}:')
        for field, column in mapping.items():
            click.echo(f'  {field:<20} -> {column}')

    click.echo()


@cli.command('exception-types', help='查看异常类型定义')
def show_exception_types():
    """查看异常类型定义"""
    click.echo('⚠️  异常类型定义')
    click.echo('=' * 60)

    for code, name in EXCEPTION_TYPES.items():
        desc = {
            'OVER_PLAN': '实际用水量超过计划的120%',
            'METER_BACKWARD': '水表读数小于上一次读数',
            'MISSING_READING': '两次读数间隔超过25小时',
            'DUPLICATE_REPORT': '同一地块同一时间重复上报',
            'UNKNOWN_PARCEL': '地块编号未在台账中登记',
            'MISSING_PARCEL_ID': '记录缺少地块编号',
            'INVALID_DATE': '日期格式无法解析',
            'READING_CONFLICT': '同一时间读数不一致',
            'INVALID_REFERENCE': '引用了不存在的地块编号',
        }.get(code, '')
        click.echo(f'  {code:<20} {name:<15} {desc}')


@cli.group(help='🎛️  阈值方案管理')
def threshold():
    """阈值方案管理命令组"""
    pass


@threshold.command('list', help='列出所有阈值方案')
@click.option('--active-only', is_flag=True, help='只显示启用的方案')
def list_schemes(active_only):
    """列出所有阈值方案"""
    try:
        schemes = threshold_manager.list_schemes(include_inactive=not active_only)

        active = threshold_manager.get_active_scheme()
        click.echo(f'🎛️  阈值方案列表 (共 {len(schemes)} 个方案)')
        click.echo(f'当前启用: [{active["id"]}] {active["name"]}')
        click.echo('-' * 110)
        click.echo(f'{"ID":>4} {"状态":<6} {"名称":<20} {"倒表容差":>8} {"超计划比":>8} {"漏读天数":>8} {"创建人":<10} {"创建时间":<20}')
        click.echo('-' * 110)

        for s in schemes:
            status = '✓ 启用' if s['is_active'] else '  停用'
            status_color = 'green' if s['is_active'] else 'yellow'
            click.secho(f'{s["id"]:>4} ', nl=False)
            click.secho(f'{status:<6} ', fg=status_color, nl=False)
            click.secho(f'{s["name"]:<20} ', nl=False)
            click.echo(f'{s["meter_backward_tolerance"]:>8.4f} {s["over_plan_ratio"]:>8.2f} {s["missing_reading_days"]:>8.2f} {s["created_by"]:<10} {s["created_at"][:19] if s["created_at"] else "":<20}')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@threshold.command('create', help='创建新阈值方案')
@click.option('--name', '-n', required=True, help='方案名称')
@click.option('--meter-backward', '-b', type=float, default=0.01, help='水表倒退容差，默认0.01')
@click.option('--over-plan-ratio', '-r', type=float, default=1.2, help='超计划比例，默认1.2')
@click.option('--missing-reading-days', '-d', type=float, default=1.0, help='漏读天数，默认1.0')
@click.option('--description', '-D', default='', help='方案描述')
@click.option('--by', '-u', default='cli', help='创建人')
def create_scheme(name, meter_backward, over_plan_ratio, missing_reading_days, description, by):
    """创建新阈值方案"""
    try:
        click.echo(f'📝 正在创建阈值方案 "{name}"...')

        scheme = threshold_manager.create_scheme(
            name=name,
            meter_backward_tolerance=meter_backward,
            over_plan_ratio=over_plan_ratio,
            missing_reading_days=missing_reading_days,
            description=description,
            created_by=by
        )

        click.secho(f'✅ 方案创建成功', fg='green', bold=True)
        click.echo(f'  方案ID: {scheme["id"]}')
        click.echo(f'  方案名称: {scheme["name"]}')
        click.echo(f'  水表倒退容差: {scheme["meter_backward_tolerance"]}')
        click.echo(f'  超计划比例: {scheme["over_plan_ratio"]}')
        click.echo(f'  漏读天数: {scheme["missing_reading_days"]} (约 {scheme["missing_reading_hours"]} 小时)')
        if scheme['description']:
            click.echo(f'  描述: {scheme["description"]}')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@threshold.command('enable', help='启用指定阈值方案')
@click.argument('scheme', required=True)
@click.option('--by', '-u', default='cli', help='操作人')
def enable_scheme(scheme, by):
    """
    启用指定阈值方案

    SCHEME: 方案ID或方案名称
    """
    try:
        click.echo(f'🔄 正在启用阈值方案 "{scheme}"...')

        active = threshold_manager.enable_scheme(scheme, operator=by)

        click.secho(f'✅ 方案已启用', fg='green', bold=True)
        click.echo(f'  方案ID: {active["id"]}')
        click.echo(f'  方案名称: {active["name"]}')
        click.echo(f'  水表倒退容差: {active["meter_backward_tolerance"]}')
        click.echo(f'  超计划比例: {active["over_plan_ratio"]}')
        click.echo(f'  漏读天数: {active["missing_reading_days"]} (约 {active["missing_reading_hours"]} 小时)')
        click.secho(f'\n⚠️  提示: 新方案将在下次检测时生效，已存在的异常记录不受影响', fg='yellow')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@threshold.command('export', help='导出阈值方案为JSON')
@click.argument('scheme', required=True)
@click.option('--output', '-o', default=None, help='输出文件路径')
def export_scheme(scheme, output):
    """
    导出阈值方案为JSON文件

    SCHEME: 方案ID或方案名称
    """
    try:
        click.echo(f'📤 正在导出阈值方案 "{scheme}"...')

        export_data, output_path = threshold_manager.export_scheme(scheme, output_path=output)

        click.secho(f'✅ 方案导出成功', fg='green', bold=True)
        click.echo(f'  输出路径: {output_path}')
        click.echo(f'  方案名称: {export_data["scheme"]["name"]}')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@threshold.command('import', help='导入阈值方案')
@click.argument('file_path', type=click.Path(exists=True, readable=True))
@click.option('--overwrite', is_flag=True, help='覆盖同名方案')
@click.option('--rename', '-r', default=None, help='重命名导入的方案')
@click.option('--by', '-u', default='cli', help='操作人')
def import_scheme(file_path, overwrite, rename, by):
    """
    导入阈值方案

    FILE_PATH: JSON文件路径
    """
    try:
        action = '覆盖' if overwrite else '导入'
        if rename:
            click.echo(f'📥 正在{action}阈值方案，将重命名为 "{rename}"...')
        else:
            click.echo(f'📥 正在{action}阈值方案...')

        scheme = threshold_manager.import_scheme(
            input_path=file_path,
            operator=by,
            overwrite=overwrite,
            rename=rename
        )

        click.secho(f'✅ 方案{action}成功', fg='green', bold=True)
        click.echo(f'  方案ID: {scheme["id"]}')
        click.echo(f'  方案名称: {scheme["name"]}')
        click.echo(f'  水表倒退容差: {scheme["meter_backward_tolerance"]}')
        click.echo(f'  超计划比例: {scheme["over_plan_ratio"]}')
        click.echo(f'  漏读天数: {scheme["missing_reading_days"]} (约 {scheme["missing_reading_hours"]} 小时)')
        click.echo(f'  状态: {"启用" if scheme["is_active"] else "停用"}')
        click.echo(f'  创建人: {scheme["created_by"]}')
        if scheme['description']:
            click.echo(f'  描述: {scheme["description"]}')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@threshold.command('show', help='查看方案详情')
@click.argument('scheme', required=True)
def show_scheme(scheme):
    """
    查看方案详情

    SCHEME: 方案ID或方案名称
    """
    try:
        s = threshold_manager.get_scheme(scheme)
        if not s:
            raise ThresholdSchemeNotFoundError(f'方案不存在: {scheme}')

        click.echo(f'📋 阈值方案详情')
        click.echo('=' * 60)
        click.echo(f'  ID: {s["id"]}')
        click.echo(f'  名称: {s["name"]}')
        status = '✓ 启用' if s['is_active'] else '  停用'
        status_color = 'green' if s['is_active'] else 'yellow'
        click.secho(f'  状态: {status}', fg=status_color)
        click.echo(f'  水表倒退容差: {s["meter_backward_tolerance"]}')
        click.echo(f'  超计划比例: {s["over_plan_ratio"]}')
        click.echo(f'  漏读天数: {s["missing_reading_days"]} (约 {s["missing_reading_hours"]} 小时)')
        click.echo(f'  创建人: {s["created_by"]}')
        click.echo(f'  创建时间: {s["created_at"]}')
        if s['description']:
            click.echo(f'  描述: {s["description"]}')

        if s.get('logs'):
            click.echo(f'\n📜 最近操作日志 (最近 {len(s["logs"])} 条):')
            click.echo('-' * 80)
            click.echo(f'{"操作":<8} {"操作人":<10} {"时间":<20} {"详情"}')
            click.echo('-' * 80)
            for log in s['logs']:
                op_name = {
                    'create': '创建',
                    'enable': '启用',
                    'disable': '停用',
                    'import': '导入',
                    'export': '导出',
                    'update': '更新',
                    'delete': '删除',
                }.get(log['operation'], log['operation'])
                details_str = str(log['details'])[:50]
                click.echo(f'{op_name:<8} {log["operator"]:<10} {log["created_at"][:19] if log["created_at"] else "":<20} {details_str}')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@threshold.command('logs', help='查看操作日志')
@click.option('--scheme', '-s', default=None, help='按方案过滤（ID或名称）')
@click.option('--operation', '-o', default=None, help='按操作类型过滤')
@click.option('--limit', '-n', default=50, help='显示数量')
def list_logs(scheme, operation, limit):
    """查看操作日志"""
    try:
        logs = threshold_manager.list_operation_logs(
            scheme_id_or_name=scheme,
            operation=operation,
            limit=limit
        )

        filter_info = []
        if scheme:
            filter_info.append(f'方案: {scheme}')
        if operation:
            filter_info.append(f'操作: {operation}')
        filter_str = f' ({", ".join(filter_info)})' if filter_info else ''

        click.echo(f'📜 阈值方案操作日志{filter_str} (共 {len(logs)} 条)')
        click.echo('-' * 100)
        click.echo(f'{"ID":>4} {"操作":<8} {"方案":<20} {"操作人":<10} {"时间":<20} {"详情"}')
        click.echo('-' * 100)

        for log in logs:
            op_name = {
                'create': '创建',
                'enable': '启用',
                'disable': '停用',
                'import': '导入',
                'export': '导出',
                'update': '更新',
                'delete': '删除',
            }.get(log['operation'], log['operation'])
            op_color = {
                'create': 'green',
                'enable': 'cyan',
                'disable': 'yellow',
                'import': 'blue',
                'export': 'magenta',
                'update': 'yellow',
                'delete': 'red',
            }.get(log['operation'], 'white')
            details_str = str(log['details'])[:40]
            click.echo(f'{log["id"]:>4} ', nl=False)
            click.secho(f'{op_name:<8} ', fg=op_color, nl=False)
            click.echo(f'{log["scheme_name"]:<20} {log["operator"]:<10} {log["created_at"][:19] if log["created_at"] else "":<20} {details_str}')

    except Exception as e:
        CliErrorHandler.handle_error(e)


@threshold.command('delete', help='删除阈值方案')
@click.argument('scheme', required=True)
@click.option('--by', '-u', default='cli', help='操作人')
@click.option('--force', is_flag=True, help='强制删除（不提示）')
def delete_scheme(scheme, by, force):
    """
    删除阈值方案（不能删除启用的和默认的）

    SCHEME: 方案ID或方案名称
    """
    try:
        s = threshold_manager.get_scheme(scheme)
        if not s:
            raise ThresholdSchemeNotFoundError(f'方案不存在: {scheme}')

        if not force:
            click.secho(f'⚠️  您将要删除方案: [{s["id"]}] {s["name"]}', fg='yellow', bold=True)
            click.echo(f'  水表倒退容差: {s["meter_backward_tolerance"]}')
            click.echo(f'  超计划比例: {s["over_plan_ratio"]}')
            click.echo(f'  漏读天数: {s["missing_reading_days"]}')
            click.echo()
            if not click.confirm('确定要删除此方案吗？此操作不可撤销'):
                click.echo('已取消删除')
                return

        click.echo(f'🗑️  正在删除阈值方案 "{scheme}"...')
        threshold_manager.delete_scheme(scheme, operator=by)

        click.secho(f'✅ 方案已删除', fg='green', bold=True)

    except Exception as e:
        CliErrorHandler.handle_error(e)


if __name__ == '__main__':
    cli()
