# -*- coding: utf-8 -*-
"""
验收测试脚本
验证完整的业务流程和所有可复现场景
"""
import os
import sys
import json
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR, DB_PATH, EXCEPTION_TYPES
from .database import init_db, get_db
from .models import Batch, Anomaly, ReportCache, Parcel
from .importer import DataImporter
from .rules import RuleEngine
from .batch_manager import batch_manager, review_manager, rollback_manager
from .reports import report_generator
from .sample_data import sample_data_generator


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


class AcceptanceTest:
    """验收测试套件"""

    def __init__(self):
        self.results: list[TestResult] = []
        self.test_data = {}

    def run(self) -> bool:
        """运行所有测试"""
        print('=' * 80)
        print('🌾 农田灌溉用水异常分析工具 - 验收测试')
        print('=' * 80)
        print(f'测试时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        print()

        try:
            self._cleanup_database()
            self._step_1_init_database()
            self._step_2_generate_sample_data()
            self._step_3_import_data()
            self._step_4_detect_anomalies()
            self._step_5_verify_expected_anomalies()
            self._step_10_verify_reproducible_scenarios()
            self._step_6_review_false_positive()
            self._step_7_rollback_batch()
            self._step_8_export_reports()
            self._step_9_verify_data_consistency()
        except Exception as e:
            self.results.append(TestResult('测试执行异常', False, str(e)))
        finally:
            self._print_summary()

        return all(r.passed for r in self.results)

    def _cleanup_database(self):
        """清理数据库"""
        if DB_PATH.exists():
            import time
            import gc
            gc.collect()
            from . import database
            try:
                database.engine.dispose()
            except:
                pass
            time.sleep(0.5)
            max_retries = 5
            for i in range(max_retries):
                try:
                    DB_PATH.unlink()
                    print('🧹 已清理旧数据库')
                    break
                except Exception as e:
                    if i < max_retries - 1:
                        time.sleep(0.5)
                        continue
                    print(f'⚠️  无法删除数据库文件: {e}')
                    raise

    def _step_1_init_database(self):
        """步骤1: 初始化数据库"""
        print('\n📋 步骤1: 初始化数据库')
        try:
            init_db()
            self.results.append(TestResult('数据库初始化', True))
            print('  ✅ 数据库初始化成功')
        except Exception as e:
            self.results.append(TestResult('数据库初始化', False, str(e)))
            raise

    def _step_2_generate_sample_data(self):
        """步骤2: 生成样例数据"""
        print('\n📋 步骤2: 生成样例数据')
        try:
            files = sample_data_generator.generate_all()
            self.test_data['sample_files'] = files

            for name, path in files.items():
                if not Path(path).exists():
                    raise FileNotFoundError(f'{name} 文件未生成: {path}')

            self.results.append(TestResult('样例数据生成', True))
            print('  ✅ 样例数据生成成功:')
            for name, path in files.items():
                print(f'     - {name}: {path}')

            print()
            sample_data_generator.print_expected_anomalies()
        except Exception as e:
            self.results.append(TestResult('样例数据生成', False, str(e)))
            raise

    def _step_3_import_data(self):
        """步骤3: 导入数据"""
        print('\n📋 步骤3: 导入数据')
        try:
            importer = DataImporter()
            files = self.test_data['sample_files']
            import_results = {}

            print('  导入地块台账...')
            result = importer.import_parcels(files['parcels'], '验收测试-地块台账')
            import_results['parcel'] = result
            print(f'    批次号: {result["batch_no"]}, 成功: {result["success_count"]}/{result["total_count"]}')
            assert result['success_count'] == 5, f'地块台账导入成功数应为5, 实际: {result["success_count"]}'

            print('  导入灌溉计划...')
            result = importer.import_plans(files['plans'], '验收测试-灌溉计划')
            import_results['plan'] = result
            print(f'    批次号: {result["batch_no"]}, 成功: {result["success_count"]}/{result["total_count"]}')
            assert result['success_count'] == 6, f'灌溉计划导入成功数应为6, 实际: {result["success_count"]}'
            assert result['error_count'] == 1, f'灌溉计划导入错误数应为1, 实际: {result["error_count"]}'

            print('  导入天气补录...')
            result = importer.import_weather(files['weather'], '验收测试-天气补录')
            import_results['weather'] = result
            print(f'    批次号: {result["batch_no"]}, 成功: {result["success_count"]}/{result["total_count"]}')
            assert result['success_count'] == 15, f'天气补录导入成功数应为15, 实际: {result["success_count"]}'

            print('  导入水表读数...')
            result = importer.import_meters(files['meters'], '验收测试-水表读数')
            import_results['meter'] = result
            print(f'    批次号: {result["batch_no"]}, 成功: {result["success_count"]}/{result["total_count"]}')
            print(f'    错误数: {result["error_count"]}')
            if result['errors']:
                print('    错误详情:')
                for err in result['errors']:
                    print(f'      - {err}')

            self.test_data['import_results'] = import_results
            self.test_data['meter_batch_id'] = import_results['meter']['batch_id']
            self.test_data['meter_batch_no'] = import_results['meter']['batch_no']

            self.results.append(TestResult('数据导入', True))
            print('  ✅ 数据导入完成')

        except AssertionError as e:
            self.results.append(TestResult('数据导入', False, str(e)))
            raise
        except Exception as e:
            self.results.append(TestResult('数据导入', False, str(e)))
            raise

    def _step_4_detect_anomalies(self):
        """步骤4: 异常检测"""
        print('\n📋 步骤4: 异常检测')
        try:
            engine = RuleEngine()
            anomalies = engine.detect_all()

            self.test_data['initial_anomalies'] = anomalies
            print(f'  检测到 {len(anomalies)} 条新异常')

            for a in anomalies[:10]:
                print(f'    #{a.get("id")} [{a["anomaly_code"]}] {a["description"][:60]}...')

            self.results.append(TestResult('异常检测', True))
            print('  ✅ 异常检测完成')

        except Exception as e:
            self.results.append(TestResult('异常检测', False, str(e)))
            raise

    def _step_5_verify_expected_anomalies(self):
        """步骤5: 验证预期异常类型"""
        print('\n📋 步骤5: 验证预期异常类型')
        try:
            anomalies = review_manager.list_anomalies()
            self.test_data['all_anomalies'] = anomalies

            anomaly_types = {}
            for a in anomalies:
                code = a['anomaly_code']
                anomaly_types[code] = anomaly_types.get(code, 0) + 1

            print('  检测到的异常类型统计:')
            for code, count in sorted(anomaly_types.items()):
                name = EXCEPTION_TYPES.get(code, code)
                expected = sample_data_generator.expected_anomalies.get(code, 0)
                status = '✅' if count >= expected else '❌'
                print(f'    {status} {code:<20} {name:<15} 预期: {expected:2d}, 实际: {count:2d}')

            expected_codes = set(sample_data_generator.expected_anomalies.keys())
            actual_codes = set(anomaly_types.keys())

            missing_codes = expected_codes - actual_codes
            if missing_codes:
                raise AssertionError(f'缺少预期的异常类型: {missing_codes}')

            for code, expected in sample_data_generator.expected_anomalies.items():
                actual = anomaly_types.get(code, 0)
                if actual < expected:
                    raise AssertionError(f'{code} 异常数量不足, 预期: {expected}, 实际: {actual}')

            self.results.append(TestResult('预期异常验证', True))
            print('  ✅ 所有预期异常类型均已检测到')

        except AssertionError as e:
            self.results.append(TestResult('预期异常验证', False, str(e)))
            raise
        except Exception as e:
            self.results.append(TestResult('预期异常验证', False, str(e)))
            raise

    def _step_6_review_false_positive(self):
        """步骤6: 复核一条误报"""
        print('\n📋 步骤6: 复核一条误报')
        try:
            anomalies = self.test_data['all_anomalies']
            unreviewed = [a for a in anomalies if not a['is_reviewed']]

            if not unreviewed:
                raise AssertionError('没有找到待复核的异常')

            anomaly_to_review = unreviewed[0]
            print(f'  选择异常 #{anomaly_to_review["id"]} 进行复核')
            print(f'    类型: {anomaly_to_review["anomaly_type"]}')
            print(f'    描述: {anomaly_to_review["description"][:80]}')

            result = review_manager.review_anomaly(
                anomaly_id=anomaly_to_review['id'],
                review_result='false_positive',
                review_comment='验收测试-标记为误报',
                reviewed_by='acceptance_test'
            )

            assert result['is_reviewed'] == True, '异常应标记为已复核'
            assert result['is_false_positive'] == True, '异常应标记为误报'
            assert result['review_result'] == 'false_positive', '复核结果应为false_positive'
            assert result['reviewed_by'] == 'acceptance_test', '复核人应为acceptance_test'

            self.test_data['reviewed_anomaly_id'] = anomaly_to_review['id']

            self.results.append(TestResult('误报复核', True))
            print(f'  ✅ 异常 #{anomaly_to_review["id"]} 已标记为误报')

        except AssertionError as e:
            self.results.append(TestResult('误报复核', False, str(e)))
            raise
        except Exception as e:
            self.results.append(TestResult('误报复核', False, str(e)))
            raise

    def _step_7_rollback_batch(self):
        """步骤7: 回滚批次"""
        print('\n📋 步骤7: 回滚批次')
        try:
            meter_batch_no = self.test_data['meter_batch_no']
            print(f'  回滚批次: {meter_batch_no}')

            before_count = len(review_manager.list_anomalies())
            print(f'  回滚前异常总数: {before_count}')

            result = rollback_manager.rollback_batch(
                batch_id_or_no=meter_batch_no,
                reason='验收测试-回滚水表读数批次',
                created_by='acceptance_test'
            )

            after_count = len(review_manager.list_anomalies())
            print(f'  回滚后异常总数: {after_count}')
            print(f'  回滚异常数: {result["anomalies_rolled_back"]}')
            print(f'  删除读数: {result["meters_deleted"]} 条')

            assert result['anomalies_rolled_back'] > 0, '应回滚至少一条异常'
            assert result['meters_deleted'] > 0, '应删除至少一条读数'
            assert after_count < before_count, '回滚后异常数应减少'

            self.test_data['rollback_result'] = result
            self.test_data['before_rollback_count'] = before_count
            self.test_data['after_rollback_count'] = after_count

            with get_db() as db:
                batch = db.query(Batch).filter(Batch.batch_no == meter_batch_no).first()
                assert batch.is_rolled_back == True, '批次应标记为已回滚'

            self.results.append(TestResult('批次回滚', True))
            print(f'  ✅ 批次 {meter_batch_no} 回滚成功')

        except AssertionError as e:
            self.results.append(TestResult('批次回滚', False, str(e)))
            raise
        except Exception as e:
            self.results.append(TestResult('批次回滚', False, str(e)))
            raise

    def _step_8_export_reports(self):
        """步骤8: 导出报告"""
        print('\n📋 步骤8: 导出报告')
        try:
            print('  生成HTML报告...')
            html_path = report_generator.export_html()
            print(f'    HTML报告: {html_path}')
            assert Path(html_path).exists(), 'HTML报告文件应存在'
            assert Path(html_path).stat().st_size > 0, 'HTML报告文件不应为空'

            print('  生成CSV报告...')
            csv_path = report_generator.export_csv()
            print(f'    CSV报告: {csv_path}')
            assert Path(csv_path).exists(), 'CSV报告文件应存在'
            assert Path(csv_path).stat().st_size > 0, 'CSV报告文件不应为空'

            summary = report_generator.generate_summary(use_cache=False)
            print(f'  报告统计: 异常总数={summary["summary"]["total_anomalies"]}')

            with get_db() as db:
                cache_count = db.query(ReportCache).count()
                print(f'  报告缓存数: {cache_count}')
                assert cache_count > 0, '应存在报告缓存'

            self.test_data['html_report'] = html_path
            self.test_data['csv_report'] = csv_path

            self.results.append(TestResult('报告导出', True))
            print('  ✅ 报告导出成功')

        except AssertionError as e:
            self.results.append(TestResult('报告导出', False, str(e)))
            raise
        except Exception as e:
            self.results.append(TestResult('报告导出', False, str(e)))
            raise

    def _step_9_verify_data_consistency(self):
        """步骤9: 验证重启后数据一致性"""
        print('\n📋 步骤9: 验证重启后数据一致性')
        try:
            before_summary = report_generator.generate_summary(use_cache=False)
            before_anomalies = review_manager.list_anomalies()
            before_batches = batch_manager.list_batches()
            before_rollbacks = rollback_manager.list_rollbacks()

            print(f'  重启前状态:')
            print(f'    异常总数: {before_summary["summary"]["total_anomalies"]}')
            print(f'    批次总数: {len(before_batches)}')
            print(f'    回滚记录: {len(before_rollbacks)}')
            print(f'    已复核: {before_summary["summary"]["review_status"]["reviewed"]}')
            print(f'    误报数: {before_summary["summary"]["review_status"]["false_positive"]}')

            print('  模拟重启 - 重新连接数据库...')
            import importlib
            from . import database
            importlib.reload(database)
            database.init_db()

            after_summary = report_generator.generate_summary(use_cache=True)
            after_anomalies = review_manager.list_anomalies()
            after_batches = batch_manager.list_batches()
            after_rollbacks = rollback_manager.list_rollbacks()

            print(f'  重启后状态:')
            print(f'    异常总数: {after_summary["summary"]["total_anomalies"]}')
            print(f'    批次总数: {len(after_batches)}')
            print(f'    回滚记录: {len(after_rollbacks)}')
            print(f'    已复核: {after_summary["summary"]["review_status"]["reviewed"]}')
            print(f'    误报数: {after_summary["summary"]["review_status"]["false_positive"]}')

            assert before_summary['summary']['total_anomalies'] == after_summary['summary']['total_anomalies'], \
                '重启后异常总数应一致'
            assert len(before_batches) == len(after_batches), '重启后批次总数应一致'
            assert len(before_rollbacks) == len(after_rollbacks), '重启后回滚记录应一致'
            assert before_summary['summary']['review_status']['reviewed'] == after_summary['summary']['review_status']['reviewed'], \
                '重启后已复核数应一致'
            assert before_summary['summary']['review_status']['false_positive'] == after_summary['summary']['review_status']['false_positive'], \
                '重启后误报数应一致'

            self.results.append(TestResult('重启数据一致性', True))
            print('  ✅ 重启后数据一致')

        except AssertionError as e:
            self.results.append(TestResult('重启数据一致性', False, str(e)))
            raise
        except Exception as e:
            self.results.append(TestResult('重启数据一致性', False, str(e)))
            raise

    def _step_10_verify_reproducible_scenarios(self):
        """步骤10: 验证可复现场景"""
        print('\n📋 步骤10: 验证可复现场景')
        try:
            scenarios = [
                ('缺少地块编号', 'MISSING_PARCEL_ID', '样例数据中水表读数有一行地块编号为空'),
                ('日期格式错误', 'INVALID_DATE', '样例数据中有一行使用了不支持的日期格式 2025.06.01'),
                ('读数冲突', 'READING_CONFLICT', 'P004 同一时间有不同的读数'),
                ('引用不存在地块', 'INVALID_REFERENCE', '引用了 P888 和 P999 等不存在的地块'),
                ('超计划用水', 'OVER_PLAN', 'P001 6月用水远超计划'),
                ('倒表', 'METER_BACKWARD', 'P002 有一次读数小于上一次'),
                ('漏采', 'MISSING_READING', 'P003 两次读数间隔超过25小时'),
                ('重复上报', 'DUPLICATE_REPORT', 'P004 同一读数重复上报'),
                ('未知地块', 'UNKNOWN_PARCEL', 'P999 未在地块台账中登记'),
            ]

            anomalies = review_manager.list_anomalies()
            anomaly_codes = {a['anomaly_code'] for a in anomalies}

            for name, code, desc in scenarios:
                present = code in anomaly_codes
                status = '✅' if present else '❌'
                print(f'  {status} {name} ({code}):')
                print(f'     {desc}')
                if not present:
                    raise AssertionError(f'可复现场景「{name}」未检测到')

            self.results.append(TestResult('可复现场景验证', True))
            print('  ✅ 所有可复现场景均已验证')

        except AssertionError as e:
            self.results.append(TestResult('可复现场景验证', False, str(e)))
            raise
        except Exception as e:
            self.results.append(TestResult('可复现场景验证', False, str(e)))
            raise

    def _print_summary(self):
        """打印测试摘要"""
        print('\n' + '=' * 80)
        print('📊 测试结果摘要')
        print('=' * 80)

        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed

        print(f'\n总计: {len(self.results)} 个测试')
        print(f'  ✅ 通过: {passed}')
        print(f'  ❌ 失败: {failed}')
        print()

        for result in self.results:
            print(result)

        print()
        if failed == 0:
            print('🎉 所有测试通过！验收成功！')
            print('\n📝 验收流程总结:')
            print('  1. ✅ 初始化数据库')
            print('  2. ✅ 生成样例数据')
            print('  3. ✅ 导入所有数据（地块、计划、天气、水表）')
            print('  4. ✅ 异常检测，发现所有预期异常类型')
            print('  5. ✅ 验证9种异常类型均被检测到')
            print('  6. ✅ 复核一条异常为误报')
            print('  7. ✅ 回滚水表读数批次')
            print('  8. ✅ 导出HTML和CSV报告')
            print('  9. ✅ 验证重启后数据一致性')
            print('  10. ✅ 验证9种可复现场景')
            print()
            print('🌾 农田灌溉用水异常分析工具验收完成！')
        else:
            print(f'❌ 有 {failed} 个测试失败，请检查相关功能。')
            sys.exit(1)

        print('=' * 80)


def run_acceptance_test() -> bool:
    """运行验收测试"""
    test = AcceptanceTest()
    return test.run()


if __name__ == '__main__':
    success = run_acceptance_test()
    sys.exit(0 if success else 1)
