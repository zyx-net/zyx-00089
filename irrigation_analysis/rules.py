# -*- coding: utf-8 -*-
"""
异常检测规则引擎
"""
import json
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from sqlalchemy import and_, func

from .config import THRESHOLDS, RULE_VERSION, EXCEPTION_TYPES
from .database import get_db
from .models import (
    Batch, Anomaly, MeterReading, IrrigationPlan, Parcel,
    WeatherRecord, RawRow
)
from .threshold_manager import threshold_manager


class AnomalyResult:
    """异常结果封装"""
    def __init__(self, anomaly_code: str, description: str, **kwargs):
        self.anomaly_code = anomaly_code
        self.anomaly_type = EXCEPTION_TYPES.get(anomaly_code, anomaly_code)
        self.description = description
        self.extra = kwargs

    def to_dict(self) -> Dict:
        return {
            'anomaly_code': self.anomaly_code,
            'anomaly_type': self.anomaly_type,
            'description': self.description,
            **self.extra
        }


class RuleEngine:
    """规则引擎"""

    def __init__(self):
        self.rule_version = RULE_VERSION
        active_thresholds = threshold_manager.get_active_thresholds()
        self.thresholds = active_thresholds
        self.threshold_scheme_id = active_thresholds['scheme_id']
        self.threshold_scheme_name = active_thresholds['scheme_name']

    def detect_all(self, batch_id: int = None, parcel_id: str = None,
                   start_date: date = None, end_date: date = None) -> List[Dict]:
        """
        执行所有异常检测规则
        返回检测到的异常列表
        """
        all_anomalies = []

        with get_db() as db:
            active_readings = self._get_active_readings(db, batch_id, parcel_id, start_date, end_date)
            active_plans = self._get_active_plans(db, batch_id, parcel_id, start_date, end_date)
            active_parcels = self._get_active_parcels(db, parcel_id)
            parcel_ids = {p.parcel_id for p in active_parcels}

            all_anomalies.extend(self._detect_unknown_parcel(db, batch_id))
            all_anomalies.extend(self._detect_invalid_reference(db, batch_id))
            all_anomalies.extend(self._detect_missing_parcel_id(db, batch_id))
            all_anomalies.extend(self._detect_invalid_date(db, batch_id))
            all_anomalies.extend(self._detect_reading_conflict(db, batch_id))
            all_anomalies.extend(self._detect_duplicate_report(db, batch_id))
            all_anomalies.extend(self._detect_meter_backward(db, active_readings))
            all_anomalies.extend(self._detect_missing_reading(db, active_readings))
            all_anomalies.extend(self._detect_over_plan(db, active_readings, active_plans))

            existing_anomalies = self._get_existing_anomalies(db, batch_id)

            new_anomalies = []
            for anomaly in all_anomalies:
                key = self._get_anomaly_key(anomaly)
                if key not in existing_anomalies:
                    new_anomalies.append(self._save_anomaly(db, anomaly, batch_id))

            return new_anomalies

    def _get_anomaly_key(self, anomaly: Dict) -> str:
        """生成异常的唯一标识键"""
        parts = [
            anomaly.get('anomaly_code', ''),
            anomaly.get('parcel_id', ''),
            anomaly.get('reading_id', '') or '',
            anomaly.get('plan_id', '') or '',
        ]
        extra = anomaly.get('extra_data', {})
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except (json.JSONDecodeError, TypeError):
                extra = {}
        if 'read_datetime' in extra:
            parts.append(str(extra['read_datetime']))
        if 'conflict_datetime' in extra:
            parts.append(str(extra['conflict_datetime']))
        return '|'.join(str(p) for p in parts)

    def _get_existing_anomalies(self, db, batch_id: int = None) -> set:
        """获取已存在的异常，用于去重"""
        query = db.query(Anomaly).filter(Anomaly.is_rolled_back == False)
        if batch_id:
            query = query.filter(Anomaly.batch_id == batch_id)
        existing = query.all()

        keys = set()
        for a in existing:
            extra = {}
            if a.extra_data:
                try:
                    extra = json.loads(a.extra_data)
                except (json.JSONDecodeError, TypeError):
                    pass
            parts = [
                a.anomaly_code,
                a.parcel_id or '',
                str(a.reading_id) if a.reading_id else '',
                str(a.plan_id) if a.plan_id else '',
            ]
            if 'read_datetime' in extra:
                parts.append(str(extra['read_datetime']))
            if 'conflict_datetime' in extra:
                parts.append(str(extra['conflict_datetime']))
            keys.add('|'.join(str(p) for p in parts))
        return keys

    def _get_active_readings(self, db, batch_id: int = None, parcel_id: str = None,
                             start_date: date = None, end_date: date = None):
        """获取有效的水表读数"""
        query = db.query(MeterReading).filter(MeterReading.parcel_id.isnot(None))
        if batch_id:
            query = query.filter(MeterReading.batch_id == batch_id)
        if parcel_id:
            query = query.filter(MeterReading.parcel_id == parcel_id)
        if start_date:
            query = query.filter(MeterReading.read_date >= start_date)
        if end_date:
            query = query.filter(MeterReading.read_date <= end_date)
        return query.order_by(MeterReading.parcel_id, MeterReading.read_datetime).all()

    def _get_active_plans(self, db, batch_id: int = None, parcel_id: str = None,
                          start_date: date = None, end_date: date = None):
        """获取有效的灌溉计划"""
        query = db.query(IrrigationPlan).filter(IrrigationPlan.parcel_id.isnot(None))
        if batch_id:
            query = query.filter(IrrigationPlan.batch_id == batch_id)
        if parcel_id:
            query = query.filter(IrrigationPlan.parcel_id == parcel_id)
        if start_date:
            query = query.filter(IrrigationPlan.plan_date >= start_date)
        if end_date:
            query = query.filter(IrrigationPlan.plan_date <= end_date)
        return query.all()

    def _get_active_parcels(self, db, parcel_id: str = None):
        """获取有效的地块"""
        query = db.query(Parcel).filter(Parcel.is_active == True)
        if parcel_id:
            query = query.filter(Parcel.parcel_id == parcel_id)
        return query.all()

    def _save_anomaly(self, db, anomaly: Dict, batch_id: int = None) -> Dict:
        """保存异常到数据库"""
        extra_data = anomaly.get('extra_data', {})
        if isinstance(extra_data, dict):
            extra_data = json.dumps(extra_data, ensure_ascii=False)

        anomaly_obj = Anomaly(
            anomaly_type=anomaly['anomaly_type'],
            anomaly_code=anomaly['anomaly_code'],
            description=anomaly['description'],
            parcel_id=anomaly.get('parcel_id'),
            reading_id=anomaly.get('reading_id'),
            plan_id=anomaly.get('plan_id'),
            raw_row_id=anomaly.get('raw_row_id'),
            batch_id=batch_id or anomaly.get('batch_id'),
            rule_version=self.rule_version,
            threshold_scheme_id=self.threshold_scheme_id,
            threshold_scheme_name=self.threshold_scheme_name,
            severity=anomaly.get('severity', 'warning'),
            extra_data=extra_data
        )
        db.add(anomaly_obj)
        db.flush()

        result = anomaly.copy()
        result['id'] = anomaly_obj.id
        result['threshold_scheme_id'] = self.threshold_scheme_id
        result['threshold_scheme_name'] = self.threshold_scheme_name
        return result

    def _detect_unknown_parcel(self, db, batch_id: int = None) -> List[Dict]:
        """检测未知地块 - 原始行中有地块编号但在parcels表中不存在"""
        anomalies = []

        query = db.query(RawRow).filter(
            RawRow.is_error == True,
            RawRow.error_message.like('%引用不存在的地块%')
        )
        if batch_id:
            query = query.filter(RawRow.batch_id == batch_id)

        raw_rows = query.all()
        known_parcels = {p.parcel_id for p in db.query(Parcel.parcel_id).all()}

        for row in raw_rows:
            try:
                row_data = json.loads(row.row_data)
                parcel_id = None
                for key, value in row_data.items():
                    if '地块' in key and '编号' in key:
                        parcel_id = str(value).strip() if value else None
                        break

                if parcel_id and parcel_id not in known_parcels:
                    anomalies.append(AnomalyResult(
                        'UNKNOWN_PARCEL',
                        f"未知地块 '{parcel_id}'，该地块编号未在地块台账中登记",
                        parcel_id=parcel_id,
                        raw_row_id=row.id,
                        batch_id=row.batch_id,
                        severity='high',
                        extra_data={'source_row': row.row_number, 'parcel_id': parcel_id}
                    ).to_dict())
            except (json.JSONDecodeError, KeyError):
                continue

        return anomalies

    def _detect_invalid_reference(self, db, batch_id: int = None) -> List[Dict]:
        """检测引用不存在的地块（导入时已标记错误的）"""
        anomalies = []

        query = db.query(RawRow).filter(
            RawRow.is_error == True,
            RawRow.error_message.like('%引用不存在的地块%')
        )
        if batch_id:
            query = query.filter(RawRow.batch_id == batch_id)

        raw_rows = query.all()
        for row in raw_rows:
            try:
                row_data = json.loads(row.row_data)
                parcel_id = None
                for key, value in row_data.items():
                    if '地块' in key and '编号' in key:
                        parcel_id = str(value).strip() if value else None
                        break

                if parcel_id:
                    anomalies.append(AnomalyResult(
                        'INVALID_REFERENCE',
                        f"引用不存在的地块 '{parcel_id}'",
                        parcel_id=parcel_id,
                        raw_row_id=row.id,
                        batch_id=row.batch_id,
                        severity='high',
                        extra_data={'source_row': row.row_number, 'parcel_id': parcel_id}
                    ).to_dict())
            except (json.JSONDecodeError, KeyError):
                continue

        return anomalies

    def _detect_missing_parcel_id(self, db, batch_id: int = None) -> List[Dict]:
        """检测缺少地块编号"""
        anomalies = []

        query = db.query(RawRow).filter(
            RawRow.is_error == True,
            RawRow.error_message.like('%缺少地块编号%')
        )
        if batch_id:
            query = query.filter(RawRow.batch_id == batch_id)

        raw_rows = query.all()
        for row in raw_rows:
            anomalies.append(AnomalyResult(
                'MISSING_PARCEL_ID',
                f"缺少地块编号，第{row.row_number}行数据未提供有效地块编号",
                raw_row_id=row.id,
                batch_id=row.batch_id,
                severity='high',
                extra_data={'source_row': row.row_number}
            ).to_dict())

        return anomalies

    def _detect_invalid_date(self, db, batch_id: int = None) -> List[Dict]:
        """检测日期格式错误"""
        anomalies = []

        query = db.query(RawRow).filter(
            RawRow.is_error == True,
            RawRow.error_message.like('%日期格式错误%')
        )
        if batch_id:
            query = query.filter(RawRow.batch_id == batch_id)

        raw_rows = query.all()
        for row in raw_rows:
            anomalies.append(AnomalyResult(
                'INVALID_DATE',
                f"日期格式错误: {row.error_message}",
                raw_row_id=row.id,
                batch_id=row.batch_id,
                severity='medium',
                extra_data={'source_row': row.row_number, 'error': row.error_message}
            ).to_dict())

        return anomalies

    def _detect_reading_conflict(self, db, batch_id: int = None) -> List[Dict]:
        """检测同一地块同一时刻读数冲突"""
        anomalies = []

        query = db.query(RawRow).filter(
            RawRow.is_error == True,
            RawRow.error_message.like('%读数冲突%')
        )
        if batch_id:
            query = query.filter(RawRow.batch_id == batch_id)

        raw_rows = query.all()
        for row in raw_rows:
            try:
                row_data = json.loads(row.row_data)
                parcel_id = None
                for key, value in row_data.items():
                    if '地块' in key and '编号' in key:
                        parcel_id = str(value).strip() if value else None
                        break

                anomalies.append(AnomalyResult(
                    'READING_CONFLICT',
                    f"读数冲突: {row.error_message}",
                    parcel_id=parcel_id,
                    raw_row_id=row.id,
                    batch_id=row.batch_id,
                    severity='high',
                    extra_data={'source_row': row.row_number, 'error': row.error_message}
                ).to_dict())
            except (json.JSONDecodeError, KeyError):
                anomalies.append(AnomalyResult(
                    'READING_CONFLICT',
                    f"读数冲突: {row.error_message}",
                    raw_row_id=row.id,
                    batch_id=row.batch_id,
                    severity='high',
                    extra_data={'source_row': row.row_number, 'error': row.error_message}
                ).to_dict())

        return anomalies

    def _detect_duplicate_report(self, db, batch_id: int = None) -> List[Dict]:
        """检测重复上报"""
        anomalies = []

        query = db.query(RawRow).filter(
            RawRow.is_error == True,
            RawRow.error_message.like('%重复上报%')
        )
        if batch_id:
            query = query.filter(RawRow.batch_id == batch_id)

        raw_rows = query.all()
        for row in raw_rows:
            try:
                row_data = json.loads(row.row_data)
                parcel_id = None
                for key, value in row_data.items():
                    if '地块' in key and '编号' in key:
                        parcel_id = str(value).strip() if value else None
                        break

                anomalies.append(AnomalyResult(
                    'DUPLICATE_REPORT',
                    f"重复上报: {row.error_message}",
                    parcel_id=parcel_id,
                    raw_row_id=row.id,
                    batch_id=row.batch_id,
                    severity='medium',
                    extra_data={'source_row': row.row_number, 'error': row.error_message}
                ).to_dict())
            except (json.JSONDecodeError, KeyError):
                anomalies.append(AnomalyResult(
                    'DUPLICATE_REPORT',
                    f"重复上报: {row.error_message}",
                    raw_row_id=row.id,
                    batch_id=row.batch_id,
                    severity='medium',
                    extra_data={'source_row': row.row_number, 'error': row.error_message}
                ).to_dict())

        return anomalies

    def _detect_meter_backward(self, db, readings) -> List[Dict]:
        """检测倒表 - 读数小于上一次读数"""
        anomalies = []
        threshold = self.thresholds.get('meter_backward_tolerance', 0.01)

        readings_by_parcel = defaultdict(list)
        for r in readings:
            if r.parcel_id:
                readings_by_parcel[r.parcel_id].append(r)

        for parcel_id, parcel_readings in readings_by_parcel.items():
            parcel_readings.sort(key=lambda x: x.read_datetime or datetime.min)
            for i in range(1, len(parcel_readings)):
                prev = parcel_readings[i - 1]
                curr = parcel_readings[i]
                diff = curr.reading - prev.reading
                if diff < -threshold:
                    anomalies.append(AnomalyResult(
                        'METER_BACKWARD',
                        f"地块 {parcel_id} 发现倒表现象: {curr.read_datetime} 读数 {curr.reading} "
                        f"小于 {prev.read_datetime} 读数 {prev.reading}，差值 {diff:.2f}",
                        parcel_id=parcel_id,
                        reading_id=curr.id,
                        raw_row_id=curr.raw_row_id,
                        batch_id=curr.batch_id,
                        severity='high',
                        extra_data={
                            'prev_reading': prev.reading,
                            'curr_reading': curr.reading,
                            'prev_datetime': prev.read_datetime.isoformat() if prev.read_datetime else None,
                            'curr_datetime': curr.read_datetime.isoformat() if curr.read_datetime else None,
                            'difference': diff
                        }
                    ).to_dict())

        return anomalies

    def _detect_missing_reading(self, db, readings) -> List[Dict]:
        """检测漏采 - 超过阈值时间没有读数"""
        anomalies = []
        max_hours = self.thresholds.get('missing_reading_hours', 25)

        readings_by_parcel = defaultdict(list)
        for r in readings:
            if r.parcel_id and r.read_datetime:
                readings_by_parcel[r.parcel_id].append(r)

        for parcel_id, parcel_readings in readings_by_parcel.items():
            parcel_readings.sort(key=lambda x: x.read_datetime)
            for i in range(1, len(parcel_readings)):
                prev = parcel_readings[i - 1]
                curr = parcel_readings[i]
                gap = curr.read_datetime - prev.read_datetime
                gap_hours = gap.total_seconds() / 3600

                if gap_hours > max_hours:
                    missing_from = prev.read_datetime + timedelta(hours=max_hours)
                    missing_to = curr.read_datetime
                    anomalies.append(AnomalyResult(
                        'MISSING_READING',
                        f"地块 {parcel_id} 存在漏采: {prev.read_datetime} 至 "
                        f"{curr.read_datetime} 间隔 {gap_hours:.1f} 小时，"
                        f"超过阈值 {max_hours} 小时",
                        parcel_id=parcel_id,
                        reading_id=curr.id,
                        raw_row_id=curr.raw_row_id,
                        batch_id=curr.batch_id,
                        severity='medium',
                        extra_data={
                            'gap_hours': round(gap_hours, 2),
                            'max_allowed_hours': max_hours,
                            'prev_datetime': prev.read_datetime.isoformat(),
                            'curr_datetime': curr.read_datetime.isoformat(),
                            'missing_from': missing_from.isoformat(),
                            'missing_to': missing_to.isoformat()
                        }
                    ).to_dict())

        return anomalies

    def _detect_over_plan(self, db, readings, plans) -> List[Dict]:
        """检测超计划用水"""
        anomalies = []
        ratio_threshold = self.thresholds.get('over_plan_ratio', 1.2)

        plans_by_parcel_month = defaultdict(float)
        for p in plans:
            if p.parcel_id and p.plan_date:
                key = (p.parcel_id, p.plan_date.year, p.plan_date.month)
                plans_by_parcel_month[key] += p.plan_water

        usage_by_parcel_month = defaultdict(list)
        for r in readings:
            if r.parcel_id and r.read_datetime:
                key = (r.parcel_id, r.read_datetime.year, r.read_datetime.month)
                usage_by_parcel_month[key].append(r)

        for (parcel_id, year, month), plan_water in plans_by_parcel_month.items():
            key = (parcel_id, year, month)
            parcel_readings = usage_by_parcel_month.get(key, [])

            if len(parcel_readings) >= 2:
                parcel_readings.sort(key=lambda x: x.read_datetime)
                first = parcel_readings[0]
                last = parcel_readings[-1]
                actual_usage = last.reading - first.reading

                if actual_usage > 0 and plan_water > 0:
                    ratio = actual_usage / plan_water
                    if ratio > ratio_threshold:
                        anomalies.append(AnomalyResult(
                            'OVER_PLAN',
                            f"地块 {parcel_id} {year}年{month}月超计划用水: "
                            f"实际用水 {actual_usage:.2f}方，计划 {plan_water:.2f}方，"
                            f"超计划 {(ratio - 1) * 100:.1f}%",
                            parcel_id=parcel_id,
                            reading_id=last.id,
                            plan_id=None,
                            raw_row_id=last.raw_row_id,
                            batch_id=last.batch_id,
                            severity='high',
                            extra_data={
                                'year': year,
                                'month': month,
                                'plan_water': plan_water,
                                'actual_usage': round(actual_usage, 2),
                                'ratio': round(ratio, 4),
                                'over_ratio': round(ratio - 1, 4),
                                'first_reading': first.reading,
                                'last_reading': last.reading,
                                'first_datetime': first.read_datetime.isoformat(),
                                'last_datetime': last.read_datetime.isoformat(),
                                'ratio_threshold': ratio_threshold
                            }
                        ).to_dict())

        return anomalies
