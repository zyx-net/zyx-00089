# -*- coding: utf-8 -*-
"""
数据修正规则沙盒管理器
"""
import json
import uuid
import csv
import io
import os
import zipfile
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from sqlalchemy import and_
import pandas as pd

from .database import get_db
from .models import (
    Sandbox, SandboxSample, SandboxRule, SandboxTrial, SandboxTrialResult,
    SandboxPromotion, SandboxConflict, SandboxLog, Batch, MeterReading,
    IrrigationPlan, WeatherRecord
)
from .config import FIELD_MAPPINGS


class SandboxError(Exception):
    """沙盒基础异常"""
    pass


class SandboxNotFoundError(SandboxError):
    """沙盒不存在"""
    pass


class SandboxRuleError(SandboxError):
    """规则错误"""
    pass


class SandboxTrialError(SandboxError):
    """试跑错误"""
    pass


class SandboxConflictError(SandboxError):
    """冲突错误"""
    pass


class SandboxPromotionError(SandboxError):
    """提升错误"""
    pass


class SandboxManager:
    """沙盒管理器"""

    RULE_TYPES = ['field_mapping', 'missing_fill', 'outlier_replace', 'custom']
    STATUSES = ['draft', 'testing', 'approved', 'applied', 'archived', 'rolled_back']
    CHANGE_TYPES = ['modified', 'added', 'deleted', 'unchanged']

    def _generate_no(self, prefix: str) -> str:
        """生成编号"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f'{prefix}_{timestamp}_{uuid.uuid4().hex[:8]}'

    def _log(self, sandbox_id: int, operation: str, operator: str, details: Dict = None) -> None:
        """记录操作日志"""
        with get_db() as db:
            log = SandboxLog(
                sandbox_id=sandbox_id,
                operation=operation,
                operator=operator,
                details=json.dumps(details, ensure_ascii=False) if details else None
            )
            db.add(log)

    def _find_sandbox(self, db, sandbox_id_or_no: Any) -> Optional[Sandbox]:
        """根据ID或编号查找沙盒"""
        if isinstance(sandbox_id_or_no, int):
            return db.query(Sandbox).filter(Sandbox.id == sandbox_id_or_no).first()
        sandbox_str = str(sandbox_id_or_no)
        if sandbox_str.isdigit():
            sandbox = db.query(Sandbox).filter(Sandbox.id == int(sandbox_str)).first()
            if sandbox:
                return sandbox
        return db.query(Sandbox).filter(Sandbox.sandbox_no == sandbox_str).first()

    def create_sandbox(self, name: str, description: str = '', source_dataset: str = None,
                       source_batch_id: Any = None, created_by: str = 'cli') -> Dict:
        """创建沙盒"""
        with get_db() as db:
            sandbox = Sandbox(
                sandbox_no=self._generate_no('SBX'),
                name=name,
                description=description,
                source_dataset=source_dataset,
                status='draft',
                created_by=created_by
            )

            if source_batch_id is not None:
                if isinstance(source_batch_id, int) or str(source_batch_id).isdigit():
                    sandbox.source_batch_id = int(source_batch_id)
                else:
                    batch = db.query(Batch).filter(Batch.batch_no == str(source_batch_id)).first()
                    if batch:
                        sandbox.source_batch_id = batch.id

            db.add(sandbox)
            db.flush()
            sandbox_id = sandbox.id

        self._log(sandbox_id, 'create', created_by, {
            'name': name,
            'description': description,
            'source_dataset': source_dataset
        })

        return self.get_sandbox(sandbox_id)

    def list_sandboxes(self, status: str = None, created_by: str = None, limit: int = 100) -> List[Dict]:
        """列出沙盒"""
        with get_db() as db:
            query = db.query(Sandbox).order_by(Sandbox.created_at.desc())
            if status:
                query = query.filter(Sandbox.status == status)
            if created_by:
                query = query.filter(Sandbox.created_by == created_by)
            sandboxes = query.limit(limit).all()
            return [self._sandbox_to_dict(s, db) for s in sandboxes]

    def get_sandbox(self, sandbox_id_or_no: Any, include_details: bool = False) -> Optional[Dict]:
        """获取沙盒详情"""
        with get_db() as db:
            sandbox = self._find_sandbox(db, sandbox_id_or_no)
            if not sandbox:
                return None
            return self._sandbox_to_dict(sandbox, db, include_details=include_details)

    def _sandbox_to_dict(self, sandbox: Sandbox, db, include_details: bool = False) -> Dict:
        """转换沙盒为字典"""
        result = {
            'id': sandbox.id,
            'sandbox_no': sandbox.sandbox_no,
            'name': sandbox.name,
            'description': sandbox.description,
            'source_dataset': sandbox.source_dataset,
            'source_batch_id': sandbox.source_batch_id,
            'status': sandbox.status,
            'created_by': sandbox.created_by,
            'created_at': sandbox.created_at.isoformat() if sandbox.created_at else None,
            'updated_at': sandbox.updated_at.isoformat() if sandbox.updated_at else None,
            'last_trial_id': sandbox.last_trial_id,
        }

        if include_details:
            sample_count = db.query(SandboxSample).filter(
                SandboxSample.sandbox_id == sandbox.id
            ).count()
            rule_count = db.query(SandboxRule).filter(
                SandboxRule.sandbox_id == sandbox.id,
                SandboxRule.is_active == True
            ).count()
            trial_count = db.query(SandboxTrial).filter(
                SandboxTrial.sandbox_id == sandbox.id
            ).count()
            log_count = db.query(SandboxLog).filter(
                SandboxLog.sandbox_id == sandbox.id
            ).count()

            last_trial = None
            if sandbox.last_trial_id:
                last_trial = db.query(SandboxTrial).filter(
                    SandboxTrial.id == sandbox.last_trial_id
                ).first()

            result.update({
                'sample_count': sample_count,
                'rule_count': rule_count,
                'trial_count': trial_count,
                'log_count': log_count,
                'last_trial': self._trial_to_dict(last_trial) if last_trial else None,
            })

        return result

    def update_sandbox(self, sandbox_id_or_no: Any, name: str = None, description: str = None,
                       status: str = None, operator: str = 'cli') -> Dict:
        """更新沙盒"""
        with get_db() as db:
            sandbox = self._find_sandbox(db, sandbox_id_or_no)
            if not sandbox:
                raise SandboxNotFoundError(f'沙盒不存在: {sandbox_id_or_no}')

            sandbox_id = sandbox.id

            if name is not None:
                sandbox.name = name
            if description is not None:
                sandbox.description = description
            if status is not None and status in self.STATUSES:
                sandbox.status = status

            sandbox.updated_at = datetime.now()

        self._log(sandbox_id, 'update', operator, {
            'name': name,
            'description': description,
            'status': status
        })

        return self.get_sandbox(sandbox_id)

    def delete_sandbox(self, sandbox_id_or_no: Any, operator: str = 'cli') -> None:
        """删除沙盒"""
        with get_db() as db:
            sandbox = self._find_sandbox(db, sandbox_id_or_no)
            if not sandbox:
                raise SandboxNotFoundError(f'沙盒不存在: {sandbox_id_or_no}')

            sandbox_id = sandbox.id
            sandbox_no = sandbox.sandbox_no

            db.query(SandboxTrialResult).filter(
                SandboxTrialResult.trial_id.in_(
                    db.query(SandboxTrial.id).filter(SandboxTrial.sandbox_id == sandbox_id)
                )
            ).delete(synchronize_session=False)

            db.query(SandboxTrial).filter(SandboxTrial.sandbox_id == sandbox_id).delete()
            db.query(SandboxRule).filter(SandboxRule.sandbox_id == sandbox_id).delete()
            db.query(SandboxSample).filter(SandboxSample.sandbox_id == sandbox_id).delete()
            db.query(SandboxConflict).filter(
                SandboxConflict.promotion_id.in_(
                    db.query(SandboxPromotion.id).filter(SandboxPromotion.sandbox_id == sandbox_id)
                )
            ).delete(synchronize_session=False)
            db.query(SandboxPromotion).filter(SandboxPromotion.sandbox_id == sandbox_id).delete()
            db.query(SandboxLog).filter(SandboxLog.sandbox_id == sandbox_id).delete()

            db.delete(sandbox)

        self._log(sandbox_id, 'delete', operator, {'sandbox_no': sandbox_no})

    def import_sample(self, sandbox_id_or_no: Any, file_path: str, source_type: str,
                      sample_name: str = None, operator: str = 'cli') -> Dict:
        """导入样例数据（CSV或JSON）"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f'文件不存在: {file_path}')

        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.csv':
            df = pd.read_csv(file_path, dtype=str)
        elif ext == '.json':
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            df = pd.DataFrame(data)
        else:
            raise ValueError(f'不支持的文件格式: {ext}，仅支持 .csv 和 .json')

        sample_data = df.to_json(orient='records', force_ascii=False)

        if not sample_name:
            sample_name = os.path.basename(file_path)

        with get_db() as db:
            sandbox = self._find_sandbox(db, sandbox_id_or_no)
            if not sandbox:
                raise SandboxNotFoundError(f'沙盒不存在: {sandbox_id_or_no}')

            sandbox_id = sandbox.id

            sample = SandboxSample(
                sandbox_id=sandbox_id,
                sample_name=sample_name,
                source_type=source_type,
                source_file=file_path,
                row_count=len(df),
                sample_data=sample_data,
                created_by=operator
            )
            db.add(sample)
            db.flush()
            sample_id = sample.id

        self._log(sandbox_id, 'import_sample', operator, {
            'sample_name': sample_name,
            'source_type': source_type,
            'file_path': file_path,
            'row_count': len(df)
        })

        return self.get_sample(sample_id)

    def list_samples(self, sandbox_id_or_no: Any) -> List[Dict]:
        """列出样例数据"""
        with get_db() as db:
            sandbox = self._find_sandbox(db, sandbox_id_or_no)
            if not sandbox:
                raise SandboxNotFoundError(f'沙盒不存在: {sandbox_id_or_no}')

            samples = db.query(SandboxSample).filter(
                SandboxSample.sandbox_id == sandbox.id
            ).order_by(SandboxSample.created_at.desc()).all()

            return [self._sample_to_dict(s) for s in samples]

    def get_sample(self, sample_id: int) -> Optional[Dict]:
        """获取样例详情"""
        with get_db() as db:
            sample = db.query(SandboxSample).filter(SandboxSample.id == sample_id).first()
            if not sample:
                return None
            return self._sample_to_dict(sample, include_data=True)

    def _sample_to_dict(self, sample: SandboxSample, include_data: bool = False) -> Dict:
        """转换样例为字典"""
        result = {
            'id': sample.id,
            'sandbox_id': sample.sandbox_id,
            'sample_name': sample.sample_name,
            'source_type': sample.source_type,
            'source_file': sample.source_file,
            'row_count': sample.row_count,
            'created_by': sample.created_by,
            'created_at': sample.created_at.isoformat() if sample.created_at else None,
        }
        if include_data:
            result['data'] = json.loads(sample.sample_data)
        return result

    def add_rule(self, sandbox_id_or_no: Any, rule_type: str, rule_name: str,
                 source_field: str = None, target_field: str = None,
                 condition: str = None, replacement: str = None,
                 fill_value: str = None, mapping_data: Dict = None,
                 priority: int = 0, operator: str = 'cli') -> Dict:
        """添加修正规则"""
        if rule_type not in self.RULE_TYPES:
            raise SandboxRuleError(f'不支持的规则类型: {rule_type}，支持: {self.RULE_TYPES}')

        with get_db() as db:
            sandbox = self._find_sandbox(db, sandbox_id_or_no)
            if not sandbox:
                raise SandboxNotFoundError(f'沙盒不存在: {sandbox_id_or_no}')

            sandbox_id = sandbox.id

            rule = SandboxRule(
                sandbox_id=sandbox_id,
                rule_type=rule_type,
                rule_name=rule_name,
                source_field=source_field,
                target_field=target_field,
                condition=condition,
                replacement=replacement,
                fill_value=fill_value,
                mapping_data=json.dumps(mapping_data, ensure_ascii=False) if mapping_data else None,
                priority=priority,
                created_by=operator
            )
            db.add(rule)
            db.flush()
            rule_id = rule.id

        self._log(sandbox_id, 'add_rule', operator, {
            'rule_id': rule_id,
            'rule_type': rule_type,
            'rule_name': rule_name
        })

        return self.get_rule(rule_id)

    def list_rules(self, sandbox_id_or_no: Any, rule_type: str = None) -> List[Dict]:
        """列出规则"""
        with get_db() as db:
            sandbox = self._find_sandbox(db, sandbox_id_or_no)
            if not sandbox:
                raise SandboxNotFoundError(f'沙盒不存在: {sandbox_id_or_no}')

            query = db.query(SandboxRule).filter(
                SandboxRule.sandbox_id == sandbox.id,
                SandboxRule.is_active == True
            )
            if rule_type:
                query = query.filter(SandboxRule.rule_type == rule_type)

            rules = query.order_by(SandboxRule.priority.desc(), SandboxRule.created_at.asc()).all()
            return [self._rule_to_dict(r) for r in rules]

    def get_rule(self, rule_id: int) -> Optional[Dict]:
        """获取规则详情"""
        with get_db() as db:
            rule = db.query(SandboxRule).filter(SandboxRule.id == rule_id).first()
            if not rule:
                return None
            return self._rule_to_dict(rule)

    def _rule_to_dict(self, rule: SandboxRule) -> Dict:
        """转换规则为字典"""
        return {
            'id': rule.id,
            'sandbox_id': rule.sandbox_id,
            'rule_type': rule.rule_type,
            'rule_name': rule.rule_name,
            'source_field': rule.source_field,
            'target_field': rule.target_field,
            'condition': rule.condition,
            'replacement': rule.replacement,
            'fill_value': rule.fill_value,
            'mapping_data': json.loads(rule.mapping_data) if rule.mapping_data else None,
            'priority': rule.priority,
            'is_active': rule.is_active,
            'created_by': rule.created_by,
            'created_at': rule.created_at.isoformat() if rule.created_at else None,
            'updated_at': rule.updated_at.isoformat() if rule.updated_at else None,
        }

    def update_rule(self, rule_id: int, rule_name: str = None, source_field: str = None,
                    target_field: str = None, condition: str = None, replacement: str = None,
                    fill_value: str = None, mapping_data: Dict = None,
                    priority: int = None, is_active: bool = None, operator: str = 'cli') -> Dict:
        """更新规则"""
        with get_db() as db:
            rule = db.query(SandboxRule).filter(SandboxRule.id == rule_id).first()
            if not rule:
                raise SandboxRuleError(f'规则不存在: {rule_id}')

            sandbox_id = rule.sandbox_id

            if rule_name is not None:
                rule.rule_name = rule_name
            if source_field is not None:
                rule.source_field = source_field
            if target_field is not None:
                rule.target_field = target_field
            if condition is not None:
                rule.condition = condition
            if replacement is not None:
                rule.replacement = replacement
            if fill_value is not None:
                rule.fill_value = fill_value
            if mapping_data is not None:
                rule.mapping_data = json.dumps(mapping_data, ensure_ascii=False)
            if priority is not None:
                rule.priority = priority
            if is_active is not None:
                rule.is_active = is_active

            rule.updated_at = datetime.now()

        self._log(sandbox_id, 'update_rule', operator, {'rule_id': rule_id})

        return self.get_rule(rule_id)

    def delete_rule(self, rule_id: int, operator: str = 'cli') -> None:
        """删除规则"""
        with get_db() as db:
            rule = db.query(SandboxRule).filter(SandboxRule.id == rule_id).first()
            if not rule:
                raise SandboxRuleError(f'规则不存在: {rule_id}')

            sandbox_id = rule.sandbox_id
            db.query(SandboxTrialResult).filter(SandboxTrialResult.rule_id == rule_id).delete()
            db.delete(rule)

        self._log(sandbox_id, 'delete_rule', operator, {'rule_id': rule_id})

    def _apply_field_mapping(self, row: Dict, rule: SandboxRule) -> Tuple[Dict, List[Dict]]:
        """应用字段映射规则"""
        changes = []
        if not rule.source_field or not rule.target_field:
            return row, changes

        if rule.source_field in row and row[rule.source_field] is not None:
            old_value = str(row[rule.target_field]) if rule.target_field in row else None
            new_value = str(row[rule.source_field])

            if old_value != new_value:
                row[rule.target_field] = new_value
                changes.append({
                    'change_type': 'modified',
                    'field_name': rule.target_field,
                    'old_value': old_value,
                    'new_value': new_value,
                    'rule_id': rule.id
                })

        return row, changes

    def _apply_missing_fill(self, row: Dict, rule: SandboxRule) -> Tuple[Dict, List[Dict]]:
        """应用缺失值填补规则"""
        changes = []
        if not rule.target_field:
            return row, changes

        value = row.get(rule.target_field)
        needs_fill = False

        if value is None or (isinstance(value, str) and value.strip() == '') or (isinstance(value, float) and pd.isna(value)):
            needs_fill = True

        if rule.condition:
            try:
                condition_env = {**row, 'pd': pd}
                if not eval(rule.condition, {"__builtins__": {}}, condition_env):
                    needs_fill = False
            except Exception:
                pass

        if needs_fill and rule.fill_value is not None:
            old_value = str(value) if value is not None else ''
            new_value = rule.fill_value

            if old_value != new_value:
                row[rule.target_field] = new_value
                changes.append({
                    'change_type': 'modified',
                    'field_name': rule.target_field,
                    'old_value': old_value,
                    'new_value': new_value,
                    'rule_id': rule.id
                })

        return row, changes

    def _apply_outlier_replace(self, row: Dict, rule: SandboxRule) -> Tuple[Dict, List[Dict]]:
        """应用异常值改写规则"""
        changes = []
        if not rule.target_field:
            return row, changes

        value = row.get(rule.target_field)
        if value is None:
            return row, changes

        should_replace = False

        if rule.condition:
            try:
                condition_env = {**row, 'pd': pd, 'value': value}
                if eval(rule.condition, {"__builtins__": {}}, condition_env):
                    should_replace = True
            except Exception:
                pass

        if should_replace and rule.replacement is not None:
            old_value = str(value)
            new_value = rule.replacement

            if rule.mapping_data:
                try:
                    mapping = json.loads(rule.mapping_data)
                    if old_value in mapping:
                        new_value = str(mapping[old_value])
                except Exception:
                    pass

            if old_value != new_value:
                row[rule.target_field] = new_value
                changes.append({
                    'change_type': 'modified',
                    'field_name': rule.target_field,
                    'old_value': old_value,
                    'new_value': new_value,
                    'rule_id': rule.id
                })

        return row, changes

    def _apply_custom_rule(self, row: Dict, rule: SandboxRule) -> Tuple[Dict, List[Dict]]:
        """应用自定义规则"""
        changes = []
        if not rule.condition or not rule.replacement:
            return row, changes

        try:
            condition_env = {**row, 'pd': pd}
            if eval(rule.condition, {"__builtins__": {}}, condition_env):
                exec_env = {'row': row, 'pd': pd, 'changes': []}
                exec(rule.replacement, {"__builtins__": {}}, exec_env)
                new_changes = exec_env.get('changes', [])
                for c in new_changes:
                    c['rule_id'] = rule.id
                changes.extend(new_changes)
        except Exception as e:
            changes.append({
                'change_type': 'error',
                'field_name': rule.target_field or 'unknown',
                'old_value': None,
                'new_value': str(e),
                'rule_id': rule.id
            })

        return row, changes

    def run_trial(self, sandbox_id_or_no: Any, operator: str = 'cli') -> Dict:
        """执行试跑"""
        with get_db() as db:
            sandbox = self._find_sandbox(db, sandbox_id_or_no)
            if not sandbox:
                raise SandboxNotFoundError(f'沙盒不存在: {sandbox_id_or_no}')

            sandbox_id = sandbox.id

            samples = db.query(SandboxSample).filter(
                SandboxSample.sandbox_id == sandbox_id
            ).all()

            if not samples:
                raise SandboxTrialError('沙盒中没有样例数据，请先导入样例')

            rules = db.query(SandboxRule).filter(
                SandboxRule.sandbox_id == sandbox_id,
                SandboxRule.is_active == True
            ).order_by(SandboxRule.priority.desc(), SandboxRule.created_at.asc()).all()

            if not rules:
                raise SandboxTrialError('沙盒中没有激活的规则，请先添加规则')

            trial = SandboxTrial(
                trial_no=self._generate_no('TRL'),
                sandbox_id=sandbox_id,
                status='running',
                executed_by=operator
            )
            db.add(trial)
            db.flush()
            trial_id = trial.id

            total_rows = 0
            affected_rows = 0
            unchanged_rows = 0
            error_count = 0
            all_results = []

            try:
                for sample in samples:
                    sample_data = json.loads(sample.sample_data)
                    total_rows += len(sample_data)

                    for row_idx, row in enumerate(sample_data):
                        row_before = dict(row)
                        row_after = dict(row)
                        row_changes = []

                        for rule in rules:
                            try:
                                if rule.rule_type == 'field_mapping':
                                    row_after, changes = self._apply_field_mapping(row_after, rule)
                                elif rule.rule_type == 'missing_fill':
                                    row_after, changes = self._apply_missing_fill(row_after, rule)
                                elif rule.rule_type == 'outlier_replace':
                                    row_after, changes = self._apply_outlier_replace(row_after, rule)
                                elif rule.rule_type == 'custom':
                                    row_after, changes = self._apply_custom_rule(row_after, rule)
                                else:
                                    changes = []

                                for c in changes:
                                    if c.get('change_type') == 'error':
                                        error_count += 1
                                    c['sample_id'] = sample.id
                                    c['row_index'] = row_idx
                                    c['row_data_before'] = json.dumps(row_before, ensure_ascii=False)
                                    c['row_data_after'] = json.dumps(row_after, ensure_ascii=False)
                                row_changes.extend(changes)

                            except Exception as e:
                                error_count += 1
                                row_changes.append({
                                    'sample_id': sample.id,
                                    'row_index': row_idx,
                                    'change_type': 'error',
                                    'field_name': 'unknown',
                                    'old_value': None,
                                    'new_value': str(e),
                                    'rule_id': rule.id,
                                    'row_data_before': json.dumps(row_before, ensure_ascii=False),
                                    'row_data_after': json.dumps(row_after, ensure_ascii=False),
                                })

                        if row_changes:
                            has_error = any(c.get('change_type') == 'error' for c in row_changes)
                            if not has_error:
                                affected_rows += 1
                            all_results.extend(row_changes)
                        else:
                            unchanged_rows += 1

                for result in all_results:
                    db_result = SandboxTrialResult(
                        trial_id=trial_id,
                        sample_id=result.get('sample_id'),
                        row_index=result.get('row_index'),
                        change_type=result.get('change_type'),
                        field_name=result.get('field_name'),
                        old_value=result.get('old_value'),
                        new_value=result.get('new_value'),
                        rule_id=result.get('rule_id'),
                        row_data_before=result.get('row_data_before'),
                        row_data_after=result.get('row_data_after'),
                    )
                    db.add(db_result)

                trial.status = 'completed'
                trial.total_rows = total_rows
                trial.affected_rows = affected_rows
                trial.unchanged_rows = unchanged_rows
                trial.error_count = error_count
                trial.completed_at = datetime.now()

                summary = {
                    'total_rows': total_rows,
                    'affected_rows': affected_rows,
                    'unchanged_rows': unchanged_rows,
                    'error_count': error_count,
                    'rules_applied': len(rules),
                    'samples_processed': len(samples),
                }
                trial.summary = json.dumps(summary, ensure_ascii=False)

                sandbox.last_trial_id = trial_id
                sandbox.updated_at = datetime.now()
                if sandbox.status == 'draft':
                    sandbox.status = 'testing'

            except Exception as e:
                trial.status = 'failed'
                trial.summary = json.dumps({'error': str(e)}, ensure_ascii=False)
                raise SandboxTrialError(f'试跑失败: {e}')

        self._log(sandbox_id, 'run_trial', operator, {
            'trial_id': trial_id,
            'total_rows': total_rows,
            'affected_rows': affected_rows,
        })

        return self.get_trial(trial_id)

    def list_trials(self, sandbox_id_or_no: Any, limit: int = 20) -> List[Dict]:
        """列出试跑记录"""
        with get_db() as db:
            sandbox = self._find_sandbox(db, sandbox_id_or_no)
            if not sandbox:
                raise SandboxNotFoundError(f'沙盒不存在: {sandbox_id_or_no}')

            trials = db.query(SandboxTrial).filter(
                SandboxTrial.sandbox_id == sandbox.id
            ).order_by(SandboxTrial.executed_at.desc()).limit(limit).all()

            return [self._trial_to_dict(t) for t in trials]

    def get_trial(self, trial_id: int, include_results: bool = False, limit_results: int = 100) -> Optional[Dict]:
        """获取试跑详情"""
        with get_db() as db:
            trial = db.query(SandboxTrial).filter(SandboxTrial.id == trial_id).first()
            if not trial:
                return None

            result = self._trial_to_dict(trial)

            if include_results:
                results = db.query(SandboxTrialResult).filter(
                    SandboxTrialResult.trial_id == trial_id
                ).limit(limit_results).all()
                result['results'] = [self._trial_result_to_dict(r) for r in results]

                by_change_type = {}
                for r in results:
                    ct = r.change_type
                    by_change_type[ct] = by_change_type.get(ct, 0) + 1
                result['by_change_type'] = by_change_type

            return result

    def _trial_to_dict(self, trial: SandboxTrial) -> Dict:
        """转换试跑为字典"""
        return {
            'id': trial.id,
            'trial_no': trial.trial_no,
            'sandbox_id': trial.sandbox_id,
            'status': trial.status,
            'total_rows': trial.total_rows,
            'affected_rows': trial.affected_rows,
            'unchanged_rows': trial.unchanged_rows,
            'error_count': trial.error_count,
            'summary': json.loads(trial.summary) if trial.summary else None,
            'executed_by': trial.executed_by,
            'executed_at': trial.executed_at.isoformat() if trial.executed_at else None,
            'completed_at': trial.completed_at.isoformat() if trial.completed_at else None,
        }

    def _trial_result_to_dict(self, result: SandboxTrialResult) -> Dict:
        """转换试跑结果为字典"""
        return {
            'id': result.id,
            'trial_id': result.trial_id,
            'sample_id': result.sample_id,
            'row_index': result.row_index,
            'change_type': result.change_type,
            'field_name': result.field_name,
            'old_value': result.old_value,
            'new_value': result.new_value,
            'rule_id': result.rule_id,
            'row_data_before': json.loads(result.row_data_before) if result.row_data_before else None,
            'row_data_after': json.loads(result.row_data_after) if result.row_data_after else None,
        }

    def _detect_conflicts(self, db, sandbox: Sandbox, trial: SandboxTrial, target_batch_id: int) -> List[Dict]:
        """检测冲突"""
        conflicts = []

        results = db.query(SandboxTrialResult).filter(
            SandboxTrialResult.trial_id == trial.id,
            SandboxTrialResult.change_type == 'modified'
        ).all()

        table_model_map = {
            'meter': MeterReading,
            'plan': IrrigationPlan,
            'weather': WeatherRecord,
        }

        for result in results:
            if not result.row_data_after or not result.row_data_before:
                continue

            try:
                row_after = json.loads(result.row_data_after)
            except Exception:
                continue

            sample = db.query(SandboxSample).filter(SandboxSample.id == result.sample_id).first()
            if not sample:
                continue

            model = table_model_map.get(sample.source_type)
            if not model:
                continue

            record = None
            if hasattr(model, 'parcel_id') and 'parcel_id' in row_after:
                parcel_id = row_after.get('parcel_id')

                if sample.source_type == 'meter' and 'read_date' in row_after:
                    record = db.query(model).filter(
                        model.parcel_id == parcel_id,
                        model.batch_id == target_batch_id
                    ).first()
                elif sample.source_type == 'plan' and 'plan_date' in row_after:
                    record = db.query(model).filter(
                        model.parcel_id == parcel_id,
                        model.batch_id == target_batch_id
                    ).first()

            if record:
                field_name = result.field_name
                if hasattr(record, field_name):
                    existing_value = str(getattr(record, field_name)) if getattr(record, field_name) is not None else ''
                    proposed_value = str(result.new_value) if result.new_value is not None else ''

                    if existing_value != proposed_value and existing_value != '':
                        conflicts.append({
                            'conflict_type': 'value_mismatch',
                            'target_record_id': record.id,
                            'target_table': model.__tablename__,
                            'field_name': field_name,
                            'existing_value': existing_value,
                            'proposed_value': proposed_value,
                            'last_modified_at': record.created_at.isoformat() if hasattr(record, 'created_at') and record.created_at else None,
                        })

        return conflicts

    def promote_to_production(self, sandbox_id_or_no: Any, trial_id: int, target_batch_id: Any = None,
                              force: bool = False, operator: str = 'cli') -> Dict:
        """提升试跑为正式修正"""
        with get_db() as db:
            sandbox = self._find_sandbox(db, sandbox_id_or_no)
            if not sandbox:
                raise SandboxNotFoundError(f'沙盒不存在: {sandbox_id_or_no}')

            sandbox_id = sandbox.id

            trial = db.query(SandboxTrial).filter(SandboxTrial.id == trial_id).first()
            if not trial:
                raise SandboxTrialError(f'试跑不存在: {trial_id}')

            if trial.status != 'completed':
                raise SandboxTrialError(f'试跑未完成，当前状态: {trial.status}')

            if target_batch_id is None and sandbox.source_batch_id:
                target_batch_id = sandbox.source_batch_id

            if target_batch_id is None:
                raise SandboxPromotionError('必须指定目标批次ID')

            if isinstance(target_batch_id, str) and not target_batch_id.isdigit():
                batch = db.query(Batch).filter(Batch.batch_no == target_batch_id).first()
                if not batch:
                    raise SandboxPromotionError(f'目标批次不存在: {target_batch_id}')
                target_batch_id = batch.id
            else:
                target_batch_id = int(target_batch_id)
                batch = db.query(Batch).filter(Batch.id == target_batch_id).first()
                if not batch:
                    raise SandboxPromotionError(f'目标批次不存在: {target_batch_id}')

            existing_promotions = db.query(SandboxPromotion).filter(
                SandboxPromotion.target_batch_id == target_batch_id,
                SandboxPromotion.is_rolled_back == False
            ).count()

            if existing_promotions > 0 and not force:
                raise SandboxConflictError(
                    f'目标批次 {target_batch_id} 已被应用过 {existing_promotions} 次修正，'
                    f'可能存在冲突。请使用 --force 强制应用，或先回滚之前的修正。'
                )

            conflicts = self._detect_conflicts(db, sandbox, trial, target_batch_id)

            if conflicts and not force:
                raise SandboxConflictError(
                    f'检测到 {len(conflicts)} 个冲突，请审查后使用 --force 强制应用，或调整规则后重试。'
                )

            promotion = SandboxPromotion(
                promotion_no=self._generate_no('PRM'),
                sandbox_id=sandbox.id,
                trial_id=trial.id,
                target_batch_id=target_batch_id,
                status='applying',
                conflict_count=len(conflicts),
                conflict_details=json.dumps(conflicts, ensure_ascii=False) if conflicts else None,
                applied_by=operator
            )
            db.add(promotion)
            db.flush()
            promotion_id = promotion.id

            applied_rows = 0
            try:
                results = db.query(SandboxTrialResult).filter(
                    SandboxTrialResult.trial_id == trial.id,
                    SandboxTrialResult.change_type == 'modified'
                ).all()

                table_model_map = {
                    'meter': MeterReading,
                    'plan': IrrigationPlan,
                    'weather': WeatherRecord,
                }

                for result in results:
                    if not result.row_data_after:
                        continue

                    try:
                        row_after = json.loads(result.row_data_after)
                    except Exception:
                        continue

                    sample = db.query(SandboxSample).filter(SandboxSample.id == result.sample_id).first()
                    if not sample:
                        continue

                    model = table_model_map.get(sample.source_type)
                    if not model:
                        continue

                    record = None
                    if hasattr(model, 'parcel_id') and 'parcel_id' in row_after:
                        parcel_id = row_after.get('parcel_id')
                        record = db.query(model).filter(
                            model.parcel_id == parcel_id,
                            model.batch_id == target_batch_id
                        ).first()

                    if record and hasattr(record, result.field_name):
                        setattr(record, result.field_name, result.new_value)
                        applied_rows += 1

                for conflict in conflicts:
                    db_conflict = SandboxConflict(
                        promotion_id=promotion_id,
                        conflict_type=conflict['conflict_type'],
                        target_record_id=conflict['target_record_id'],
                        target_table=conflict['target_table'],
                        field_name=conflict['field_name'],
                        existing_value=conflict['existing_value'],
                        proposed_value=conflict['proposed_value'],
                        resolution='overwritten' if force else 'pending'
                    )
                    if force:
                        db_conflict.resolved_at = datetime.now()
                        db_conflict.resolved_by = operator
                    db.add(db_conflict)

                promotion.status = 'applied'
                promotion.applied_rows = applied_rows
                promotion.applied_at = datetime.now()

                sandbox.status = 'applied'
                sandbox.updated_at = datetime.now()

            except Exception as e:
                promotion.status = 'failed'
                raise SandboxPromotionError(f'应用修正失败: {e}')

        self._log(sandbox_id, 'promote', operator, {
            'promotion_id': promotion_id,
            'trial_id': trial_id,
            'target_batch_id': target_batch_id,
            'conflict_count': len(conflicts),
            'applied_rows': applied_rows,
        })

        return self.get_promotion(promotion_id)

    def list_promotions(self, sandbox_id_or_no: Any = None, limit: int = 20) -> List[Dict]:
        """列出提升记录"""
        with get_db() as db:
            query = db.query(SandboxPromotion).order_by(SandboxPromotion.applied_at.desc())

            if sandbox_id_or_no is not None:
                sandbox = self._find_sandbox(db, sandbox_id_or_no)
                if sandbox:
                    query = query.filter(SandboxPromotion.sandbox_id == sandbox.id)

            promotions = query.limit(limit).all()
            return [self._promotion_to_dict(p, db) for p in promotions]

    def get_promotion(self, promotion_id: int) -> Optional[Dict]:
        """获取提升详情"""
        with get_db() as db:
            promotion = db.query(SandboxPromotion).filter(SandboxPromotion.id == promotion_id).first()
            if not promotion:
                return None
            return self._promotion_to_dict(promotion, db, include_conflicts=True)

    def _promotion_to_dict(self, promotion: SandboxPromotion, db, include_conflicts: bool = False) -> Dict:
        """转换提升记录为字典"""
        result = {
            'id': promotion.id,
            'promotion_no': promotion.promotion_no,
            'sandbox_id': promotion.sandbox_id,
            'trial_id': promotion.trial_id,
            'target_batch_id': promotion.target_batch_id,
            'status': promotion.status,
            'conflict_count': promotion.conflict_count,
            'applied_rows': promotion.applied_rows,
            'applied_by': promotion.applied_by,
            'applied_at': promotion.applied_at.isoformat() if promotion.applied_at else None,
            'is_rolled_back': promotion.is_rolled_back,
            'rolled_back_at': promotion.rolled_back_at.isoformat() if promotion.rolled_back_at else None,
            'rolled_back_by': promotion.rolled_back_by,
            'rollback_note': promotion.rollback_note,
        }

        if include_conflicts:
            conflicts = db.query(SandboxConflict).filter(
                SandboxConflict.promotion_id == promotion.id
            ).all()
            result['conflicts'] = [self._conflict_to_dict(c) for c in conflicts]

        return result

    def _conflict_to_dict(self, conflict: SandboxConflict) -> Dict:
        """转换冲突为字典"""
        return {
            'id': conflict.id,
            'promotion_id': conflict.promotion_id,
            'conflict_type': conflict.conflict_type,
            'target_record_id': conflict.target_record_id,
            'target_table': conflict.target_table,
            'field_name': conflict.field_name,
            'existing_value': conflict.existing_value,
            'proposed_value': conflict.proposed_value,
            'last_modified_at': conflict.last_modified_at.isoformat() if conflict.last_modified_at else None,
            'last_modified_by': conflict.last_modified_by,
            'resolution': conflict.resolution,
            'resolved_at': conflict.resolved_at.isoformat() if conflict.resolved_at else None,
            'resolved_by': conflict.resolved_by,
        }

    def rollback_promotion(self, promotion_id: int, reason: str, operator: str = 'cli') -> Dict:
        """回滚提升记录"""
        with get_db() as db:
            promotion = db.query(SandboxPromotion).filter(SandboxPromotion.id == promotion_id).first()
            if not promotion:
                raise SandboxPromotionError(f'提升记录不存在: {promotion_id}')

            sandbox_id = promotion.sandbox_id

            if promotion.is_rolled_back:
                raise SandboxPromotionError('该提升记录已被回滚')

            trial = db.query(SandboxTrial).filter(SandboxTrial.id == promotion.trial_id).first()
            if not trial:
                raise SandboxTrialError(f'试跑记录不存在: {promotion.trial_id}')

            results = db.query(SandboxTrialResult).filter(
                SandboxTrialResult.trial_id == trial.id,
                SandboxTrialResult.change_type == 'modified'
            ).all()

            table_model_map = {
                'meter': MeterReading,
                'plan': IrrigationPlan,
                'weather': WeatherRecord,
            }

            rolled_back_count = 0
            for result in results:
                if not result.row_data_before:
                    continue

                try:
                    row_before = json.loads(result.row_data_before)
                except Exception:
                    continue

                sample = db.query(SandboxSample).filter(SandboxSample.id == result.sample_id).first()
                if not sample:
                    continue

                model = table_model_map.get(sample.source_type)
                if not model:
                    continue

                record = None
                if hasattr(model, 'parcel_id') and 'parcel_id' in row_before:
                    parcel_id = row_before.get('parcel_id')
                    record = db.query(model).filter(
                        model.parcel_id == parcel_id,
                        model.batch_id == promotion.target_batch_id
                    ).first()

                if record and hasattr(record, result.field_name):
                    setattr(record, result.field_name, result.old_value)
                    rolled_back_count += 1

            promotion.is_rolled_back = True
            promotion.rolled_back_at = datetime.now()
            promotion.rolled_back_by = operator
            promotion.rollback_note = reason

            sandbox = db.query(Sandbox).filter(Sandbox.id == promotion.sandbox_id).first()
            if sandbox:
                sandbox.status = 'rolled_back'
                sandbox.updated_at = datetime.now()

            db.query(SandboxConflict).filter(
                SandboxConflict.promotion_id == promotion_id
            ).update({
                'resolution': 'rolled_back',
                'resolved_at': datetime.now(),
                'resolved_by': operator
            })

        self._log(sandbox_id, 'rollback', operator, {
            'promotion_id': promotion_id,
            'reason': reason,
            'rolled_back_count': rolled_back_count,
        })

        return self.get_promotion(promotion_id)

    def list_logs(self, sandbox_id_or_no: Any = None, operation: str = None, limit: int = 100) -> List[Dict]:
        """列出操作日志"""
        with get_db() as db:
            query = db.query(SandboxLog).order_by(SandboxLog.created_at.desc())

            if sandbox_id_or_no is not None:
                sandbox = self._find_sandbox(db, sandbox_id_or_no)
                if sandbox:
                    query = query.filter(SandboxLog.sandbox_id == sandbox.id)

            if operation:
                query = query.filter(SandboxLog.operation == operation)

            logs = query.limit(limit).all()
            return [self._log_to_dict(l) for l in logs]

    def _log_to_dict(self, log: SandboxLog) -> Dict:
        """转换日志为字典"""
        return {
            'id': log.id,
            'sandbox_id': log.sandbox_id,
            'operation': log.operation,
            'operator': log.operator,
            'details': json.loads(log.details) if log.details else None,
            'created_at': log.created_at.isoformat() if log.created_at else None,
        }

    def export_sandbox_package(self, sandbox_id_or_no: Any, output_path: str = None) -> str:
        """导出沙盒包"""
        sandbox = self.get_sandbox(sandbox_id_or_no, include_details=True)
        if not sandbox:
            raise SandboxNotFoundError(f'沙盒不存在: {sandbox_id_or_no}')

        samples = self.list_samples(sandbox_id_or_no)
        rules = self.list_rules(sandbox_id_or_no)
        trials = self.list_trials(sandbox_id_or_no)
        promotions = self.list_promotions(sandbox_id_or_no)
        logs = self.list_logs(sandbox_id_or_no)

        package_data = {
            'version': '1.0.0',
            'exported_at': datetime.now().isoformat(),
            'sandbox': sandbox,
            'samples': samples,
            'rules': rules,
            'trials': trials,
            'promotions': promotions,
            'logs': logs,
        }

        if output_path is None:
            from .config import OUTPUT_DIR
            output_path = os.path.join(OUTPUT_DIR, f'sandbox_{sandbox["sandbox_no"]}.zip')

        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('metadata.json', json.dumps({
                'version': '1.0.0',
                'exported_at': datetime.now().isoformat(),
                'sandbox_no': sandbox['sandbox_no'],
                'sandbox_name': sandbox['name'],
                'created_by': sandbox['created_by'],
                'rule_count': len(rules),
                'sample_count': len(samples),
                'trial_count': len(trials),
            }, ensure_ascii=False, indent=2))

            zf.writestr('sandbox.json', json.dumps(sandbox, ensure_ascii=False, indent=2))
            zf.writestr('rules.json', json.dumps(rules, ensure_ascii=False, indent=2))
            zf.writestr('samples.json', json.dumps(samples, ensure_ascii=False, indent=2))
            zf.writestr('trials.json', json.dumps(trials, ensure_ascii=False, indent=2))
            zf.writestr('promotions.json', json.dumps(promotions, ensure_ascii=False, indent=2))
            zf.writestr('logs.json', json.dumps(logs, ensure_ascii=False, indent=2))

            summary = self._generate_report_summary(sandbox, rules, samples, trials, promotions, logs)
            zf.writestr('report.md', summary)

        return output_path

    def _generate_report_summary(self, sandbox: Dict, rules: List[Dict], samples: List[Dict],
                                 trials: List[Dict], promotions: List[Dict], logs: List[Dict]) -> str:
        """生成报告摘要"""
        lines = []
        lines.append(f'# 沙盒规则报告 - {sandbox["name"]}')
        lines.append('')
        lines.append(f'**沙盒编号**: {sandbox["sandbox_no"]}')
        lines.append(f'**创建人**: {sandbox["created_by"]}')
        lines.append(f'**创建时间**: {sandbox["created_at"]}')
        lines.append(f'**状态**: {sandbox["status"]}')
        lines.append(f'**描述**: {sandbox["description"] or "无"}')
        lines.append('')
        lines.append('## 规则摘要')
        lines.append('')
        lines.append(f'共 {len(rules)} 条规则:')
        lines.append('')
        lines.append('| 序号 | 规则名称 | 规则类型 | 目标字段 | 优先级 |')
        lines.append('|-----|---------|---------|---------|-------|')
        for i, rule in enumerate(rules, 1):
            type_name = {
                'field_mapping': '字段映射',
                'missing_fill': '缺失值填补',
                'outlier_replace': '异常值改写',
                'custom': '自定义'
            }.get(rule['rule_type'], rule['rule_type'])
            lines.append(f'| {i} | {rule["rule_name"]} | {type_name} | {rule["target_field"] or "-"} | {rule["priority"]} |')
        lines.append('')
        lines.append('## 差异统计')
        lines.append('')
        lines.append(f'共 {len(trials)} 次试跑:')
        lines.append('')
        lines.append('| 试跑编号 | 状态 | 总行数 | 影响行数 | 未变化 | 错误 | 执行人 | 执行时间 |')
        lines.append('|---------|------|-------|---------|--------|------|--------|---------|')
        for trial in trials:
            lines.append(f'| {trial["trial_no"]} | {trial["status"]} | {trial["total_rows"]} | {trial["affected_rows"]} | {trial["unchanged_rows"]} | {trial["error_count"]} | {trial["executed_by"]} | {trial["executed_at"]} |')
        lines.append('')
        lines.append('## 操作者记录')
        lines.append('')
        lines.append(f'共 {len(logs)} 条操作日志:')
        lines.append('')
        lines.append('| 序号 | 操作 | 操作人 | 时间 |')
        lines.append('|-----|------|--------|------|')
        for i, log in enumerate(logs[:20], 1):
            op_name = {
                'create': '创建沙盒',
                'update': '更新沙盒',
                'delete': '删除沙盒',
                'import_sample': '导入样例',
                'add_rule': '添加规则',
                'update_rule': '更新规则',
                'delete_rule': '删除规则',
                'run_trial': '执行试跑',
                'promote': '提升为正式',
                'rollback': '回滚',
            }.get(log['operation'], log['operation'])
            lines.append(f'| {i} | {op_name} | {log["operator"]} | {log["created_at"]} |')
        if len(logs) > 20:
            lines.append('')
            lines.append(f'* 仅显示最近 20 条操作，共 {len(logs)} 条 *')

        return '\n'.join(lines)

    def import_sandbox_package(self, file_path: str, rename: str = None, operator: str = 'cli') -> Dict:
        """导入沙盒包"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f'文件不存在: {file_path}')

        if not zipfile.is_zipfile(file_path):
            raise ValueError('不是有效的ZIP文件')

        with zipfile.ZipFile(file_path, 'r') as zf:
            required_files = ['sandbox.json', 'rules.json', 'samples.json']
            for f in required_files:
                if f not in zf.namelist():
                    raise ValueError(f'沙盒包缺少必要文件: {f}')

            sandbox_data = json.loads(zf.read('sandbox.json').decode('utf-8'))
            rules_data = json.loads(zf.read('rules.json').decode('utf-8'))
            samples_data = json.loads(zf.read('samples.json').decode('utf-8'))

        name = rename if rename else sandbox_data['name']
        description = sandbox_data.get('description', '')
        source_dataset = sandbox_data.get('source_dataset')

        sandbox = self.create_sandbox(
            name=name,
            description=description,
            source_dataset=source_dataset,
            created_by=operator
        )

        sandbox_id = sandbox['id']

        for sample in samples_data:
            with get_db() as db:
                db_sample = SandboxSample(
                    sandbox_id=sandbox_id,
                    sample_name=sample['sample_name'],
                    source_type=sample['source_type'],
                    source_file=sample.get('source_file', 'imported'),
                    row_count=sample['row_count'],
                    sample_data=json.dumps(sample.get('data', []), ensure_ascii=False),
                    created_by=operator
                )
                db.add(db_sample)

        for rule in rules_data:
            self.add_rule(
                sandbox_id_or_no=sandbox_id,
                rule_type=rule['rule_type'],
                rule_name=rule['rule_name'],
                source_field=rule.get('source_field'),
                target_field=rule.get('target_field'),
                condition=rule.get('condition'),
                replacement=rule.get('replacement'),
                fill_value=rule.get('fill_value'),
                mapping_data=rule.get('mapping_data'),
                priority=rule.get('priority', 0),
                operator=operator
            )

        self._log(sandbox_id, 'import_package', operator, {
            'source_file': file_path,
            'rule_count': len(rules_data),
            'sample_count': len(samples_data),
        })

        return self.get_sandbox(sandbox_id, include_details=True)


sandbox_manager = SandboxManager()
