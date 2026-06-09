# -*- coding: utf-8 -*-
"""
样例数据生成器
包含所有可复现的错误场景
"""
import csv
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict

from .config import DATA_DIR, FIELD_MAPPINGS


class SampleDataGenerator:
    """样例数据生成器"""

    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or DATA_DIR
        self.output_dir.mkdir(exist_ok=True)

        self.expected_anomalies = {
            'OVER_PLAN': 1,
            'METER_BACKWARD': 1,
            'MISSING_READING': 1,
            'DUPLICATE_REPORT': 1,
            'UNKNOWN_PARCEL': 1,
            'MISSING_PARCEL_ID': 1,
            'INVALID_DATE': 1,
            'READING_CONFLICT': 1,
            'INVALID_REFERENCE': 2,
        }

    def generate_all(self) -> Dict[str, str]:
        """生成所有样例数据文件"""
        files = {}
        files['parcels'] = self.generate_parcels()
        files['meters'] = self.generate_meters()
        files['plans'] = self.generate_plans()
        files['weather'] = self.generate_weather()
        return files

    def generate_parcels(self) -> str:
        """生成地块台账"""
        filepath = self.output_dir / 'sample_parcels.csv'
        mapping = FIELD_MAPPINGS['parcel']

        parcels = [
            {
                mapping['parcel_id']: 'P001',
                mapping['parcel_name']: '东一号地块',
                mapping['area']: '50.5',
                mapping['crop_type']: '小麦',
                mapping['location']: '村东头',
            },
            {
                mapping['parcel_id']: 'P002',
                mapping['parcel_name']: '西二号地块',
                mapping['area']: '35.2',
                mapping['crop_type']: '玉米',
                mapping['location']: '村西头',
            },
            {
                mapping['parcel_id']: 'P003',
                mapping['parcel_name']: '南三号地块',
                mapping['area']: '42.0',
                mapping['crop_type']: '水稻',
                mapping['location']: '村南边',
            },
            {
                mapping['parcel_id']: 'P004',
                mapping['parcel_name']: '北四号地块',
                mapping['area']: '28.8',
                mapping['crop_type']: '棉花',
                mapping['location']: '村北边',
            },
            {
                mapping['parcel_id']: 'P005',
                mapping['parcel_name']: '中五号地块',
                mapping['area']: '60.0',
                mapping['crop_type']: '大豆',
                mapping['location']: '村中央',
            },
        ]

        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=parcels[0].keys())
            writer.writeheader()
            writer.writerows(parcels)

        return str(filepath)

    def generate_meters(self) -> str:
        """
        生成水表读数数据，包含以下异常场景：
        1. 超计划用水 - P001 6月读数大幅增加
        2. 倒表 - P002 有一次读数小于上一次
        3. 漏采 - P003 两次读数间隔超过25小时
        4. 重复上报 - P004 同一时间重复上报
        5. 未知地块 - P999 不存在的地块
        6. 缺少地块编号 - 某行无地块编号
        7. 日期格式错误 - 日期格式不正确
        8. 读数冲突 - 同一时间读数不一致
        9. 引用不存在地块 - P888 不存在的地块
        """
        filepath = self.output_dir / 'sample_meters.csv'
        mapping = FIELD_MAPPINGS['meter']

        base_date = datetime(2025, 6, 1)

        meters = []

        # === P001: 正常读数 + 超计划用水 ===
        # 6月1日 - 6月5日 正常读数，每天8:00
        for i in range(5):
            dt = base_date + timedelta(days=i, hours=8)
            meters.append({
                mapping['parcel_id']: 'P001',
                mapping['read_date']: dt.strftime('%Y-%m-%d'),
                mapping['read_time']: dt.strftime('%H:%M'),
                mapping['reading']: f'{100.0 + i * 5.0:.2f}',
                mapping['operator']: '张三',
            })

        # P001 6月15日读数，体现超计划（6月计划用水50方，但6月1日到15日已用75方）
        for i in range(10, 15):
            dt = base_date + timedelta(days=i, hours=8)
            meters.append({
                mapping['parcel_id']: 'P001',
                mapping['read_date']: dt.strftime('%Y-%m-%d'),
                mapping['read_time']: dt.strftime('%H:%M'),
                mapping['reading']: f'{150.0 + (i - 10) * 15.0:.2f}',
                mapping['operator']: '张三',
            })

        # === P002: 正常 + 倒表 ===
        for i in range(3):
            dt = base_date + timedelta(days=i, hours=9)
            meters.append({
                mapping['parcel_id']: 'P002',
                mapping['read_date']: dt.strftime('%Y-%m-%d'),
                mapping['read_time']: dt.strftime('%H:%M'),
                mapping['reading']: f'{200.0 + i * 3.0:.2f}',
                mapping['operator']: '李四',
            })
        # 倒表异常：读数小于前一次（206.00 -> 180.00）
        dt = base_date + timedelta(days=3, hours=9)
        meters.append({
            mapping['parcel_id']: 'P002',
            mapping['read_date']: dt.strftime('%Y-%m-%d'),
            mapping['read_time']: dt.strftime('%H:%M'),
            mapping['reading']: '180.00',
            mapping['operator']: '李四',
        })
        # 恢复正常
        dt = base_date + timedelta(days=4, hours=9)
        meters.append({
            mapping['parcel_id']: 'P002',
            mapping['read_date']: dt.strftime('%Y-%m-%d'),
            mapping['read_time']: dt.strftime('%H:%M'),
            mapping['reading']: '212.00',
            mapping['operator']: '李四',
        })

        # === P003: 漏采（间隔超过25小时）===
        for i in range(2):
            dt = base_date + timedelta(days=i, hours=10)
            meters.append({
                mapping['parcel_id']: 'P003',
                mapping['read_date']: dt.strftime('%Y-%m-%d'),
                mapping['read_time']: dt.strftime('%H:%M'),
                mapping['reading']: f'{300.0 + i * 4.0:.2f}',
                mapping['operator']: '王五',
            })
        # 间隔30小时（正常24小时，漏采一次）
        dt = base_date + timedelta(days=3, hours=16)
        meters.append({
            mapping['parcel_id']: 'P003',
            mapping['read_date']: dt.strftime('%Y-%m-%d'),
            mapping['read_time']: dt.strftime('%H:%M'),
            mapping['reading']: '312.00',
            mapping['operator']: '王五',
        })

        # === P004: 重复上报 + 读数冲突 ===
        dt = base_date + timedelta(days=1, hours=11)
        meters.append({
            mapping['parcel_id']: 'P004',
            mapping['read_date']: dt.strftime('%Y-%m-%d'),
            mapping['read_time']: dt.strftime('%H:%M'),
            mapping['reading']: '400.00',
            mapping['operator']: '赵六',
        })
        # 重复上报（同样的数据）
        meters.append({
            mapping['parcel_id']: 'P004',
            mapping['read_date']: dt.strftime('%Y-%m-%d'),
            mapping['read_time']: dt.strftime('%H:%M'),
            mapping['reading']: '400.00',
            mapping['operator']: '赵六',
        })
        # 读数冲突（同一时间不同读数）
        meters.append({
            mapping['parcel_id']: 'P004',
            mapping['read_date']: dt.strftime('%Y-%m-%d'),
            mapping['read_time']: dt.strftime('%H:%M'),
            mapping['reading']: '410.00',
            mapping['operator']: '赵六',
        })

        # === P999: 未知地块（不存在于地块台账）===
        dt = base_date + timedelta(days=1, hours=12)
        meters.append({
            mapping['parcel_id']: 'P999',
            mapping['read_date']: dt.strftime('%Y-%m-%d'),
            mapping['read_time']: dt.strftime('%H:%M'),
            mapping['reading']: '500.00',
            mapping['operator']: '未知',
        })

        # === 缺少地块编号 ===
        dt = base_date + timedelta(days=1, hours=13)
        meters.append({
            mapping['parcel_id']: '',
            mapping['read_date']: dt.strftime('%Y-%m-%d'),
            mapping['read_time']: dt.strftime('%H:%M'),
            mapping['reading']: '600.00',
            mapping['operator']: '未知',
        })

        # === 日期格式错误 ===
        meters.append({
            mapping['parcel_id']: 'P005',
            mapping['read_date']: '2025-13-01',
            mapping['read_time']: '14:00',
            mapping['reading']: '700.00',
            mapping['operator']: '孙七',
        })

        # === P888: 引用不存在的地块（在计划和读数中都引用）===
        dt = base_date + timedelta(days=2, hours=8)
        meters.append({
            mapping['parcel_id']: 'P888',
            mapping['read_date']: dt.strftime('%Y-%m-%d'),
            mapping['read_time']: dt.strftime('%H:%M'),
            mapping['reading']: '800.00',
            mapping['operator']: '周八',
        })

        # === P005: 一些正常读数 ===
        for i in range(3):
            dt = base_date + timedelta(days=i, hours=15)
            meters.append({
                mapping['parcel_id']: 'P005',
                mapping['read_date']: dt.strftime('%Y-%m-%d'),
                mapping['read_time']: dt.strftime('%H:%M'),
                mapping['reading']: f'{900.0 + i * 2.0:.2f}',
                mapping['operator']: '孙七',
            })

        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=meters[0].keys())
            writer.writeheader()
            writer.writerows(meters)

        return str(filepath)

    def generate_plans(self) -> str:
        """
        生成灌溉计划数据
        P001 6月计划用水50方（实际会超）
        包含引用不存在地块的场景
        """
        filepath = self.output_dir / 'sample_plans.csv'
        mapping = FIELD_MAPPINGS['plan']

        plans = [
            {
                mapping['parcel_id']: 'P001',
                mapping['plan_date']: '2025-06-01',
                mapping['plan_water']: '20.0',
                mapping['irrigation_type']: '滴灌',
            },
            {
                mapping['parcel_id']: 'P001',
                mapping['plan_date']: '2025-06-10',
                mapping['plan_water']: '30.0',
                mapping['irrigation_type']: '漫灌',
            },
            {
                mapping['parcel_id']: 'P002',
                mapping['plan_date']: '2025-06-01',
                mapping['plan_water']: '15.0',
                mapping['irrigation_type']: '喷灌',
            },
            {
                mapping['parcel_id']: 'P003',
                mapping['plan_date']: '2025-06-01',
                mapping['plan_water']: '25.0',
                mapping['irrigation_type']: '漫灌',
            },
            {
                mapping['parcel_id']: 'P004',
                mapping['plan_date']: '2025-06-01',
                mapping['plan_water']: '18.0',
                mapping['irrigation_type']: '滴灌',
            },
            {
                mapping['parcel_id']: 'P005',
                mapping['plan_date']: '2025-06-01',
                mapping['plan_water']: '35.0',
                mapping['irrigation_type']: '喷灌',
            },
            {
                mapping['parcel_id']: 'P888',
                mapping['plan_date']: '2025-06-01',
                mapping['plan_water']: '40.0',
                mapping['irrigation_type']: '漫灌',
            },
        ]

        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=plans[0].keys())
            writer.writeheader()
            writer.writerows(plans)

        return str(filepath)

    def generate_weather(self) -> str:
        """生成天气补录数据"""
        filepath = self.output_dir / 'sample_weather.csv'
        mapping = FIELD_MAPPINGS['weather']

        weather = []
        base_date = datetime(2025, 6, 1)

        for i in range(15):
            dt = base_date + timedelta(days=i)
            weather.append({
                mapping['record_date']: dt.strftime('%Y-%m-%d'),
                mapping['rainfall']: f'{0.0 if i % 3 != 0 else 15.5:.1f}',
                mapping['temperature']: f'{25.0 + (i % 5) * 2:.1f}',
                mapping['humidity']: f'{60.0 + (i % 3) * 10:.1f}',
                mapping['weather_type']: '晴' if i % 3 != 0 else '小雨',
            })

        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=weather[0].keys())
            writer.writeheader()
            writer.writerows(weather)

        return str(filepath)

    def print_expected_anomalies(self) -> None:
        """打印预期的异常数量"""
        print("=" * 60)
        print("样例数据预期异常数量")
        print("=" * 60)
        total = 0
        for code, count in self.expected_anomalies.items():
            from .config import EXCEPTION_TYPES
            name = EXCEPTION_TYPES.get(code, code)
            print(f"  {code:20s} {name:15s} 预期: {count:2d} 条")
            total += count
        print("-" * 60)
        print(f"  {'总计':<35s} 预期: {total:2d} 条")
        print("=" * 60)


sample_data_generator = SampleDataGenerator()
