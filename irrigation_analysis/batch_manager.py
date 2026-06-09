# -*- coding: utf-8 -*-
"""
批次管理、复核标记和回滚功能
"""
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from sqlalchemy import and_

from .database import get_db
from .models import (
    Batch, Anomaly, Rollback, MeterReading, IrrigationPlan,
    WeatherRecord, RawRow, BatchParcel
)


class BatchManager:
    """批次管理器"""

    def list_batches(self, batch_type: str = None, limit: int = 100) -> List[Dict]:
        """列出所有批次"""
        with get_db() as db:
            query = db.query(Batch).order_by(Batch.created_at.desc())
            if batch_type:
                query = query.filter(Batch.batch_type == batch_type)
            batches = query.limit(limit).all()
            return [self._batch_to_dict(b, db) for b in batches]

    def get_batch(self, batch_id_or_no: Any) -> Optional[Dict]:
        """获取批次详情"""
        with get_db() as db:
            batch = self._find_batch(db, batch_id_or_no)
            if not batch:
                return None
            return self._batch_to_dict(batch, db, include_details=True)

    def _find_batch(self, db, batch_id_or_no: Any) -> Optional[Batch]:
        """根据ID或批次号查找批次"""
        if isinstance(batch_id_or_no, int):
            return db.query(Batch).filter(Batch.id == batch_id_or_no).first()
        batch_id_str = str(batch_id_or_no)
        if batch_id_str.isdigit():
            batch = db.query(Batch).filter(Batch.id == int(batch_id_str)).first()
            if batch:
                return batch
        return db.query(Batch).filter(Batch.batch_no == batch_id_str).first()

    def _batch_to_dict(self, batch: Batch, db, include_details: bool = False) -> Dict:
        """转换批次为字典"""
        result = {
            'id': batch.id,
            'batch_no': batch.batch_no,
            'batch_type': batch.batch_type,
            'description': batch.description,
            'rule_version': batch.rule_version,
            'created_by': batch.created_by,
            'created_at': batch.created_at.isoformat() if batch.created_at else None,
            'is_rolled_back': batch.is_rolled_back,
            'rolled_back_at': batch.rolled_back_at.isoformat() if batch.rolled_back_at else None,
            'rolled_back_by': batch.rolled_back_by,
            'rollback_reason': batch.rollback_reason,
        }

        if include_details:
            meter_count = db.query(MeterReading).filter(
                MeterReading.batch_id == batch.id
            ).count()
            plan_count = db.query(IrrigationPlan).filter(
                IrrigationPlan.batch_id == batch.id
            ).count()
            weather_count = db.query(WeatherRecord).filter(
                WeatherRecord.batch_id == batch.id
            ).count()
            anomaly_count = db.query(Anomaly).filter(
                Anomaly.batch_id == batch.id,
                Anomaly.is_rolled_back == False
            ).count()
            error_count = db.query(RawRow).filter(
                RawRow.batch_id == batch.id,
                RawRow.is_error == True
            ).count()
            raw_count = db.query(RawRow).filter(
                RawRow.batch_id == batch.id
            ).count()

            result.update({
                'meter_count': meter_count,
                'plan_count': plan_count,
                'weather_count': weather_count,
                'anomaly_count': anomaly_count,
                'error_count': error_count,
                'raw_count': raw_count,
            })

        return result


