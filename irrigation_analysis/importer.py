# -*- coding: utf-8 -*-
"""
数据导入模块
"""
import json
import uuid
from datetime import datetime, date
from typing import Dict, List, Tuple, Optional, Any
import pandas as pd
from dateutil import parser as date_parser

from .config import FIELD_MAPPINGS, DATE_FORMATS, DATETIME_FORMATS, RULE_VERSION
from .database import get_db
from .models import (
    Batch, RawRow, Parcel, MeterReading, IrrigationPlan, WeatherRecord,
    BatchParcel, Anomaly
)


class ImportError(Exception):
    """导入错误基类"""
    def __init__(self, message: str, row_number: int = None, field: str = None):
        self.row_number = row_number
        self.field = field
        super().__init__(message)

    def __str__(self):
        parts = []
        if self.row_number is not None:
            parts.append(f"第{self.row_number}行")
        if self.field:
            parts.append(f"[{self.field}]")
        parts.append(super().__str__())
        return ' '.join(parts)


class DataImporter:
    """数据导入器"""

    def __init__(self, custom_field_mappings: Dict = None):
        self.field_mappings = custom_field_mappings or FIELD_MAPPINGS
        self.errors: List[ImportError] = []

    def _parse_date(self, value: str, field_name: str, row_num: int) -> Optional[date]:
        """解析日期，支持多种格式"""
        if not value or pd.isna(value):
            return None

        value_str = str(value).strip()
        if not value_str:
            return None

        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(value_str, fmt).date()
            except ValueError:
                continue

        try:
            return date_parser.parse(value_str, fuzzy=True).date()
        except Exception:
            raise ImportError(
                f"日期格式错误: '{value_str}'，支持的格式: YYYY-MM-DD, YYYY/MM/DD",
                row_num, field_name
            )

    def _parse_datetime(self, date_val: str, time_val: str, row_num: int) -> Optional[datetime]:
        """解析日期时间"""
        d = self._parse_date(date_val, '读数日期', row_num)
        if d is None:
            return None

        if not time_val or pd.isna(time_val):
            return datetime(d.year, d.month, d.day)

        time_str = str(time_val).strip()
        if not time_str:
            return datetime(d.year, d.month, d.day)

        try:
            if ':' in time_str:
                parts = time_str.split(':')
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
                second = int(parts[2]) if len(parts) > 2 else 0
                return datetime(d.year, d.month, d.day, hour, minute, second)
            else:
                hour = int(time_str)
                return datetime(d.year, d.month, d.day, hour)
        except (ValueError, IndexError):
            raise ImportError(
                f"时间格式错误: '{time_str}'，正确格式: HH:MM 或 HH",
                row_num, '读数时间'
            )

    def _parse_float(self, value: Any, field_name: str, row_num: int) -> Optional[float]:
        """解析浮点数"""
        if value is None or pd.isna(value):
            return None

        value_str = str(value).strip()
        if not value_str:
            return None

        try:
            return float(value_str)
        except ValueError:
            raise ImportError(
                f"数值格式错误: '{value_str}'",
                row_num, field_name
            )

    def _map_columns(self, df_columns: List[str], source_type: str) -> Dict[str, str]:
        """根据配置的字段映射，将CSV列名映射到标准字段名"""
        mapping = self.field_mappings.get(source_type, {})
        reverse_map = {v: k for k, v in mapping.items()}

        result = {}
        for col in df_columns:
            col_clean = str(col).strip()
            if col_clean in reverse_map:
                result[col] = reverse_map[col_clean]
            elif col_clean in mapping:
                result[col] = col_clean

        return result

    def _save_raw_row(self, db, batch_id: int, source_type: str,
                      row_num: int, row_data: Dict,
                      is_error: bool = False, error_msg: str = None) -> int:
        """保存原始行数据"""
        raw_row = RawRow(
            batch_id=batch_id,
            source_type=source_type,
            row_number=row_num,
            row_data=json.dumps(row_data, ensure_ascii=False),
            is_error=is_error,
            error_message=error_msg
        )
        db.add(raw_row)
        db.flush()
        return raw_row.id

    def _create_batch(self, db, batch_type: str, description: str = '') -> Batch:
        """创建批次"""
        batch = Batch(
            batch_no=f'BATCH{datetime.now().strftime("%Y%m%d%H%M%S")}{uuid.uuid4().hex[:4].upper()}',
            batch_type=batch_type,
            description=description,
            rule_version=RULE_VERSION
        )
        db.add(batch)
        db.flush()
        return batch

    def import_parcels(self, file_path: str, description: str = '') -> Dict:
        """导入地块台账"""
        return self._import_data(file_path, 'parcel', description)

    def import_meters(self, file_path: str, description: str = '') -> Dict:
        """导入水表读数"""
        return self._import_data(file_path, 'meter', description)

    def import_plans(self, file_path: str, description: str = '') -> Dict:
        """导入灌溉计划"""
        return self._import_data(file_path, 'plan', description)

    def import_weather(self, file_path: str, description: str = '') -> Dict:
        """导入天气补录"""
        return self._import_data(file_path, 'weather', description)

    def _import_data(self, file_path: str, source_type: str, description: str) -> Dict:
        """通用数据导入方法"""
        self.errors = []

        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig')
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding='gbk')
        except Exception as e:
            raise ImportError(f"读取文件失败: {str(e)}")

        if df.empty:
            raise ImportError("文件为空，没有可导入的数据")

        col_map = self._map_columns(df.columns.tolist(), source_type)
        if not col_map:
            available_fields = list(self.field_mappings.get(source_type, {}).values())
            raise ImportError(
                f"未识别到有效的字段列。CSV列: {list(df.columns)}。"
                f"支持的字段: {available_fields}"
            )

        with get_db() as db:
            batch = self._create_batch(db, source_type, description)
            success_count = 0
            error_count = 0

            for idx, row in df.iterrows():
                row_num = idx + 2
                row_data = row.to_dict()

                try:
                    mapped_row = {}
                    for csv_col, std_field in col_map.items():
                        mapped_row[std_field] = row.get(csv_col)

                    if source_type == 'parcel':
                        self._process_parcel(db, batch, mapped_row, row_data, row_num)
                    elif source_type == 'meter':
                        self._process_meter(db, batch, mapped_row, row_data, row_num)
                    elif source_type == 'plan':
                        self._process_plan(db, batch, mapped_row, row_data, row_num)
                    elif source_type == 'weather':
                        self._process_weather(db, batch, mapped_row, row_data, row_num)

                    self._save_raw_row(db, batch.id, source_type, row_num, row_data)
                    success_count += 1

                except ImportError as e:
                    error_count += 1
                    self.errors.append(e)
                    self._save_raw_row(
                        db, batch.id, source_type, row_num, row_data,
                        is_error=True, error_msg=str(e)
                    )
                except Exception as e:
                    error_count += 1
                    err = ImportError(f"未知错误: {str(e)}", row_num)
                    self.errors.append(err)
                    self._save_raw_row(
                        db, batch.id, source_type, row_num, row_data,
                        is_error=True, error_msg=str(err)
                    )

            return {
                'batch_no': batch.batch_no,
                'batch_id': batch.id,
                'success_count': success_count,
                'error_count': error_count,
                'total_count': len(df),
                'errors': [str(e) for e in self.errors]
            }

    def _process_parcel(self, db, batch: Batch, mapped_row: Dict,
                        row_data: Dict, row_num: int) -> None:
        """处理地块数据"""
        parcel_id = mapped_row.get('parcel_id')
        if not parcel_id or pd.isna(parcel_id) or str(parcel_id).strip() == '':
            raise ImportError("缺少地块编号", row_num, '地块编号')

        parcel_id = str(parcel_id).strip()

        existing = db.query(Parcel).filter(Parcel.parcel_id == parcel_id).first()
        if existing:
            existing.parcel_name = mapped_row.get('parcel_name', existing.parcel_name)
            existing.area = self._parse_float(mapped_row.get('area'), '面积', row_num)
            existing.crop_type = mapped_row.get('crop_type')
            existing.location = mapped_row.get('location')
            existing.updated_at = datetime.now()
        else:
            parcel = Parcel(
                parcel_id=parcel_id,
                parcel_name=mapped_row.get('parcel_name'),
                area=self._parse_float(mapped_row.get('area'), '面积', row_num),
                crop_type=mapped_row.get('crop_type'),
                location=mapped_row.get('location')
            )
            db.add(parcel)
            db.flush()

        batch_parcel = BatchParcel(batch_id=batch.id, parcel_id=parcel_id)
        db.merge(batch_parcel)

    def _process_meter(self, db, batch: Batch, mapped_row: Dict,
                       row_data: Dict, row_num: int) -> None:
        """处理水表读数数据"""
        parcel_id = mapped_row.get('parcel_id')
        if not parcel_id or pd.isna(parcel_id) or str(parcel_id).strip() == '':
            raise ImportError("缺少地块编号", row_num, '地块编号')

        parcel_id = str(parcel_id).strip()

        parcel = db.query(Parcel).filter(Parcel.parcel_id == parcel_id).first()
        if not parcel:
            raise ImportError(
                f"引用不存在的地块: '{parcel_id}'",
                row_num, '地块编号'
            )

        read_date = self._parse_date(mapped_row.get('read_date'), '读数日期', row_num)
        if read_date is None:
            raise ImportError("缺少读数日期", row_num, '读数日期')

        read_time = mapped_row.get('read_time', '')
        read_datetime = self._parse_datetime(
            mapped_row.get('read_date'), read_time, row_num
        )

        reading = self._parse_float(mapped_row.get('reading'), '水表读数', row_num)
        if reading is None:
            raise ImportError("缺少水表读数", row_num, '水表读数')

        existing = db.query(MeterReading).filter(
            MeterReading.parcel_id == parcel_id,
            MeterReading.read_datetime == read_datetime
        ).first()

        if existing:
            if abs(existing.reading - reading) > 0.001:
                raise ImportError(
                    f"同一地块同一时刻读数冲突: 已有读数={existing.reading}, "
                    f"当前读数={reading}",
                    row_num, '水表读数'
                )
            else:
                raise ImportError(
                    f"重复上报: 地块 {parcel_id} 在 {read_datetime} 的读数已存在",
                    row_num
                )

        raw_row_id = self._save_raw_row(db, batch.id, 'meter', row_num, row_data)

        meter = MeterReading(
            parcel_id=parcel_id,
            read_date=read_date,
            read_time=str(read_time) if read_time and not pd.isna(read_time) else '',
            read_datetime=read_datetime,
            reading=reading,
            operator=mapped_row.get('operator'),
            batch_id=batch.id,
            raw_row_id=raw_row_id
        )
        db.add(meter)

    def _process_plan(self, db, batch: Batch, mapped_row: Dict,
                      row_data: Dict, row_num: int) -> None:
        """处理灌溉计划数据"""
        parcel_id = mapped_row.get('parcel_id')
        if not parcel_id or pd.isna(parcel_id) or str(parcel_id).strip() == '':
            raise ImportError("缺少地块编号", row_num, '地块编号')

        parcel_id = str(parcel_id).strip()

        parcel = db.query(Parcel).filter(Parcel.parcel_id == parcel_id).first()
        if not parcel:
            raise ImportError(
                f"引用不存在的地块: '{parcel_id}'",
                row_num, '地块编号'
            )

        plan_date = self._parse_date(mapped_row.get('plan_date'), '计划日期', row_num)
        if plan_date is None:
            raise ImportError("缺少计划日期", row_num, '计划日期')

        plan_water = self._parse_float(mapped_row.get('plan_water'), '计划用水量', row_num)
        if plan_water is None:
            raise ImportError("缺少计划用水量", row_num, '计划用水量')

        raw_row_id = self._save_raw_row(db, batch.id, 'plan', row_num, row_data)

        plan = IrrigationPlan(
            parcel_id=parcel_id,
            plan_date=plan_date,
            plan_water=plan_water,
            irrigation_type=mapped_row.get('irrigation_type'),
            batch_id=batch.id,
            raw_row_id=raw_row_id
        )
        db.add(plan)

    def _process_weather(self, db, batch: Batch, mapped_row: Dict,
                         row_data: Dict, row_num: int) -> None:
        """处理天气补录数据"""
        record_date = self._parse_date(mapped_row.get('record_date'), '记录日期', row_num)
        if record_date is None:
            raise ImportError("缺少记录日期", row_num, '记录日期')

        raw_row_id = self._save_raw_row(db, batch.id, 'weather', row_num, row_data)

        weather = WeatherRecord(
            record_date=record_date,
            rainfall=self._parse_float(mapped_row.get('rainfall'), '降雨量', row_num) or 0.0,
            temperature=self._parse_float(mapped_row.get('temperature'), '气温', row_num),
            humidity=self._parse_float(mapped_row.get('humidity'), '湿度', row_num),
            weather_type=mapped_row.get('weather_type'),
            batch_id=batch.id,
            raw_row_id=raw_row_id
        )
        db.add(weather)
