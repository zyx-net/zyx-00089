# -*- coding: utf-8 -*-
"""
批次管理、复核标记和回滚功能
"""
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from sqlalchemy import and_

from .database import get_db
from .models import (
    Batch, Anomaly, Rollback, MeterReading, IrrigationPlan,
    WeatherRecord, RawRow, BatchParcel, AnomalyReviewHistory
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
    """复核管理器 - 支持复核历史记录、追加备注、修改状态、撤销复核"""

    REVIEW_RESULTS = ['valid', 'false_positive', 'needs_investigation']
    ACTION_TYPES = ['review', 'update_status', 'append_comment', 'undo']

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
            return [self._anomaly_to_dict(a, db) for a in anomalies]

    def get_anomaly(self, anomaly_id: int) -> Optional[Dict]:
        """获取异常详情（含复核摘要）"""
        with get_db() as db:
            anomaly = db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
            if not anomaly:
                return None
            return self._anomaly_to_dict(anomaly, db, include_details=True)

    def get_review_history(self, anomaly_id: int) -> List[Dict]:
        """获取某条异常的复核时间线（包含撤销记录）"""
        with get_db() as db:
            anomaly = db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
            if not anomaly:
                raise ValueError(f"异常不存在: {anomaly_id}")

            history = db.query(AnomalyReviewHistory).filter(
                AnomalyReviewHistory.anomaly_id == anomaly_id
            ).order_by(AnomalyReviewHistory.sequence.asc()).all()

            return [self._history_to_dict(h) for h in history]

    def get_review_summary(self, anomaly_id: int) -> Dict:
        """获取复核摘要（用于报告导出和列表展示）"""
        with get_db() as db:
            anomaly = db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
            if not anomaly:
                raise ValueError(f"异常不存在: {anomaly_id}")

            history = db.query(AnomalyReviewHistory).filter(
                AnomalyReviewHistory.anomaly_id == anomaly_id,
                AnomalyReviewHistory.is_undone == False
            ).order_by(AnomalyReviewHistory.sequence.desc()).all()

            review_count = len(history)
            last_review = history[0] if history else None
            all_comments = [h.review_comment for h in history if h.review_comment]

            return {
                'anomaly_id': anomaly_id,
                'review_count': review_count,
                'undo_count': db.query(AnomalyReviewHistory).filter(
                    AnomalyReviewHistory.anomaly_id == anomaly_id,
                    AnomalyReviewHistory.is_undone == True
                ).count(),
                'last_review_at': last_review.reviewed_at.isoformat() if last_review else None,
                'last_review_by': last_review.reviewed_by if last_review else None,
                'last_review_result': last_review.review_result if last_review else None,
                'all_comments': all_comments,
            }

    def review_anomaly(self, anomaly_id: int, review_result: str,
                       review_comment: str = None, reviewed_by: str = 'manual') -> Dict:
        """
        复核异常（写入历史记录）
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

            next_seq = self._get_next_sequence(db, anomaly_id)

            history = AnomalyReviewHistory(
                anomaly_id=anomaly_id,
                sequence=next_seq,
                action_type='review',
                review_result=review_result,
                review_comment=review_comment,
                is_false_positive=(review_result == 'false_positive'),
                reviewed_by=reviewed_by,
                reviewed_at=datetime.now(),
                is_undone=False
            )
            db.add(history)

            anomaly.is_reviewed = True
            anomaly.reviewed_at = history.reviewed_at
            anomaly.reviewed_by = reviewed_by
            anomaly.review_result = review_result
            anomaly.review_comment = review_comment
            anomaly.is_false_positive = (review_result == 'false_positive')

            db.flush()
            return self._anomaly_to_dict(anomaly, db)

    def append_comment(self, anomaly_id: int, comment: str,
                       reviewed_by: str = 'manual') -> Dict:
        """追加备注（不改变状态，仅添加备注）"""
        if not comment or not comment.strip():
            raise ValueError("备注不能为空")

        with get_db() as db:
            anomaly = db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
            if not anomaly:
                raise ValueError(f"异常不存在: {anomaly_id}")

            if anomaly.is_rolled_back:
                raise ValueError(f"异常已被回滚，无法追加备注: {anomaly_id}")

            next_seq = self._get_next_sequence(db, anomaly_id)

            history = AnomalyReviewHistory(
                anomaly_id=anomaly_id,
                sequence=next_seq,
                action_type='append_comment',
                review_result=anomaly.review_result,
                review_comment=comment.strip(),
                is_false_positive=anomaly.is_false_positive,
                reviewed_by=reviewed_by,
                reviewed_at=datetime.now(),
                is_undone=False
            )
            db.add(history)

            existing_comment = anomaly.review_comment or ''
            if existing_comment:
                anomaly.review_comment = existing_comment + '\n' + comment.strip()
            else:
                anomaly.review_comment = comment.strip()
            anomaly.reviewed_at = history.reviewed_at
            anomaly.reviewed_by = reviewed_by

            db.flush()
            return self._anomaly_to_dict(anomaly, db)

    def update_review_status(self, anomaly_id: int, new_status: str,
                             comment: str = None, reviewed_by: str = 'manual') -> Dict:
        """修改处置状态（更新复核结果，可选添加备注）"""
        if new_status not in self.REVIEW_RESULTS:
            raise ValueError(f"无效的复核状态: {new_status}。有效值: {self.REVIEW_RESULTS}")

        with get_db() as db:
            anomaly = db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
            if not anomaly:
                raise ValueError(f"异常不存在: {anomaly_id}")

            if anomaly.is_rolled_back:
                raise ValueError(f"异常已被回滚，无法修改状态: {anomaly_id}")

            next_seq = self._get_next_sequence(db, anomaly_id)

            history = AnomalyReviewHistory(
                anomaly_id=anomaly_id,
                sequence=next_seq,
                action_type='update_status',
                review_result=new_status,
                review_comment=comment,
                is_false_positive=(new_status == 'false_positive'),
                reviewed_by=reviewed_by,
                reviewed_at=datetime.now(),
                is_undone=False
            )
            db.add(history)

            anomaly.is_reviewed = True
            anomaly.reviewed_at = history.reviewed_at
            anomaly.reviewed_by = reviewed_by
            anomaly.review_result = new_status
            anomaly.is_false_positive = (new_status == 'false_positive')
            if comment:
                existing_comment = anomaly.review_comment or ''
                if existing_comment:
                    anomaly.review_comment = existing_comment + '\n' + comment
                else:
                    anomaly.review_comment = comment

            db.flush()
            return self._anomaly_to_dict(anomaly, db)

    def undo_last_review(self, anomaly_id: int, undo_reason: str = None,
                         undone_by: str = 'manual') -> Dict:
        """
        撤销最近一次复核操作
        撤销后异常状态回滚到上一次操作前的状态
        """
        with get_db() as db:
            anomaly = db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
            if not anomaly:
                raise ValueError(f"异常不存在: {anomaly_id}")

            if anomaly.is_rolled_back:
                raise ValueError(f"异常已被回滚，无法撤销: {anomaly_id}")

            last_history = db.query(AnomalyReviewHistory).filter(
                AnomalyReviewHistory.anomaly_id == anomaly_id,
                AnomalyReviewHistory.is_undone == False
            ).order_by(AnomalyReviewHistory.sequence.desc()).first()

            if not last_history:
                raise ValueError(f"异常 {anomaly_id} 没有可撤销的复核操作")

            last_history.is_undone = True
            last_history.undone_at = datetime.now()
            last_history.undone_by = undone_by
            last_history.undo_reason = undo_reason

            next_seq = self._get_next_sequence(db, anomaly_id)
            undo_history = AnomalyReviewHistory(
                anomaly_id=anomaly_id,
                sequence=next_seq,
                action_type='undo',
                review_result=None,
                review_comment=undo_reason,
                is_false_positive=False,
                reviewed_by=undone_by,
                reviewed_at=last_history.undone_at,
                is_undone=False,
                extra_data=json.dumps({
                    'undone_sequence': last_history.sequence,
                    'undone_action_type': last_history.action_type,
                    'undone_result': last_history.review_result,
                }, ensure_ascii=False)
            )
            db.add(undo_history)

            current_valid = db.query(AnomalyReviewHistory).filter(
                AnomalyReviewHistory.anomaly_id == anomaly_id,
                AnomalyReviewHistory.is_undone == False,
                AnomalyReviewHistory.action_type != 'undo'
            ).order_by(AnomalyReviewHistory.sequence.desc()).first()

            if current_valid:
                anomaly.is_reviewed = True
                anomaly.reviewed_at = current_valid.reviewed_at
                anomaly.reviewed_by = current_valid.reviewed_by
                anomaly.review_result = current_valid.review_result
                anomaly.is_false_positive = current_valid.is_false_positive

                all_comments = db.query(AnomalyReviewHistory).filter(
                    AnomalyReviewHistory.anomaly_id == anomaly_id,
                    AnomalyReviewHistory.is_undone == False,
                    AnomalyReviewHistory.review_comment != None
                ).order_by(AnomalyReviewHistory.sequence.asc()).all()

                comments = [h.review_comment for h in all_comments if h.review_comment and h.sequence <= current_valid.sequence]
                anomaly.review_comment = '\n'.join(comments) if comments else None
            else:
                anomaly.is_reviewed = False
                anomaly.reviewed_at = None
                anomaly.reviewed_by = None
                anomaly.review_result = None
                anomaly.review_comment = None
                anomaly.is_false_positive = False

            db.flush()
            return self._anomaly_to_dict(anomaly, db)

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

    def _get_next_sequence(self, db, anomaly_id: int) -> int:
        """获取下一个序列号"""
        max_seq = db.query(AnomalyReviewHistory).filter(
            AnomalyReviewHistory.anomaly_id == anomaly_id
        ).count()
        return max_seq + 1

    def _history_to_dict(self, history: AnomalyReviewHistory) -> Dict:
        """转换复核历史记录为字典"""
        import json
        try:
            extra_data = json.loads(history.extra_data) if history.extra_data else None
        except (json.JSONDecodeError, TypeError):
            extra_data = {'raw': history.extra_data}

        return {
            'id': history.id,
            'anomaly_id': history.anomaly_id,
            'sequence': history.sequence,
            'action_type': history.action_type,
            'action_type_name': {
                'review': '首次复核',
                'update_status': '修改状态',
                'append_comment': '追加备注',
                'undo': '撤销操作'
            }.get(history.action_type, history.action_type),
            'review_result': history.review_result,
            'review_result_name': {
                'valid': '确认有效',
                'false_positive': '误报',
                'needs_investigation': '待调查'
            }.get(history.review_result, history.review_result) if history.review_result else None,
            'review_comment': history.review_comment,
            'is_false_positive': history.is_false_positive,
            'reviewed_by': history.reviewed_by,
            'reviewed_at': history.reviewed_at.isoformat() if history.reviewed_at else None,
            'is_undone': history.is_undone,
            'undone_at': history.undone_at.isoformat() if history.undone_at else None,
            'undone_by': history.undone_by,
            'undo_reason': history.undo_reason,
            'extra_data': extra_data,
        }

    def _anomaly_to_dict(self, anomaly: Anomaly, db, include_details: bool = False) -> Dict:
        """转换异常为字典（含复核摘要）"""
        import json
        try:
            extra_data = json.loads(anomaly.extra_data) if anomaly.extra_data else {}
        except (json.JSONDecodeError, TypeError):
            extra_data = {'raw': anomaly.extra_data}

        review_summary = self._get_summary_sync(db, anomaly.id)

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

            'review_summary': review_summary,
        }

        if include_details:
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

            review_history = db.query(AnomalyReviewHistory).filter(
                AnomalyReviewHistory.anomaly_id == anomaly.id
            ).order_by(AnomalyReviewHistory.sequence.asc()).all()
            result['review_history'] = [self._history_to_dict(h) for h in review_history]

        return result

    def _get_summary_sync(self, db, anomaly_id: int) -> Dict:
        """同步获取复核摘要（内部使用）"""
        history = db.query(AnomalyReviewHistory).filter(
            AnomalyReviewHistory.anomaly_id == anomaly_id,
            AnomalyReviewHistory.is_undone == False,
            AnomalyReviewHistory.action_type != 'undo'
        ).order_by(AnomalyReviewHistory.sequence.desc()).all()

        review_count = len(history)
        last_review = history[0] if history else None
        all_comments = [h.review_comment for h in history if h.review_comment]

        return {
            'review_count': review_count,
            'undo_count': db.query(AnomalyReviewHistory).filter(
                AnomalyReviewHistory.anomaly_id == anomaly_id,
                AnomalyReviewHistory.is_undone == True
            ).count(),
            'last_review_at': last_review.reviewed_at.isoformat() if last_review else None,
            'last_review_by': last_review.reviewed_by if last_review else None,
            'last_review_result': last_review.review_result if last_review else None,
            'all_comments': all_comments,
        }


class RollbackManager:
    """回滚管理器
    注意：回滚操作仅标记异常为已回滚状态，不删除任何原始异常记录或复核历史记录。
    审计数据（anomaly_review_history表）永久保留，用于追溯和合规审计。
    """

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
