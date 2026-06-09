# -*- coding: utf-8 -*-
"""
配置管理和字段映射
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
OUTPUT_DIR = BASE_DIR / 'outputs'
DB_PATH = DATA_DIR / 'irrigation.db'

DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

DATABASE_URL = f'sqlite:///{DB_PATH}'

RULE_VERSION = '1.0.0'

FIELD_MAPPINGS = {
    'parcel': {
        'parcel_id': '地块编号',
        'parcel_name': '地块名称',
        'area': '面积(亩)',
        'crop_type': '作物类型',
        'location': '位置',
    },
    'meter': {
        'parcel_id': '地块编号',
        'read_date': '读数日期',
        'read_time': '读数时间',
        'reading': '水表读数',
        'operator': '操作员',
    },
    'plan': {
        'parcel_id': '地块编号',
        'plan_date': '计划日期',
        'plan_water': '计划用水量(方)',
        'irrigation_type': '灌溉类型',
    },
    'weather': {
        'record_date': '记录日期',
        'rainfall': '降雨量(mm)',
        'temperature': '气温(℃)',
        'humidity': '湿度(%)',
        'weather_type': '天气类型',
    }
}

DATE_FORMATS = [
    '%Y-%m-%d',
    '%Y/%m/%d',
    '%Y年%m月%d日',
    '%m/%d/%Y',
    '%d/%m/%Y',
]

DATETIME_FORMATS = [
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M',
    '%Y/%m/%d %H:%M:%S',
    '%Y/%m/%d %H:%M',
]

THRESHOLDS = {
    'over_plan_ratio': 1.2,
    'meter_backward_tolerance': 0.01,
    'missing_reading_hours': 25,
}

EXCEPTION_TYPES = {
    'OVER_PLAN': '超计划用水',
    'METER_BACKWARD': '倒表',
    'MISSING_READING': '漏采',
    'DUPLICATE_REPORT': '重复上报',
    'UNKNOWN_PARCEL': '未知地块',
    'MISSING_PARCEL_ID': '缺少地块编号',
    'INVALID_DATE': '日期格式错误',
    'READING_CONFLICT': '读数冲突',
    'INVALID_REFERENCE': '引用不存在地块',
}
