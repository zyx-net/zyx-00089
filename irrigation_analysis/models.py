# -*- coding: utf-8 -*-
"""
数据库模型定义
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, Text, Boolean,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Parcel(Base):
    """地块台账"""
    __tablename__ = 'parcels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    parcel_id = Column(String(50), unique=True, nullable=False, index=True)
    parcel_name = Column(String(100))
    area = Column(Float)
    crop_type = Column(String(50))
    location = Column(String(200))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_active = Column(Boolean, default=True)

    meter_readings = relationship('MeterReading', back_populates='parcel')
    irrigation_plans = relationship('IrrigationPlan', back_populates='parcel')


class MeterReading(Base):
    """水表读数"""
    __tablename__ = 'meter_readings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    parcel_id = Column(String(50), ForeignKey('parcels.parcel_id'), index=True)
    read_date = Column(Date, index=True)
    read_time = Column(String(20))
    read_datetime = Column(DateTime, index=True)
    reading = Column(Float, nullable=False)
    operator = Column(String(50))
    batch_id = Column(Integer, ForeignKey('batches.id'), index=True)
    raw_row_id = Column(Integer, ForeignKey('raw_rows.id'))
    created_at = Column(DateTime, default=datetime.now)

    parcel = relationship('Parcel', back_populates='meter_readings')
    batch = relationship('Batch', back_populates='meter_readings')
    raw_row = relationship('RawRow')


class IrrigationPlan(Base):
    """灌溉计划"""
    __tablename__ = 'irrigation_plans'

    id = Column(Integer, primary_key=True, autoincrement=True)
    parcel_id = Column(String(50), ForeignKey('parcels.parcel_id'), index=True)
    plan_date = Column(Date, index=True)
    plan_water = Column(Float, nullable=False)
    irrigation_type = Column(String(50))
    batch_id = Column(Integer, ForeignKey('batches.id'), index=True)
    raw_row_id = Column(Integer, ForeignKey('raw_rows.id'))
    created_at = Column(DateTime, default=datetime.now)

    parcel = relationship('Parcel', back_populates='irrigation_plans')
    batch = relationship('Batch', back_populates='irrigation_plans')
    raw_row = relationship('RawRow')


class WeatherRecord(Base):
    """天气补录"""
    __tablename__ = 'weather_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    record_date = Column(Date, index=True)
    rainfall = Column(Float, default=0.0)
    temperature = Column(Float)
    humidity = Column(Float)
    weather_type = Column(String(20))
    batch_id = Column(Integer, ForeignKey('batches.id'), index=True)
    raw_row_id = Column(Integer, ForeignKey('raw_rows.id'))
    created_at = Column(DateTime, default=datetime.now)

    batch = relationship('Batch', back_populates='weather_records')
    raw_row = relationship('RawRow')


class Batch(Base):
    """批次信息"""
    __tablename__ = 'batches'

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_no = Column(String(50), unique=True, nullable=False, index=True)
    batch_type = Column(String(20), nullable=False)
    description = Column(String(200))
    rule_version = Column(String(20), nullable=False)
    created_by = Column(String(50), default='system')
    created_at = Column(DateTime, default=datetime.now, index=True)
    is_rolled_back = Column(Boolean, default=False)
    rolled_back_at = Column(DateTime)
    rolled_back_by = Column(String(50))
    rollback_reason = Column(String(200))

    meter_readings = relationship('MeterReading', back_populates='batch')
    irrigation_plans = relationship('IrrigationPlan', back_populates='batch')
    weather_records = relationship('WeatherRecord', back_populates='batch')
    parcels = relationship('Parcel', secondary='batch_parcels', backref='batches')
    anomalies = relationship('Anomaly', back_populates='batch')
    raw_rows = relationship('RawRow', back_populates='batch')


class BatchParcel(Base):
    """批次-地块关联表"""
    __tablename__ = 'batch_parcels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey('batches.id'), index=True)
    parcel_id = Column(String(50), ForeignKey('parcels.parcel_id'), index=True)
    imported_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint('batch_id', 'parcel_id', name='_batch_parcel_uc'),
    )


class RawRow(Base):
    """原始数据行 - 保存导入的原始行数据"""
    __tablename__ = 'raw_rows'

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey('batches.id'), index=True)
    source_type = Column(String(20), nullable=False)
    row_number = Column(Integer)
    row_data = Column(Text, nullable=False)
    is_error = Column(Boolean, default=False)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

    batch = relationship('Batch', back_populates='raw_rows')


class Anomaly(Base):
    """异常结果"""
    __tablename__ = 'anomalies'

    id = Column(Integer, primary_key=True, autoincrement=True)
    anomaly_type = Column(String(50), nullable=False, index=True)
    anomaly_code = Column(String(20), nullable=False, index=True)
    description = Column(Text, nullable=False)
    parcel_id = Column(String(50), index=True)
    reading_id = Column(Integer, ForeignKey('meter_readings.id'))
    plan_id = Column(Integer, ForeignKey('irrigation_plans.id'))
    raw_row_id = Column(Integer, ForeignKey('raw_rows.id'))
    batch_id = Column(Integer, ForeignKey('batches.id'), index=True)
    rule_version = Column(String(20), nullable=False)
    threshold_scheme_id = Column(Integer, ForeignKey('threshold_schemes.id'))
    threshold_scheme_name = Column(String(100))
    severity = Column(String(20), default='warning')
    detected_at = Column(DateTime, default=datetime.now)
    extra_data = Column(Text)

    is_reviewed = Column(Boolean, default=False)
    reviewed_at = Column(DateTime)
    reviewed_by = Column(String(50))
    review_result = Column(String(20))
    review_comment = Column(Text)
    is_false_positive = Column(Boolean, default=False)

    is_rolled_back = Column(Boolean, default=False)
    rollback_id = Column(Integer, ForeignKey('rollbacks.id'))

    batch = relationship('Batch', back_populates='anomalies')
    reading = relationship('MeterReading')
    plan = relationship('IrrigationPlan')
    raw_row = relationship('RawRow')
    rollback = relationship('Rollback', back_populates='anomalies')

    __table_args__ = (
        Index('idx_anomaly_type_parcel', 'anomaly_type', 'parcel_id'),
        Index('idx_anomaly_batch_rule', 'batch_id', 'rule_version'),
    )


class Rollback(Base):
    """回滚记录"""
    __tablename__ = 'rollbacks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    rollback_no = Column(String(50), unique=True, nullable=False)
    batch_id = Column(Integer, ForeignKey('batches.id'), index=True)
    reason = Column(String(200), nullable=False)
    created_by = Column(String(50), default='system')
    created_at = Column(DateTime, default=datetime.now, index=True)

    anomalies = relationship('Anomaly', back_populates='rollback')


class ReportCache(Base):
    """报告缓存 - 确保重启后报告统计一致"""
    __tablename__ = 'report_caches'

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_type = Column(String(20), nullable=False)
    report_key = Column(String(100), nullable=False)
    report_data = Column(Text, nullable=False)
    generated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint('report_type', 'report_key', name='_report_type_key_uc'),
    )


class ThresholdScheme(Base):
    """阈值方案"""
    __tablename__ = 'threshold_schemes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(500))
    meter_backward_tolerance = Column(Float, nullable=False, default=0.01)
    over_plan_ratio = Column(Float, nullable=False, default=1.2)
    missing_reading_days = Column(Float, nullable=False, default=1.0)
    is_active = Column(Boolean, default=False, index=True)
    created_by = Column(String(50), default='system')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    anomalies = relationship('ThresholdSchemeLog', back_populates='scheme')


class ThresholdSchemeLog(Base):
    """阈值方案操作日志"""
    __tablename__ = 'threshold_scheme_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheme_id = Column(Integer, ForeignKey('threshold_schemes.id'), index=True)
    scheme_name = Column(String(100), nullable=False)
    operation = Column(String(20), nullable=False)
    operator = Column(String(50), default='system')
    details = Column(Text)
    created_at = Column(DateTime, default=datetime.now, index=True)

    scheme = relationship('ThresholdScheme', back_populates='anomalies')