class ReviewManager:
    """复核管理器"""

    REVIEW_RESULTS = ['valid', 'false_positive', 'needs_investigation']

    def list_anomalies(self, batch_id: Any = None, anomaly_type: str = None,
                       is_reviewed: bool = None, is_false_positive: bool = None,
                       parcel_id: str = None, limit: int = 1000) -> List[Dict]:
        """列出异常"""
        with get_db() as db:
            query = db.query(Anomaly).filter(Anomaly.is_rolled_back == False)

            if batch_id is not None:
                if isinstance(batch_id, int) or str(batch_id).isdigit():
                    query = query.filter(Anomaly.batch_id == int(batch_id))
                else:
                    batch = db.query(Batch).filter(Batch.batch_no == str(batch_id)).first()
                    if batch:
                        query = query.filter(Anomaly.batch_id == batch.id)
                    else:
                        return []

            if anomaly_type:
                query = query.filter(Anomaly.anomaly_code == anomaly_type)
            if is_reviewed is not None:
                query = query.filter(Anomaly.is_reviewed == is_reviewed)
            if is_false_positive is not None:
                query = query.filter(Anomaly.is_false_positive == is_false_positive)
            if parcel_id:
                query = query.filter(Anomaly.parcel_id == parcel_id)

            anomalies = query.order_by(Anomaly.detected_at.desc()).limit(limit).all()
            return [self._anomaly_to_dict(a) for a in anomalies]

    def get_anomaly(self, anomaly_id: int) -> Optional[Dict]:
        """获取异常详情"""
        with get_db() as db:
            anomaly = db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
            if not anomaly:
                return None
            return self._anomaly_to_dict(anomaly, include_details=True)

    def review_anomaly(self, anomaly_id: int, review_result: str,
                       review_comment: str = None, reviewed_by: str = 'manual') -> Dict:
        """
        复核异常
        review_result: valid（确认有效）, false_positive（误报）, needs_investigation（待调查）
        """
        if review_result not in self.REVIEW_RESULTS:
            raise ValueError(f"无效的复核结果: {review_result}。有效值: {self.REVIEW_RESULTS}")

        with get_db() as db:
            anomaly = db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
            if not anomaly:
                raise ValueError(f"异常不存在: {anomaly_id}")

            if anomaly.is_rolled_back:
                raise ValueError(f"异常已被回滚，无法复核: {anomaly_id}")

            anomaly.is_reviewed = True
            anomaly.reviewed_at = datetime.now()
            anomaly.reviewed_by = reviewed_by
            anomaly.review_result = review_result
            anomaly.review_comment = review_comment
            anomaly.is_false_positive = (review_result == 'false_positive')

            db.flush()
            return self._anomaly_to_dict(anomaly)

    def batch_review(self, anomaly_ids: List[int], review_result: str,
                     review_comment: str = None, reviewed_by: str = 'manual') -> int:
        """批量复核"""
        count = 0
        for aid in anomaly_ids:
            try:
                self.review_anomaly(aid, review_result, review_comment, reviewed_by)
                count += 1
            except ValueError:
                continue
        return count

    def _anomaly_to_dict(self, anomaly: Anomaly, include_details: bool = False) -> Dict:
        """转换异常为字典"""
        import json
        try:
            extra_data = json.loads(anomaly.extra_data) if anomaly.extra_data else {}
        except (json.JSONDecodeError, TypeError):
            extra_data = {'raw': anomaly.extra_data}

        result = {
            'id': anomaly.id,
            'anomaly_code': anomaly.anomaly_code,
            'anomaly_type': anomaly.anomaly_type,
            'description': anomaly.description,
            'parcel_id': anomaly.parcel_id,
            'reading_id': anomaly.reading_id,
            'plan_id': anomaly.plan_id,
            'raw_row_id': anomaly.raw_row_id,
            'batch_id': anomaly.batch_id,
            'rule_version': anomaly.rule_version,
            'threshold_scheme_id': anomaly.threshold_scheme_id,
            'threshold_scheme_name': anomaly.threshold_scheme_name,
            'severity': anomaly.severity,
            'detected_at': anomaly.detected_at.isoformat() if anomaly.detected_at else None,
            'extra_data': extra_data,

            'is_reviewed': anomaly.is_reviewed,
            'reviewed_at': anomaly.reviewed_at.isoformat() if anomaly.reviewed_at else None,
            'reviewed_by': anomaly.reviewed_by,
            'review_result': anomaly.review_result,
            'review_comment': anomaly.review_comment,
            'is_false_positive': anomaly.is_false_positive,

            'is_rolled_back': anomaly.is_rolled_back,
            'rollback_id': anomaly.rollback_id,
        }

        if include_details:
            with get_db() as db:
                from .models import RawRow
                if anomaly.raw_row_id:
                    raw_row = db.query(RawRow).filter(RawRow.id == anomaly.raw_row_id).first()
                    if raw_row:
                        try:
                            result['raw_row_data'] = json.loads(raw_row.row_data)
                        except (json.JSONDecodeError, TypeError):
                            result['raw_row_data'] = raw_row.row_data
                        result['row_number'] = raw_row.row_number

                if anomaly.batch_id:
                    batch = db.query(Batch).filter(Batch.id == anomaly.batch_id).first()
                    if batch:
                        result['batch_no'] = batch.batch_no

        return result


