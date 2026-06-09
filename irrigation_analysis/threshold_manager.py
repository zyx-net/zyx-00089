# -*- coding: utf-8 -*-
"""
阈值方案管理模块
支持阈值方案的创建、列表、启用、导出、导入
"""
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path

from .database import get_db
from .models import ThresholdScheme, ThresholdSchemeLog
from .config import THRESHOLDS


REQUIRED_FIELDS = ['name', 'meter_backward_tolerance', 'over_plan_ratio', 'missing_reading_days']

VALID_OPERATIONS = ['create', 'enable', 'disable', 'import', 'export', 'update', 'delete']


class ThresholdSchemeError(Exception):
    """阈值方案异常基类"""
    pass


class ThresholdSchemeNotFoundError(ThresholdSchemeError):
    """方案不存在"""
    pass


class ThresholdSchemeNameConflictError(ThresholdSchemeError):
    """方案名称冲突"""
    pass


class ThresholdSchemeValidationError(ThresholdSchemeError):
    """方案验证错误"""
    pass


class ThresholdSchemeImportError(ThresholdSchemeError):
    """导入错误"""
    pass


class ThresholdSchemeManager:
    """阈值方案管理器"""

    def __init__(self):
        self._ensure_default_scheme()

    def _ensure_default_scheme(self):
        """确保默认方案存在"""
        with get_db() as db:
            default = db.query(ThresholdScheme).filter(
                ThresholdScheme.name == 'default'
            ).first()

            if not default:
                default = ThresholdScheme(
                    name='default',
                    description='系统默认阈值方案',
                    meter_backward_tolerance=THRESHOLDS.get('meter_backward_tolerance', 0.01),
                    over_plan_ratio=THRESHOLDS.get('over_plan_ratio', 1.2),
                    missing_reading_days=THRESHOLDS.get('missing_reading_hours', 25) / 24.0,
                    is_active=True,
                    created_by='system'
                )
                db.add(default)
                db.flush()

                self._log_operation(
                    db,
                    scheme_id=default.id,
                    scheme_name='default',
                    operation='create',
                    operator='system',
                    details={'from_config': True, 'thresholds': {
                        'meter_backward_tolerance': default.meter_backward_tolerance,
                        'over_plan_ratio': default.over_plan_ratio,
                        'missing_reading_days': default.missing_reading_days,
                    }}
                )

            active = db.query(ThresholdScheme).filter(
                ThresholdScheme.is_active == True
            ).first()

            if not active:
                default.is_active = True
                self._log_operation(
                    db,
                    scheme_id=default.id,
                    scheme_name='default',
                    operation='enable',
                    operator='system',
                    details={'reason': 'no_active_scheme'}
                )

    def _log_operation(self, db, scheme_id: int, scheme_name: str,
                       operation: str, operator: str, details: Dict = None):
        """记录操作日志"""
        log = ThresholdSchemeLog(
            scheme_id=scheme_id,
            scheme_name=scheme_name,
            operation=operation,
            operator=operator,
            details=json.dumps(details or {}, ensure_ascii=False)
        )
        db.add(log)

    def list_schemes(self, include_inactive: bool = True) -> List[Dict]:
        """列出所有方案"""
        with get_db() as db:
            query = db.query(ThresholdScheme)
            if not include_inactive:
                query = query.filter(ThresholdScheme.is_active == True)
            schemes = query.order_by(
                ThresholdScheme.is_active.desc(),
                ThresholdScheme.created_at.desc()
            ).all()
            return [self._scheme_to_dict(s) for s in schemes]

    def get_scheme(self, scheme_id_or_name: Any) -> Optional[Dict]:
        """获取方案详情"""
        with get_db() as db:
            scheme = self._find_scheme(db, scheme_id_or_name)
            if not scheme:
                return None
            return self._scheme_to_dict(scheme, include_logs=True)

    def get_active_scheme(self) -> Dict:
        """获取当前启用的方案"""
        with get_db() as db:
            scheme = db.query(ThresholdScheme).filter(
                ThresholdScheme.is_active == True
            ).first()
            if not scheme:
                raise ThresholdSchemeNotFoundError('没有启用的阈值方案')
            return self._scheme_to_dict(scheme)

    def get_active_thresholds(self) -> Dict:
        """获取当前启用的阈值（兼容格式）"""
        scheme = self.get_active_scheme()
        return {
            'scheme_id': scheme['id'],
            'scheme_name': scheme['name'],
            'meter_backward_tolerance': scheme['meter_backward_tolerance'],
            'over_plan_ratio': scheme['over_plan_ratio'],
            'missing_reading_hours': scheme['missing_reading_days'] * 24,
            'missing_reading_days': scheme['missing_reading_days'],
        }

    def create_scheme(self, name: str, meter_backward_tolerance: float,
                      over_plan_ratio: float, missing_reading_days: float,
                      description: str = '', created_by: str = 'cli') -> Dict:
        """创建新方案"""
        self._validate_thresholds(
            meter_backward_tolerance=meter_backward_tolerance,
            over_plan_ratio=over_plan_ratio,
            missing_reading_days=missing_reading_days
        )

        if not name or len(name.strip()) == 0:
            raise ThresholdSchemeValidationError('方案名称不能为空')

        if len(name) > 100:
            raise ThresholdSchemeValidationError('方案名称不能超过100个字符')

        with get_db() as db:
            existing = db.query(ThresholdScheme).filter(
                ThresholdScheme.name == name
            ).first()
            if existing:
                raise ThresholdSchemeNameConflictError(f'方案名称 "{name}" 已存在')

            scheme = ThresholdScheme(
                name=name.strip(),
                description=description or '',
                meter_backward_tolerance=float(meter_backward_tolerance),
                over_plan_ratio=float(over_plan_ratio),
                missing_reading_days=float(missing_reading_days),
                is_active=False,
                created_by=created_by
            )
            db.add(scheme)
            db.flush()

            self._log_operation(
                db,
                scheme_id=scheme.id,
                scheme_name=scheme.name,
                operation='create',
                operator=created_by,
                details={'thresholds': {
                    'meter_backward_tolerance': scheme.meter_backward_tolerance,
                    'over_plan_ratio': scheme.over_plan_ratio,
                    'missing_reading_days': scheme.missing_reading_days,
                }, 'description': scheme.description}
            )

            return self._scheme_to_dict(scheme)

    def enable_scheme(self, scheme_id_or_name: Any, operator: str = 'cli') -> Dict:
        """启用方案"""
        with get_db() as db:
            scheme = self._find_scheme(db, scheme_id_or_name)
            if not scheme:
                raise ThresholdSchemeNotFoundError(f'方案不存在: {scheme_id_or_name}')

            if scheme.is_active:
                return self._scheme_to_dict(scheme)

            current_active = db.query(ThresholdScheme).filter(
                ThresholdScheme.is_active == True
            ).first()

            if current_active:
                current_active.is_active = False
                self._log_operation(
                    db,
                    scheme_id=current_active.id,
                    scheme_name=current_active.name,
                    operation='disable',
                    operator=operator,
                    details={'reason': f'replaced by scheme #{scheme.id} ({scheme.name})'}
                )

            scheme.is_active = True
            db.flush()

            self._log_operation(
                db,
                scheme_id=scheme.id,
                scheme_name=scheme.name,
                operation='enable',
                operator=operator,
                details={'previous_scheme': current_active.name if current_active else None}
            )

            return self._scheme_to_dict(scheme)

    def delete_scheme(self, scheme_id_or_name: Any, operator: str = 'cli') -> None:
        """删除方案（不能删除启用的和默认的）"""
        with get_db() as db:
            scheme = self._find_scheme(db, scheme_id_or_name)
            if not scheme:
                raise ThresholdSchemeNotFoundError(f'方案不存在: {scheme_id_or_name}')

            if scheme.name == 'default':
                raise ThresholdSchemeValidationError('不能删除默认方案')

            if scheme.is_active:
                raise ThresholdSchemeValidationError('不能删除当前启用的方案，请先切换到其他方案')

            db.query(ThresholdSchemeLog).filter(
                ThresholdSchemeLog.scheme_id == scheme.id
            ).update({'scheme_id': None})

            db.delete(scheme)
            db.flush()

    def export_scheme(self, scheme_id_or_name: Any, output_path: str = None) -> Tuple[Dict, str]:
        """导出方案为JSON文件"""
        scheme = self.get_scheme(scheme_id_or_name)
        if not scheme:
            raise ThresholdSchemeNotFoundError(f'方案不存在: {scheme_id_or_name}')

        export_data = {
            'version': '1.0',
            'exported_at': datetime.now().isoformat(),
            'scheme': {
                'name': scheme['name'],
                'description': scheme['description'],
                'meter_backward_tolerance': scheme['meter_backward_tolerance'],
                'over_plan_ratio': scheme['over_plan_ratio'],
                'missing_reading_days': scheme['missing_reading_days'],
            },
            'metadata': {
                'created_at': scheme['created_at'],
                'created_by': scheme['created_by'],
            }
        }

        if output_path is None:
            safe_name = ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in scheme['name'])
            output_path = str(
                Path(__file__).resolve().parent.parent / 'outputs' / f'scheme_{safe_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        with get_db() as db:
            self._log_operation(
                db,
                scheme_id=scheme['id'],
                scheme_name=scheme['name'],
                operation='export',
                operator='cli',
                details={'output_path': str(output_path)}
            )

        return export_data, str(output_path)

    def import_scheme(self, input_path: str, operator: str = 'cli',
                      overwrite: bool = False, rename: str = None) -> Dict:
        """导入方案

        Args:
            input_path: 导入文件路径
            operator: 操作人
            overwrite: 是否覆盖同名方案
            rename: 重命名导入的方案

        Returns:
            导入的方案字典
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise ThresholdSchemeImportError(f'文件不存在: {input_path}')

        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ThresholdSchemeImportError(f'JSON格式错误: {e}')

        self._validate_import_data(import_data)

        scheme_data = import_data['scheme']
        name = rename.strip() if rename else scheme_data['name'].strip()

        if not name:
            raise ThresholdSchemeImportError('方案名称不能为空')

        if len(name) > 100:
            raise ThresholdSchemeImportError('方案名称不能超过100个字符')

        self._validate_thresholds(
            meter_backward_tolerance=scheme_data['meter_backward_tolerance'],
            over_plan_ratio=scheme_data['over_plan_ratio'],
            missing_reading_days=scheme_data['missing_reading_days']
        )

        with get_db() as db:
            existing = db.query(ThresholdScheme).filter(
                ThresholdScheme.name == name
            ).first()

            if existing and not overwrite:
                raise ThresholdSchemeNameConflictError(
                    f'方案名称 "{name}" 已存在。请使用 --overwrite 覆盖，或使用 --rename 重命名'
                )

            if existing and overwrite:
                if existing.is_active:
                    raise ThresholdSchemeValidationError(
                        '不能覆盖当前启用的方案，请先切换到其他方案'
                    )

                old_thresholds = {
                    'meter_backward_tolerance': existing.meter_backward_tolerance,
                    'over_plan_ratio': existing.over_plan_ratio,
                    'missing_reading_days': existing.missing_reading_days,
                }

                existing.description = scheme_data.get('description', existing.description)
                existing.meter_backward_tolerance = float(scheme_data['meter_backward_tolerance'])
                existing.over_plan_ratio = float(scheme_data['over_plan_ratio'])
                existing.missing_reading_days = float(scheme_data['missing_reading_days'])
                existing.updated_at = datetime.now()

                self._log_operation(
                    db,
                    scheme_id=existing.id,
                    scheme_name=existing.name,
                    operation='update',
                    operator=operator,
                    details={
                        'source': 'import',
                        'source_file': str(input_path),
                        'old_thresholds': old_thresholds,
                        'new_thresholds': {
                            'meter_backward_tolerance': existing.meter_backward_tolerance,
                            'over_plan_ratio': existing.over_plan_ratio,
                            'missing_reading_days': existing.missing_reading_days,
                        }
                    }
                )

                db.flush()
                return self._scheme_to_dict(existing)
            else:
                scheme = ThresholdScheme(
                    name=name,
                    description=scheme_data.get('description', ''),
                    meter_backward_tolerance=float(scheme_data['meter_backward_tolerance']),
                    over_plan_ratio=float(scheme_data['over_plan_ratio']),
                    missing_reading_days=float(scheme_data['missing_reading_days']),
                    is_active=False,
                    created_by=operator
                )
                db.add(scheme)
                db.flush()

                self._log_operation(
                    db,
                    scheme_id=scheme.id,
                    scheme_name=scheme.name,
                    operation='import',
                    operator=operator,
                    details={
                        'source_file': str(input_path),
                        'thresholds': {
                            'meter_backward_tolerance': scheme.meter_backward_tolerance,
                            'over_plan_ratio': scheme.over_plan_ratio,
                            'missing_reading_days': scheme.missing_reading_days,
                        }
                    }
                )

                return self._scheme_to_dict(scheme)

    def list_operation_logs(self, scheme_id_or_name: Any = None,
                            operation: str = None, limit: int = 100) -> List[Dict]:
        """列出操作日志"""
        with get_db() as db:
            query = db.query(ThresholdSchemeLog)

            if scheme_id_or_name is not None:
                scheme = self._find_scheme(db, scheme_id_or_name)
                if scheme:
                    query = query.filter(
                        (ThresholdSchemeLog.scheme_id == scheme.id) |
                        (ThresholdSchemeLog.scheme_name == scheme.name)
                    )
                else:
                    scheme_name = str(scheme_id_or_name)
                    query = query.filter(ThresholdSchemeLog.scheme_name == scheme_name)

            if operation:
                if operation not in VALID_OPERATIONS:
                    raise ThresholdSchemeValidationError(
                        f'无效的操作类型: {operation}。有效值: {VALID_OPERATIONS}'
                    )
                query = query.filter(ThresholdSchemeLog.operation == operation)

            logs = query.order_by(ThresholdSchemeLog.created_at.desc()).limit(limit).all()
            return [self._log_to_dict(log) for log in logs]

    def _validate_import_data(self, import_data: Dict) -> None:
        """验证导入数据格式"""
        if not isinstance(import_data, dict):
            raise ThresholdSchemeImportError('导入数据格式错误，应为JSON对象')

        if 'scheme' not in import_data:
            raise ThresholdSchemeImportError('缺少必填字段: scheme')

        scheme_data = import_data['scheme']
        if not isinstance(scheme_data, dict):
            raise ThresholdSchemeImportError('scheme 字段必须是对象')

        missing_fields = [f for f in REQUIRED_FIELDS if f not in scheme_data]
        if missing_fields:
            raise ThresholdSchemeImportError(
                f'方案数据缺少必填字段: {", ".join(missing_fields)}'
            )

    def _validate_thresholds(self, meter_backward_tolerance: float,
                             over_plan_ratio: float,
                             missing_reading_days: float) -> None:
        """验证阈值参数"""
        try:
            meter_backward_tolerance = float(meter_backward_tolerance)
            over_plan_ratio = float(over_plan_ratio)
            missing_reading_days = float(missing_reading_days)
        except (TypeError, ValueError):
            raise ThresholdSchemeValidationError('阈值必须是数值类型')

        if meter_backward_tolerance < 0:
            raise ThresholdSchemeValidationError(
                f'水表倒退容差不能为负数: {meter_backward_tolerance}'
            )
        if meter_backward_tolerance > 1000:
            raise ThresholdSchemeValidationError(
                f'水表倒退容差过大: {meter_backward_tolerance}，合理范围: 0-1000'
            )

        if over_plan_ratio <= 1.0:
            raise ThresholdSchemeValidationError(
                f'超计划比例必须大于1.0: {over_plan_ratio}'
            )
        if over_plan_ratio > 10.0:
            raise ThresholdSchemeValidationError(
                f'超计划比例过大: {over_plan_ratio}，合理范围: 1.0-10.0'
            )

        if missing_reading_days <= 0:
            raise ThresholdSchemeValidationError(
                f'漏读天数必须大于0: {missing_reading_days}'
            )
        if missing_reading_days > 365:
            raise ThresholdSchemeValidationError(
                f'漏读天数过大: {missing_reading_days}，合理范围: 0-365'
            )

    def _find_scheme(self, db, scheme_id_or_name: Any) -> Optional[ThresholdScheme]:
        """根据ID或名称查找方案"""
        if isinstance(scheme_id_or_name, int):
            return db.query(ThresholdScheme).filter(
                ThresholdScheme.id == scheme_id_or_name
            ).first()

        scheme_id_str = str(scheme_id_or_name)
        if scheme_id_str.isdigit():
            scheme = db.query(ThresholdScheme).filter(
                ThresholdScheme.id == int(scheme_id_str)
            ).first()
            if scheme:
                return scheme

        return db.query(ThresholdScheme).filter(
            ThresholdScheme.name == scheme_id_str
        ).first()

    def _scheme_to_dict(self, scheme: ThresholdScheme, include_logs: bool = False) -> Dict:
        """转换方案为字典"""
        result = {
            'id': scheme.id,
            'name': scheme.name,
            'description': scheme.description,
            'meter_backward_tolerance': scheme.meter_backward_tolerance,
            'over_plan_ratio': scheme.over_plan_ratio,
            'missing_reading_days': scheme.missing_reading_days,
            'missing_reading_hours': round(scheme.missing_reading_days * 24, 2),
            'is_active': scheme.is_active,
            'created_by': scheme.created_by,
            'created_at': scheme.created_at.isoformat() if scheme.created_at else None,
            'updated_at': scheme.updated_at.isoformat() if scheme.updated_at else None,
        }

        if include_logs:
            with get_db() as db:
                logs = db.query(ThresholdSchemeLog).filter(
                    ThresholdSchemeLog.scheme_id == scheme.id
                ).order_by(ThresholdSchemeLog.created_at.desc()).limit(20).all()
                result['logs'] = [self._log_to_dict(log) for log in logs]

        return result

    def _log_to_dict(self, log: ThresholdSchemeLog) -> Dict:
        """转换日志为字典"""
        try:
            details = json.loads(log.details) if log.details else {}
        except (json.JSONDecodeError, TypeError):
            details = {'raw': log.details}

        return {
            'id': log.id,
            'scheme_id': log.scheme_id,
            'scheme_name': log.scheme_name,
            'operation': log.operation,
            'operator': log.operator,
            'details': details,
            'created_at': log.created_at.isoformat() if log.created_at else None,
        }


_threshold_manager_instance = None


def get_threshold_manager():
    """获取阈值方案管理器实例（懒加载）"""
    global _threshold_manager_instance
    if _threshold_manager_instance is None:
        _threshold_manager_instance = ThresholdSchemeManager()
    return _threshold_manager_instance


class _LazyThresholdManager:
    """懒加载包装器"""
    def __getattr__(self, name):
        return getattr(get_threshold_manager(), name)


threshold_manager = _LazyThresholdManager()
