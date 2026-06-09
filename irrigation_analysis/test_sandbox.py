# -*- coding: utf-8 -*-
"""
数据修正规则沙盒模块 - 单元测试和集成测试
覆盖: 跨重启持久化、导入导出、冲突处理、权限/日志、回滚链路
"""
import os
import sys
import json
import tempfile
import shutil
from datetime import datetime, date
from pathlib import Path
from typing import Any, List

from .config import DATA_DIR, OUTPUT_DIR
from .database import init_db, get_db, engine as default_engine
from .models import Base, Batch, MeterReading, Parcel
from .sandbox_manager import (
    sandbox_manager, SandboxNotFoundError, SandboxRuleError,
    SandboxTrialError, SandboxConflictError, SandboxPromotionError
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class TestResult:
    """测试结果"""
    def __init__(self, name: str, passed: bool, message: str = '', expected: Any = None, actual: Any = None):
        self.name = name
        self.passed = passed
        self.message = message
        self.expected = expected
        self.actual = actual
        self.timestamp = datetime.now()

    def __str__(self):
        status = '✅ PASS' if self.passed else '❌ FAIL'
        msg = f'{status} {self.name}'
        if self.message:
            msg += f' - {self.message}'
        if self.expected is not None or self.actual is not None:
            msg += f' (预期: {self.expected}, 实际: {self.actual})'
        return msg


class SandboxTestSuite:
    """沙盒模块测试套件"""

    def __init__(self):
        self.results: List[TestResult] = []
        self.test_data = {}
        self.temp_dir = tempfile.mkdtemp(prefix='sandbox_test_')
        self.test_db_path = Path(self.temp_dir) / 'test_sandbox.db'

    def run(self) -> bool:
        """运行所有测试"""
        print('=' * 80)
        print('🧪 数据修正规则沙盒 - 测试套件')
        print('=' * 80)
        print(f'测试时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        print(f'临时目录: {self.temp_dir}')
        print()

        try:
            self._setup_database()
            self._test_1_sandbox_crud()
            self._test_2_sample_import()
            self._test_3_rule_management()
            self._test_4_trial_execution()
            self._test_5_persistence_across_restart()
            self._test_6_conflict_detection()
            self._test_7_rollback_mechanism()
            self._test_8_import_export_package()
            self._test_9_operation_logs()
            self._test_10_promote_to_production()

        except Exception as e:
            self.results.append(TestResult('测试执行异常', False, str(e)))
            import traceback
            traceback.print_exc()
        finally:
            self._cleanup()
            self._print_summary()

        return all(r.passed for r in self.results)

    def _setup_database(self):
        """设置测试数据库"""
        if self.test_db_path.exists():
            self.test_db_path.unlink()

        import importlib
        from . import database
        database.DB_PATH = self.test_db_path
        
        test_db_url = f'sqlite:///{self.test_db_path}?check_same_thread=False'
        database.engine = create_engine(
            test_db_url,
            echo=False,
            future=True,
            connect_args={'check_same_thread': False},
            pool_pre_ping=True,
            pool_recycle=3600,
            isolation_level='SERIALIZABLE'
        )
        database.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=database.engine,
            future=True
        )

        init_db()
        print(f'🗄️  测试数据库已初始化: {self.test_db_path}')

        self._create_test_batch()
        print()

    def _create_test_batch(self):
        """创建测试批次数据"""
        with get_db() as db:
            batch = Batch(
                batch_no=f'TEST_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
                batch_type='meter',
                description='测试批次',
                rule_version='1.0',
                created_by='test_user'
            )
            db.add(batch)
            db.flush()
            batch_id = batch.id

            for i in range(1, 4):
                reading = MeterReading(
                    batch_id=batch_id,
                    parcel_id=f'P{i:03d}',
                    read_date=date(2026, 6, 1),
                    reading=100 * i,
                    operator=f'测试员{i}'
                )
                db.add(reading)

            parcel = Parcel(
                parcel_id='P001',
                parcel_name='测试地块1',
                area=5.5,
                crop_type='小麦',
                location='测试区'
            )
            db.add(parcel)

        self.test_data['batch_id'] = batch_id
        print(f'📦 已创建测试批次 #{batch_id}，含 3 条水表读数记录')

    def _test_1_sandbox_crud(self):
        """测试1: 沙盒创建/查询/更新/删除"""
        print('🧪 测试1: 沙盒CRUD操作')

        try:
            sandbox = sandbox_manager.create_sandbox(
                name='测试沙盒1',
                description='用于测试CRUD操作',
                source_dataset='test_dataset',
                source_batch_id=self.test_data['batch_id'],
                created_by='tester1'
            )
            self.test_data['sandbox_id'] = sandbox['id']
            self.results.append(TestResult('创建沙盒', True, f'沙盒ID: {sandbox["id"]}'))

            found = sandbox_manager.get_sandbox(sandbox['id'])
            assert found is not None, '沙盒应该存在'
            assert found['name'] == '测试沙盒1'
            assert found['status'] == 'draft'
            self.results.append(TestResult('查询沙盒', True, f'名称: {found["name"]}'))

            updated = sandbox_manager.update_sandbox(
                sandbox['id'],
                name='测试沙盒1-已更新',
                description='更新后的描述',
                status='testing',
                operator='tester2'
            )
            assert updated['name'] == '测试沙盒1-已更新'
            assert updated['status'] == 'testing'
            self.results.append(TestResult('更新沙盒', True, f'新名称: {updated["name"]}'))

            list_all = sandbox_manager.list_sandboxes()
            assert len(list_all) >= 1
            self.results.append(TestResult('列出沙盒', True, f'共 {len(list_all)} 个沙盒'))

        except Exception as e:
            self.results.append(TestResult('沙盒CRUD', False, str(e)))

        print()

    def _test_2_sample_import(self):
        """测试2: 样例数据导入（CSV和JSON）"""
        print('🧪 测试2: 样例数据导入')

        try:
            sandbox_id = self.test_data['sandbox_id']

            csv_data = """parcel_id,read_date,reading,operator
P001,2026-06-01,100,测试员1
P002,2026-06-01,200,
P003,2026-06-01,9999,测试员3"""

            csv_file = os.path.join(self.temp_dir, 'test_sample.csv')
            with open(csv_file, 'w', encoding='utf-8') as f:
                f.write(csv_data)

            sample = sandbox_manager.import_sample(
                sandbox_id_or_no=sandbox_id,
                file_path=csv_file,
                source_type='meter',
                sample_name='测试水表数据CSV',
                operator='tester1'
            )
            assert sample['row_count'] == 3
            self.test_data['sample_id'] = sample['id']
            self.results.append(TestResult('导入CSV样例', True, f'{sample["row_count"]} 行'))

            json_data = [
                {'parcel_id': 'P001', 'read_date': '2026-06-01', 'reading': 150, 'operator': '测试员A'},
                {'parcel_id': 'P002', 'read_date': '2026-06-01', 'reading': None, 'operator': ''},
            ]
            json_file = os.path.join(self.temp_dir, 'test_sample.json')
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False)

            sample2 = sandbox_manager.import_sample(
                sandbox_id_or_no=sandbox_id,
                file_path=json_file,
                source_type='meter',
                sample_name='测试水表数据JSON',
                operator='tester1'
            )
            assert sample2['row_count'] == 2
            self.results.append(TestResult('导入JSON样例', True, f'{sample2["row_count"]} 行'))

            samples = sandbox_manager.list_samples(sandbox_id)
            assert len(samples) == 2
            self.results.append(TestResult('列出样例', True, f'共 {len(samples)} 份'))

        except Exception as e:
            self.results.append(TestResult('样例导入', False, str(e)))

        print()

    def _test_3_rule_management(self):
        """测试3: 规则管理（添加/查询/更新/删除）"""
        print('🧪 测试3: 规则管理')

        try:
            sandbox_id = self.test_data['sandbox_id']

            rule1 = sandbox_manager.add_rule(
                sandbox_id_or_no=sandbox_id,
                rule_type='missing_fill',
                rule_name='填补缺失操作员',
                target_field='operator',
                fill_value='未知操作员',
                priority=1,
                operator='tester1'
            )
            self.test_data['rule1_id'] = rule1['id']
            self.results.append(TestResult('添加缺失值填补规则', True, f'规则ID: {rule1["id"]}'))

            rule2 = sandbox_manager.add_rule(
                sandbox_id_or_no=sandbox_id,
                rule_type='outlier_replace',
                rule_name='修正异常读数',
                target_field='reading',
                condition='value and float(value) > 9000',
                replacement='0',
                priority=2,
                operator='tester1'
            )
            self.test_data['rule2_id'] = rule2['id']
            self.results.append(TestResult('添加异常值改写规则', True, f'规则ID: {rule2["id"]}'))

            rule3 = sandbox_manager.add_rule(
                sandbox_id_or_no=sandbox_id,
                rule_type='field_mapping',
                rule_name='字段映射测试',
                source_field='parcel_id',
                target_field='meter_id',
                priority=0,
                operator='tester1'
            )
            self.test_data['rule3_id'] = rule3['id']
            self.results.append(TestResult('添加字段映射规则', True, f'规则ID: {rule3["id"]}'))

            rules = sandbox_manager.list_rules(sandbox_id)
            assert len(rules) == 3
            self.results.append(TestResult('列出规则', True, f'共 {len(rules)} 条'))

            updated_rule = sandbox_manager.update_rule(
                rule1['id'],
                rule_name='填补缺失操作员-已更新',
                fill_value='临时工',
                operator='tester2'
            )
            assert updated_rule['rule_name'] == '填补缺失操作员-已更新'
            assert updated_rule['fill_value'] == '临时工'
            self.results.append(TestResult('更新规则', True, f'新名称: {updated_rule["rule_name"]}'))

            fetched_rule = sandbox_manager.get_rule(rule1['id'])
            assert fetched_rule is not None
            self.results.append(TestResult('查询规则', True, f'名称: {fetched_rule["rule_name"]}'))

        except Exception as e:
            self.results.append(TestResult('规则管理', False, str(e)))

        print()

    def _test_4_trial_execution(self):
        """测试4: 试跑执行与差异计算"""
        print('🧪 测试4: 试跑执行与差异计算')

        try:
            sandbox_id = self.test_data['sandbox_id']

            trial = sandbox_manager.run_trial(sandbox_id, operator='tester1')
            self.test_data['trial_id'] = trial['id']

            assert trial['status'] == 'completed'
            assert trial['total_rows'] == 5
            self.results.append(TestResult('执行试跑', True,
                f'试跑ID: {trial["id"]}, 总行数: {trial["total_rows"]}'))
            self.results.append(TestResult('试跑-影响行数', trial['affected_rows'] >= 2,
                f'影响行数: {trial["affected_rows"]}'))
            self.results.append(TestResult('试跑-错误计数', trial['error_count'] == 0,
                f'错误数: {trial["error_count"]}'))

            trial_detail = sandbox_manager.get_trial(trial['id'], include_results=True)
            assert 'results' in trial_detail
            assert len(trial_detail['results']) > 0
            self.results.append(TestResult('查询试跑详情', True,
                f'共 {len(trial_detail["results"])} 条差异记录'))

            if trial_detail.get('by_change_type'):
                self.results.append(TestResult('按变更类型统计', True,
                    f'统计结果: {trial_detail["by_change_type"]}'))

            trials = sandbox_manager.list_trials(sandbox_id)
            assert len(trials) >= 1
            self.results.append(TestResult('列出试跑记录', True, f'共 {len(trials)} 次'))

        except Exception as e:
            self.results.append(TestResult('试跑执行', False, str(e)))

        print()

    def _test_5_persistence_across_restart(self):
        """测试5: 跨重启持久化（模拟重启后数据仍存在）"""
        print('🧪 测试5: 跨重启持久化')

        try:
            sandbox_id = self.test_data['sandbox_id']
            trial_id = self.test_data['trial_id']

            from . import database
            database.engine.dispose()
            print('  ↻ 模拟数据库连接重启...')

            sandbox_after = sandbox_manager.get_sandbox(sandbox_id, include_details=True)
            assert sandbox_after is not None
            assert sandbox_after['id'] == sandbox_id
            self.results.append(TestResult('沙盒持久化', True,
                f'重启后沙盒仍存在: {sandbox_after["name"]}'))

            rules_after = sandbox_manager.list_rules(sandbox_id)
            assert len(rules_after) >= 3
            self.results.append(TestResult('规则持久化', True,
                f'重启后规则仍存在: {len(rules_after)} 条'))

            samples_after = sandbox_manager.list_samples(sandbox_id)
            assert len(samples_after) >= 2
            self.results.append(TestResult('样例持久化', True,
                f'重启后样例仍存在: {len(samples_after)} 份'))

            trial_after = sandbox_manager.get_trial(trial_id, include_results=True)
            assert trial_after is not None
            assert trial_after['id'] == trial_id
            self.results.append(TestResult('试跑结果持久化', True,
                f'重启后试跑仍存在，{len(trial_after["results"])} 条差异'))

            logs_after = sandbox_manager.list_logs(sandbox_id)
            assert len(logs_after) > 0
            self.results.append(TestResult('操作日志持久化', True,
                f'重启后日志仍存在: {len(logs_after)} 条'))

            print(f'  ✓ 重启前沙盒ID: {sandbox_id}')
            print(f'  ✓ 重启后沙盒ID: {sandbox_after["id"]}')
            print(f'  ✓ 所有数据验证通过')

        except Exception as e:
            self.results.append(TestResult('跨重启持久化', False, str(e)))

        print()

    def _test_6_conflict_detection(self):
        """测试6: 冲突检测"""
        print('🧪 测试6: 冲突检测')

        try:
            sandbox_id = self.test_data['sandbox_id']
            trial_id = self.test_data['trial_id']
            batch_id = self.test_data['batch_id']

            with get_db() as db:
                reading = db.query(MeterReading).filter(
                    MeterReading.batch_id == batch_id,
                    MeterReading.parcel_id == 'P001'
                ).first()
                if reading:
                    reading.operator = '已被修改'
                    db.flush()

            try:
                sandbox_manager.promote_to_production(
                    sandbox_id_or_no=sandbox_id,
                    trial_id=trial_id,
                    target_batch_id=batch_id,
                    force=False,
                    operator='tester1'
                )
                self.results.append(TestResult('冲突检测-未触发', False,
                    '应该检测到冲突但未检测到'))
            except SandboxConflictError as e:
                self.results.append(TestResult('冲突检测-正常触发', True,
                    f'成功检测到冲突: {str(e)[:60]}...'))

            promotion = sandbox_manager.promote_to_production(
                sandbox_id_or_no=sandbox_id,
                trial_id=trial_id,
                target_batch_id=batch_id,
                force=True,
                operator='tester1'
            )
            self.test_data['promotion_id'] = promotion['id']

            assert promotion['conflict_count'] > 0
            self.results.append(TestResult('冲突检测-强制应用', True,
                f'检测到 {promotion["conflict_count"]} 个冲突，已强制覆盖'))

            if promotion.get('conflicts'):
                self.results.append(TestResult('冲突记录保存', True,
                    f'共保存 {len(promotion["conflicts"])} 条冲突记录'))

        except Exception as e:
            self.results.append(TestResult('冲突检测', False, str(e)))

        print()

    def _test_7_rollback_mechanism(self):
        """测试7: 回滚机制"""
        print('🧪 测试7: 回滚机制')

        try:
            promotion_id = self.test_data['promotion_id']
            batch_id = self.test_data['batch_id']

            with get_db() as db:
                reading_before = db.query(MeterReading).filter(
                    MeterReading.batch_id == batch_id,
                    MeterReading.parcel_id == 'P001'
                ).first()
                value_before = reading_before.operator if reading_before else None

            rollback = sandbox_manager.rollback_promotion(
                promotion_id=promotion_id,
                reason='测试回滚功能',
                operator='tester3'
            )

            assert rollback['is_rolled_back'] == True
            assert rollback['rolled_back_by'] == 'tester3'
            assert rollback['rollback_note'] == '测试回滚功能'
            self.results.append(TestResult('执行回滚', True,
                f'回滚人: {rollback["rolled_back_by"]}'))

            with get_db() as db:
                reading_after = db.query(MeterReading).filter(
                    MeterReading.batch_id == batch_id,
                    MeterReading.parcel_id == 'P001'
                ).first()
                value_after = reading_after.operator if reading_after else None

            self.results.append(TestResult('数据恢复验证', value_after == '已被修改',
                f'回滚前: {value_before}，回滚后: {value_after}'))

            promotion_after = sandbox_manager.get_promotion(promotion_id)
            assert promotion_after['is_rolled_back'] == True
            self.results.append(TestResult('回滚状态持久化', True,
                '回滚状态已保存到数据库'))

            sandbox = sandbox_manager.get_sandbox(self.test_data['sandbox_id'])
            assert sandbox['status'] == 'rolled_back'
            self.results.append(TestResult('沙盒状态更新', True,
                f'沙盒状态已更新为: {sandbox["status"]}'))

            logs = sandbox_manager.list_logs(self.test_data['sandbox_id'], operation='rollback')
            assert len(logs) >= 1
            self.results.append(TestResult('回滚日志记录', True,
                f'已记录 {len(logs)} 条回滚操作日志'))

        except Exception as e:
            self.results.append(TestResult('回滚机制', False, str(e)))

        print()

    def _test_8_import_export_package(self):
        """测试8: 沙盒包导入导出"""
        print('🧪 测试8: 沙盒包导入导出')

        try:
            sandbox_id = self.test_data['sandbox_id']

            export_path = sandbox_manager.export_sandbox_package(
                sandbox_id_or_no=sandbox_id,
                output_path=os.path.join(self.temp_dir, 'sandbox_export.zip')
            )

            assert os.path.exists(export_path)
            file_size = os.path.getsize(export_path)
            assert file_size > 0
            self.results.append(TestResult('导出沙盒包', True,
                f'文件: {export_path}, 大小: {file_size} bytes'))

            import zipfile
            with zipfile.ZipFile(export_path, 'r') as zf:
                files = zf.namelist()
                required = ['metadata.json', 'sandbox.json', 'rules.json', 'samples.json', 'report.md']
                for req in required:
                    assert req in files, f'缺少必要文件: {req}'
            self.results.append(TestResult('验证包内容', True,
                f'包含 {len(files)} 个文件: {", ".join(files[:5])}'))

            with zipfile.ZipFile(export_path, 'r') as zf:
                metadata = json.loads(zf.read('metadata.json').decode('utf-8'))
                assert 'sandbox_no' in metadata
                assert 'rule_count' in metadata
                self.results.append(TestResult('验证元数据', True,
                    f'沙盒编号: {metadata["sandbox_no"]}, 规则数: {metadata["rule_count"]}'))

            with zipfile.ZipFile(export_path, 'r') as zf:
                report = zf.read('report.md').decode('utf-8')
                assert '# 沙盒规则报告' in report
                assert '规则摘要' in report
                assert '差异统计' in report
                assert '操作者记录' in report
            self.results.append(TestResult('验证报告内容', True,
                '报告包含规则摘要、差异统计、操作者记录'))

            imported = sandbox_manager.import_sandbox_package(
                file_path=export_path,
                rename='导入的沙盒副本',
                operator='importer_user'
            )

            assert imported is not None
            assert imported['name'] == '导入的沙盒副本'
            assert imported['created_by'] == 'importer_user'
            self.test_data['imported_sandbox_id'] = imported['id']
            self.results.append(TestResult('导入沙盒包', True,
                f'新沙盒ID: {imported["id"]}, 名称: {imported["name"]}'))

            imported_rules = sandbox_manager.list_rules(imported['id'])
            assert len(imported_rules) >= 3
            self.results.append(TestResult('导入规则验证', True,
                f'成功导入 {len(imported_rules)} 条规则'))

            imported_samples = sandbox_manager.list_samples(imported['id'])
            assert len(imported_samples) >= 2
            self.results.append(TestResult('导入样例验证', True,
                f'成功导入 {len(imported_samples)} 份样例'))

        except Exception as e:
            self.results.append(TestResult('导入导出', False, str(e)))

        print()

    def _test_9_operation_logs(self):
        """测试9: 操作日志与权限追踪"""
        print('🧪 测试9: 操作日志与权限追踪')

        try:
            sandbox_id = self.test_data['sandbox_id']

            logs = sandbox_manager.list_logs(sandbox_id)
            assert len(logs) > 0
            self.results.append(TestResult('日志记录存在', True,
                f'共 {len(logs)} 条日志'))

            operations = set(log['operation'] for log in logs)
            expected_ops = {'create', 'update', 'import_sample', 'add_rule',
                           'update_rule', 'run_trial', 'promote', 'rollback'}
            found_ops = operations & expected_ops
            self.results.append(TestResult('日志操作类型', len(found_ops) >= 5,
                f'记录的操作类型: {", ".join(sorted(found_ops))}'))

            create_logs = [l for l in logs if l['operation'] == 'create']
            assert len(create_logs) == 1
            assert create_logs[0]['operator'] == 'tester1'
            self.results.append(TestResult('创建日志验证', True,
                f'创建人: {create_logs[0]["operator"]}'))

            operators = set(log['operator'] for log in logs)
            assert 'tester1' in operators
            assert 'tester2' in operators
            assert 'tester3' in operators
            self.results.append(TestResult('多用户操作追踪', True,
                f'追踪到 {len(operators)} 个操作员: {", ".join(sorted(operators))}'))

            all_logs = sandbox_manager.list_logs()
            assert len(all_logs) >= len(logs)
            self.results.append(TestResult('全局日志查询', True,
                f'系统全局共 {len(all_logs)} 条操作日志'))

            by_op = sandbox_manager.list_logs(sandbox_id, operation='rollback')
            assert len(by_op) >= 1
            self.results.append(TestResult('按操作过滤', True,
                f'回滚操作日志: {len(by_op)} 条'))

        except Exception as e:
            self.results.append(TestResult('操作日志', False, str(e)))

        print()

    def _test_10_promote_to_production(self):
        """测试10: 提升为正式修正（完整流程）"""
        print('🧪 测试10: 提升为正式修正完整流程')

        try:
            sandbox2 = sandbox_manager.create_sandbox(
                name='提升测试沙盒',
                description='用于测试提升流程',
                source_batch_id=self.test_data['batch_id'],
                created_by='promotion_tester'
            )
            sandbox2_id = sandbox2['id']

            csv_data = """parcel_id,read_date,reading,operator
P002,2026-06-01,200,
P003,2026-06-01,150,测试员3"""

            csv_file = os.path.join(self.temp_dir, 'promotion_test.csv')
            with open(csv_file, 'w', encoding='utf-8') as f:
                f.write(csv_data)

            sandbox_manager.import_sample(
                sandbox_id_or_no=sandbox2_id,
                file_path=csv_file,
                source_type='meter',
                sample_name='提升测试样例',
                operator='promotion_tester'
            )

            sandbox_manager.add_rule(
                sandbox_id_or_no=sandbox2_id,
                rule_type='missing_fill',
                rule_name='填补操作员',
                target_field='operator',
                fill_value='默认操作员',
                operator='promotion_tester'
            )

            trial2 = sandbox_manager.run_trial(sandbox2_id, operator='promotion_tester')
            assert trial2['affected_rows'] == 1

            with get_db() as db:
                db.query(MeterReading).filter(
                    MeterReading.batch_id == self.test_data['batch_id'],
                    MeterReading.parcel_id == 'P002'
                ).update({'operator': None})

            promotion2 = sandbox_manager.promote_to_production(
                sandbox_id_or_no=sandbox2_id,
                trial_id=trial2['id'],
                target_batch_id=self.test_data['batch_id'],
                force=False,
                operator='promotion_tester'
            )

            assert promotion2['status'] == 'applied'
            assert promotion2['applied_rows'] >= 1
            self.results.append(TestResult('提升应用成功', True,
                f'应用ID: {promotion2["id"]}, 应用行数: {promotion2["applied_rows"]}'))

            with get_db() as db:
                reading = db.query(MeterReading).filter(
                    MeterReading.batch_id == self.test_data['batch_id'],
                    MeterReading.parcel_id == 'P002'
                ).first()
                assert reading.operator == '默认操作员'
            self.results.append(TestResult('数据修改验证', True,
                '数据库中的数据已被正确修改'))

            promotions = sandbox_manager.list_promotions(sandbox2_id)
            assert len(promotions) == 1
            self.results.append(TestResult('提升记录查询', True,
                f'沙盒的提升记录: {len(promotions)} 条'))

            all_promotions = sandbox_manager.list_promotions()
            assert len(all_promotions) >= 2
            self.results.append(TestResult('全局提升记录', True,
                f'系统全局提升记录: {len(all_promotions)} 条'))

            rollback2 = sandbox_manager.rollback_promotion(
                promotion_id=promotion2['id'],
                reason='清理测试数据',
                operator='cleanup_user'
            )
            assert rollback2['is_rolled_back'] == True
            self.results.append(TestResult('清理-回滚成功', True,
                '测试数据已回滚清理'))

            sandbox_manager.delete_sandbox(self.test_data.get('imported_sandbox_id', sandbox2_id),
                                         operator='cleanup_user')

        except Exception as e:
            self.results.append(TestResult('提升流程', False, str(e)))

        print()

    def _cleanup(self):
        """清理测试资源"""
        try:
            from . import database
            database.engine.dispose()
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            print(f'🧹 测试目录已清理')
        except Exception as e:
            print(f'⚠️  清理时发生错误: {e}')

    def _print_summary(self):
        """打印测试摘要"""
        print('=' * 80)
        print('📊 测试结果摘要')
        print('=' * 80)

        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)

        print()
        for result in self.results:
            print(f'  {result}')

        print()
        print('-' * 80)
        print(f'总计: {total} 项测试')
        print(f'  ✅ 通过: {passed}')
        print(f'  ❌ 失败: {failed}')
        print(f'  📊 通过率: {passed/total*100:.1f}%' if total > 0 else '')
        print('-' * 80)

        if failed == 0:
            print()
            print('🎉 所有测试通过！沙盒模块功能正常。')
        else:
            print()
            print(f'⚠️  有 {failed} 项测试失败，请检查。')

        print()
        print(f'⏱️  测试完成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')


def run_tests():
    """运行沙盒测试"""
    test_suite = SandboxTestSuite()
    return test_suite.run()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