class RollbackManager:
    """回滚管理器"""

    def rollback_batch(self, batch_id_or_no: Any, reason: str,
                       created_by: str = 'manual') -> Dict:
        """回滚整个批次"""
        with get_db() as db:
            batch = self._find_batch(db, batch_id_or_no)
            if not batch:
                raise ValueError(f"批次不存在: {batch_id_or_no}")

            if batch.is_rolled_back:
                raise ValueError(f"批次已被回滚: {batch.batch_no}")

            rollback_no = f'RB{datetime.now().strftime("%Y%m%d%H%M%S")}{uuid.uuid4().hex[:4].upper()}'
            rollback = Rollback(
                rollback_no=rollback_no,
                batch_id=batch.id,
                reason=reason,
                created_by=created_by
            )
            db.add(rollback)
            db.flush()

            anomaly_count = db.query(Anomaly).filter(
                Anomaly.batch_id == batch.id,
                Anomaly.is_rolled_back == False
            ).update({
                Anomaly.is_rolled_back: True,
                Anomaly.rollback_id: rollback.id
            })

            meter_count = db.query(MeterReading).filter(
                MeterReading.batch_id == batch.id
            ).delete()

            plan_count = db.query(IrrigationPlan).filter(
                IrrigationPlan.batch_id == batch.id
            ).delete()

            weather_count = db.query(WeatherRecord).filter(
                WeatherRecord.batch_id == batch.id
            ).delete()

            db.query(BatchParcel).filter(
                BatchParcel.batch_id == batch.id
            ).delete()

            batch.is_rolled_back = True
            batch.rolled_back_at = datetime.now()
            batch.rolled_back_by = created_by
            batch.rollback_reason = reason

            db.flush()

            return {
                'rollback_no': rollback_no,
                'rollback_id': rollback.id,
                'batch_id': batch.id,
                'batch_no': batch.batch_no,
                'reason': reason,
                'created_by': created_by,
                'created_at': rollback.created_at.isoformat(),
                'anomalies_rolled_back': anomaly_count,
                'meters_deleted': meter_count,
                'plans_deleted': plan_count,
                'weather_deleted': weather_count,
            }

    def rollback_anomaly(self, anomaly_id: int, reason: str,
                         created_by: str = 'manual') -> Dict:
        """回滚单个异常"""
        with get_db() as db:
            anomaly = db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
            if not anomaly:
                raise ValueError(f"异常不存在: {anomaly_id}")

            if anomaly.is_rolled_back:
                raise ValueError(f"异常已被回滚: {anomaly_id}")

            rollback_no = f'RB{datetime.now().strftime("%Y%m%d%H%M%S")}{uuid.uuid4().hex[:4].upper()}'
            rollback = Rollback(
                rollback_no=rollback_no,
                batch_id=anomaly.batch_id,
                reason=reason,
                created_by=created_by
            )
            db.add(rollback)
            db.flush()

            anomaly.is_rolled_back = True
            anomaly.rollback_id = rollback.id

            db.flush()

            return {
                'rollback_no': rollback_no,
                'rollback_id': rollback.id,
                'anomaly_id': anomaly_id,
                'reason': reason,
                'created_by': created_by,
                'created_at': rollback.created_at.isoformat(),
            }

    def list_rollbacks(self, limit: int = 100) -> List[Dict]:
        """列出回滚记录"""
        with get_db() as db:
            rollbacks = db.query(Rollback).order_by(Rollback.created_at.desc()).limit(limit).all()
            return [self._rollback_to_dict(r, db) for r in rollbacks]

    def get_rollback(self, rollback_id_or_no: Any) -> Optional[Dict]:
        """获取回滚详情"""
        with get_db() as db:
            rollback = self._find_rollback(db, rollback_id_or_no)
            if not rollback:
                return None
            return self._rollback_to_dict(rollback, db, include_details=True)

    def _find_batch(self, db, batch_id_or_no: Any) -> Optional[Batch]:
        """查找批次"""
        if isinstance(batch_id_or_no, int):
            return db.query(Batch).filter(Batch.id == batch_id_or_no).first()
        batch_id_str = str(batch_id_or_no)
        if batch_id_str.isdigit():
            batch = db.query(Batch).filter(Batch.id == int(batch_id_str)).first()
            if batch:
                return batch
        return db.query(Batch).filter(Batch.batch_no == batch_id_str).first()

    def _find_rollback(self, db, rollback_id_or_no: Any) -> Optional[Rollback]:
        """查找回滚记录"""
        if isinstance(rollback_id_or_no, int):
            return db.query(Rollback).filter(Rollback.id == rollback_id_or_no).first()
        rb_id_str = str(rollback_id_or_no)
        if rb_id_str.isdigit():
            rb = db.query(Rollback).filter(Rollback.id == int(rb_id_str)).first()
            if rb:
                return rb
        return db.query(Rollback).filter(Rollback.rollback_no == rb_id_str).first()

    def _rollback_to_dict(self, rollback: Rollback, db, include_details: bool = False) -> Dict:
        """转换回滚记录为字典"""
        result = {
            'id': rollback.id,
            'rollback_no': rollback.rollback_no,
            'batch_id': rollback.batch_id,
            'reason': rollback.reason,
            'created_by': rollback.created_by,
            'created_at': rollback.created_at.isoformat() if rollback.created_at else None,
        }

        if include_details:
            batch = db.query(Batch).filter(Batch.id == rollback.batch_id).first()
            if batch:
                result['batch_no'] = batch.batch_no

            anomaly_count = db.query(Anomaly).filter(
                Anomaly.rollback_id == rollback.id
            ).count()
            result['anomaly_count'] = anomaly_count

        return result


batch_manager = BatchManager()
review_manager = ReviewManager()
rollback_manager = RollbackManager()
