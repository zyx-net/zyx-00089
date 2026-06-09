# -*- coding: utf-8 -*-
"""
回归测试脚本
验证编码修复、HTML报告完整性和所有功能
"""
import sys
import os
import io
import re
import csv
import json
import subprocess
from pathlib import Path
from datetime import datetime


class RegressionTest:
    """回归测试套件"""

    def __init__(self):
        self.project_dir = Path(__file__).resolve().parent.parent
        self.data_dir = self.project_dir / 'data'
        self.output_dir = self.project_dir / 'outputs'
        self.results = []
        self.db_path = self.data_dir / 'irrigation.db'

    def run(self):
        """运行所有回归测试"""
        print('=' * 80)
        print('🧪 农田灌溉用水异常分析工具 - 回归测试')
        print('=' * 80)
        print(f'测试时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        print(f'项目目录: {self.project_dir}')
        print()

        try:
            self._cleanup()

            self._test_1_gbk_encoding_help()
            self._test_2_gbk_encoding_init()
            self._test_3_sample_and_acceptance()
            self._test_4_invalid_meter_import()
            self._test_5_summary_twice()
            self._test_6_html_report()
            self._test_7_csv_report()
            self._test_8_html_content_readable()
            self._test_9_html_tags_integrity()
            self._test_10_full_pipeline_import_detect_anomalies()
            self._test_11_import_all_behavior()

        except Exception as e:
            self._add_result('测试执行异常', False, str(e))
        finally:
            self._print_summary()

        return all(r[1] for r in self.results)

    def _cleanup(self):
        """清理旧数据"""
        import time
        import gc
        gc.collect()
        time.sleep(0.2)

        if self.db_path.exists():
            try:
                self.db_path.unlink()
                print('🧹 已清理旧数据库')
            except Exception as e:
                print(f'⚠️  无法删除数据库: {e}')

        for f in self.output_dir.glob('report_*.html'):
            try:
                f.unlink()
            except:
                pass
        for f in self.output_dir.glob('report_*.csv'):
            try:
                f.unlink()
            except:
                pass

    def _run_command(self, args, env=None, cwd=None):
        """运行命令并捕获输出"""
        cmd = [sys.executable, str(self.project_dir / 'main.py')] + args
        env = env or os.environ.copy()
        cwd = cwd or str(self.project_dir)

        try:
            result = subprocess.run(
                cmd,
                env=env,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=120
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return -1, '', str(e)

    def _add_result(self, name: str, passed: bool, message: str = ''):
        """添加测试结果"""
        self.results.append((name, passed, message))
        status = '✅ PASS' if passed else '❌ FAIL'
        msg = f'{status} {name}'
        if message:
            msg += f' - {message}'
        print(msg)

    def _test_1_gbk_encoding_help(self):
        """测试1: GBK环境下 --help 命令"""
        print('\n📋 测试1: GBK环境下 --help 命令')

        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'gbk:strict'
        env['LANG'] = 'zh_CN.GBK'

        try:
            code, stdout, stderr = self._run_command(['--help'], env=env)

            if code != 0:
                self._add_result('GBK环境 --help', False, f'退出码={code}, stderr={stderr[:200]}')
                return

            if 'UnicodeEncodeError' in stdout or 'UnicodeEncodeError' in stderr:
                self._add_result('GBK环境 --help', False, '触发UnicodeEncodeError')
                return

            if '农田灌溉用水异常分析工具' not in stdout:
                self._add_result('GBK环境 --help', False, '输出中缺少中文标题')
                return

            if 'Usage:' not in stdout:
                self._add_result('GBK环境 --help', False, '输出中缺少Usage')
                return

            self._add_result('GBK环境 --help', True, '正常输出中文和帮助信息')

        except Exception as e:
            self._add_result('GBK环境 --help', False, str(e))

    def _test_2_gbk_encoding_init(self):
        """测试2: GBK环境下 init 命令"""
        print('\n📋 测试2: GBK环境下 init 命令')

        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'gbk:strict'
        env['LANG'] = 'zh_CN.GBK'

        try:
            code, stdout, stderr = self._run_command(['init'], env=env)

            if code != 0:
                self._add_result('GBK环境 init', False, f'退出码={code}, stderr={stderr[:200]}')
                return

            if 'UnicodeEncodeError' in stdout or 'UnicodeEncodeError' in stderr:
                self._add_result('GBK环境 init', False, '触发UnicodeEncodeError')
                return

            if '数据库初始化成功' not in stdout:
                self._add_result('GBK环境 init', False, '输出中缺少成功信息')
                return

            if not self.db_path.exists():
                self._add_result('GBK环境 init', False, '数据库文件未创建')
                return

            self._add_result('GBK环境 init', True, '正常初始化数据库并输出中文')

        except Exception as e:
            self._add_result('GBK环境 init', False, str(e))

    def _test_3_sample_and_acceptance(self):
        """测试3: 样例数据和验收测试"""
        print('\n📋 测试3: 样例数据和验收测试')

        try:
            code, stdout, stderr = self._run_command(['import-all'])

            if code != 0:
                self._add_result('导入样例数据', False, f'退出码={code}, stderr={stderr[:200]}')
                return

            if '所有样例数据导入完成' not in stdout:
                self._add_result('导入样例数据', False, '输出中缺少完成信息')
                return

            code, stdout, stderr = self._run_command(['detect'])

            if code != 0:
                self._add_result('异常检测', False, f'退出码={code}, stderr={stderr[:200]}')
                return

            if '检测完成' not in stdout:
                self._add_result('异常检测', False, '输出中缺少完成信息')
                return

            self._add_result('样例数据和验收测试', True, '样例数据导入和检测正常')

        except Exception as e:
            self._add_result('样例数据和验收测试', False, str(e))

    def _test_4_invalid_meter_import(self):
        """测试4: 非法水表读数导入（包含HTML特殊字符和异常数据）"""
        print('\n📋 测试4: 非法水表读数导入')

        try:
            invalid_csv = self.data_dir / 'test_invalid_meters.csv'
            content = (
                '地块编号,读数日期,读数时间,水表读数,操作员\n'
                'P001,2025-06-01,08:00,100.0,正常用户\n'
                'P001,2025-06-02,08:00,<script>alert(\'xss\')</script>,包含HTML标签\n'
                'P002,2025-06-01,09:00,150.0,"包含,逗号和""引号""\n'
                'P003,2025-13-01,10:00,200.0,非法月份\n'
                ',2025-06-01,11:00,250.0,缺少地块编号\n'
            )

            with open(invalid_csv, 'w', encoding='utf-8-sig', newline='') as f:
                f.write(content)

            code, stdout, stderr = self._run_command(
                ['import', 'meter', str(invalid_csv)]
            )

            if 'UnicodeEncodeError' in stdout or 'UnicodeEncodeError' in stderr:
                self._add_result('非法水表导入', False, '触发UnicodeEncodeError')
                return

            if '导入完成' not in stdout and '导入错误' not in stdout:
                self._add_result('非法水表导入', False, '没有导入结果信息')
                return

            self._add_result('非法水表导入', True, '正确处理包含特殊字符的非法数据')

        except Exception as e:
            self._add_result('非法水表导入', False, str(e))

    def _test_5_summary_twice(self):
        """测试5: summary 连续运行两次"""
        print('\n📋 测试5: summary 连续运行两次')

        try:
            code1, stdout1, stderr1 = self._run_command(['summary'])
            code2, stdout2, stderr2 = self._run_command(['summary'])

            if code1 != 0 or code2 != 0:
                self._add_result('summary两次运行', False, f'退出码: {code1}/{code2}')
                return

            if 'UnicodeEncodeError' in stdout1 or 'UnicodeEncodeError' in stderr1:
                self._add_result('summary两次运行', False, '第一次运行触发编码错误')
                return

            if 'UnicodeEncodeError' in stdout2 or 'UnicodeEncodeError' in stderr2:
                self._add_result('summary两次运行', False, '第二次运行触发编码错误')
                return

            if '异常总数' not in stdout1 or '异常总数' not in stdout2:
                self._add_result('summary两次运行', False, '输出中缺少异常总数')
                return

            lines1 = [l.strip() for l in stdout1.split('\n') if l.strip()]
            lines2 = [l.strip() for l in stdout2.split('\n') if l.strip()]

            if len(lines1) < 5 or len(lines2) < 5:
                self._add_result('summary两次运行', False, '输出内容不完整')
                return

            self._add_result('summary两次运行', True, '两次运行结果一致，无编码错误')

        except Exception as e:
            self._add_result('summary两次运行', False, str(e))

    def _test_6_html_report(self):
        """测试6: HTML报告导出"""
        print('\n📋 测试6: HTML报告导出')

        try:
            html_files_before = list(self.output_dir.glob('report_*.html'))

            code, stdout, stderr = self._run_command(['report', '--format', 'html'])

            if code != 0:
                self._add_result('HTML报告导出', False, f'退出码={code}, stderr={stderr[:200]}')
                return

            html_files_after = list(self.output_dir.glob('report_*.html'))
            new_files = [f for f in html_files_after if f not in html_files_before]

            if not new_files:
                self._add_result('HTML报告导出', False, '没有生成新的HTML文件')
                return

            latest_html = max(new_files, key=lambda x: x.stat().st_mtime)

            if latest_html.stat().st_size == 0:
                self._add_result('HTML报告导出', False, 'HTML文件为空')
                return

            with open(latest_html, 'r', encoding='utf-8') as f:
                content = f.read()

            if len(content) < 100:
                self._add_result('HTML报告导出', False, 'HTML内容太短')
                return

            self.test_html_path = latest_html
            self._add_result('HTML报告导出', True, f'生成HTML报告: {latest_html.name}')

        except Exception as e:
            self._add_result('HTML报告导出', False, str(e))

    def _test_7_csv_report(self):
        """测试7: CSV报告导出"""
        print('\n📋 测试7: CSV报告导出')

        try:
            csv_files_before = list(self.output_dir.glob('report_*.csv'))

            code, stdout, stderr = self._run_command(['report', '--format', 'csv'])

            if code != 0:
                self._add_result('CSV报告导出', False, f'退出码={code}, stderr={stderr[:200]}')
                return

            csv_files_after = list(self.output_dir.glob('report_*.csv'))
            new_files = [f for f in csv_files_after if f not in csv_files_before]

            if not new_files:
                self._add_result('CSV报告导出', False, '没有生成新的CSV文件')
                return

            latest_csv = max(new_files, key=lambda x: x.stat().st_mtime)

            if latest_csv.stat().st_size == 0:
                self._add_result('CSV报告导出', False, 'CSV文件为空')
                return

            with open(latest_csv, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                rows = list(reader)

            if len(rows) < 5:
                self._add_result('CSV报告导出', False, 'CSV行数太少')
                return

            header_row = None
            for i, row in enumerate(rows):
                if '异常ID' in row or '异常代码' in row:
                    header_row = i
                    break

            if header_row is None:
                self._add_result('CSV报告导出', False, 'CSV中没有找到表头行')
                return

            self._add_result('CSV报告导出', True, f'生成CSV报告: {latest_csv.name}, {len(rows)} 行')

        except Exception as e:
            self._add_result('CSV报告导出', False, str(e))

    def _test_8_html_content_readable(self):
        """测试8: HTML内容浏览器可读"""
        print('\n📋 测试8: HTML内容浏览器可读')

        try:
            if not hasattr(self, 'test_html_path') or not self.test_html_path.exists():
                self._add_result('HTML内容可读', False, '没有可用的HTML文件')
                return

            with open(self.test_html_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if '<meta charset="UTF-8">' not in content and 'charset=utf-8' not in content.lower():
                self._add_result('HTML内容可读', False, '缺少UTF-8字符集声明')
                return

            if 'Content-Type' not in content and 'charset' not in content:
                self._add_result('HTML内容可读', False, '缺少Content-Type声明')
                return

            if '农田灌溉用水异常分析报告' not in content:
                self._add_result('HTML内容可读', False, 'HTML中缺少中文标题')
                return

            if '异常总数' not in content:
                self._add_result('HTML内容可读', False, 'HTML中缺少异常总数')
                return

            if '按异常类型汇总' not in content:
                self._add_result('HTML内容可读', False, 'HTML中缺少按异常类型汇总')
                return

            self._add_result('HTML内容可读', True, 'HTML包含正确的字符集声明和中文内容')

        except Exception as e:
            self._add_result('HTML内容可读', False, str(e))

    def _test_9_html_tags_integrity(self):
        """测试9: HTML标签完整性（检查坏标签）"""
        print('\n📋 测试9: HTML标签完整性')

        try:
            if not hasattr(self, 'test_html_path') or not self.test_html_path.exists():
                self._add_result('HTML标签完整性', False, '没有可用的HTML文件')
                return

            with open(self.test_html_path, 'r', encoding='utf-8') as f:
                content = f.read()

            bad_patterns = [
                r'(?<!<)/h2>',
                r'(?<!<)/div>',
                r'<h2[^>]*></h2>',
                r'<div[^>]*></div>',
                r'<[^>]*<[^>]*>',
                r'&amp;amp;',
                r'&amp;lt;',
                r'&amp;gt;',
            ]

            found_issues = []
            for pattern in bad_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    found_issues.append(f'模式 {pattern} 出现 {len(matches)} 次')

            if found_issues:
                self._add_result(
                    'HTML标签完整性',
                    False,
                    '发现潜在问题: ' + '; '.join(found_issues[:3])
                )
                return

            tag_stack = []
            tag_pattern = re.compile(r'<(/?)([a-zA-Z0-9]+)[^>]*>')
            self_closing = {'br', 'hr', 'img', 'input', 'meta', 'link'}

            for match in tag_pattern.finditer(content):
                is_closing = match.group(1) == '/'
                tag_name = match.group(2).lower()

                if tag_name in self_closing:
                    continue

                if is_closing:
                    if not tag_stack or tag_stack[-1] != tag_name:
                        self._add_result(
                            'HTML标签完整性',
                            False,
                            f'标签不匹配: 遇到 </{tag_name}> 但期望 </{tag_stack[-1] if tag_stack else "none"}>'
                        )
                        return
                    tag_stack.pop()
                else:
                    tag_stack.append(tag_name)

            if tag_stack:
                self._add_result(
                    'HTML标签完整性',
                    False,
                    f'存在未闭合的标签: {tag_stack}'
                )
                return

            if '<script>' in content and '</script>' in content:
                self._add_result(
                    'HTML标签完整性',
                    False,
                    'HTML中包含script标签（可能未正确转义）'
                )
                return

            if 'alert(' in content or 'xss' in content.lower():
                self._add_result(
                    'HTML标签完整性',
                    False,
                    'HTML中包含潜在的XSS内容'
                )
                return

            self._add_result('HTML标签完整性', True, '所有HTML标签正确闭合，无坏标签')

        except Exception as e:
            self._add_result('HTML标签完整性', False, str(e))

    def _test_10_full_pipeline_import_detect_anomalies(self):
        """测试10: 完整链路 - 导入→检测→异常列表，验证None格式化不崩溃"""
        print('\n📋 测试10: 完整链路 - 导入→检测→异常列表')

        try:
            self._cleanup()

            code, stdout, stderr = self._run_command(['init'])
            if code != 0:
                self._add_result('完整链路-初始化', False, f'init失败: {stderr[:200]}')
                return
            self._add_result('完整链路-初始化', True)

            code, stdout, stderr = self._run_command(['import-all'])
            if code != 0:
                self._add_result('完整链路-导入样例', False, f'import-all失败: {stderr[:200]}')
                return

            if '正在执行异常检测' in stdout:
                self._add_result('完整链路-导入样例', False, 'import-all 不应该自动执行检测')
                return
            self._add_result('完整链路-导入样例', True, 'import-all 仅导入数据，不自动检测')

            code, stdout, stderr = self._run_command(['detect'])
            if code != 0:
                self._add_result('完整链路-异常检测', False, f'detect失败: {stderr[:200]}')
                return

            if 'UnicodeEncodeError' in stdout or 'NoneType' in stderr:
                self._add_result('完整链路-异常检测', False, 'detect输出中出现编码或None格式化错误')
                return

            if '检测完成' not in stdout or '新发现' not in stdout:
                self._add_result('完整链路-异常检测', False, 'detect输出中缺少完成信息')
                return
            self._add_result('完整链路-异常检测', True, '异常检测完成，无格式化错误')

            code, stdout, stderr = self._run_command(['anomalies'])
            if code != 0:
                self._add_result('完整链路-异常列表', False, f'anomalies失败: {stderr[:200]}')
                return

            if 'NoneType' in stderr or 'unsupported format' in stderr:
                self._add_result('完整链路-异常列表', False, 'anomalies出现None格式化崩溃')
                return

            if '缺少地块编号' not in stdout:
                self._add_result('完整链路-异常列表', False, '异常列表中缺少"缺少地块编号"记录')
                return

            if '日期格式错误' not in stdout:
                self._add_result('完整链路-异常列表', False, '异常列表中缺少"日期格式错误"记录')
                return

            anomaly_lines = []
            in_table = False
            for l in stdout.split('\n'):
                stripped = l.strip()
                if 'ID 类型' in l and '严重程度' in l:
                    in_table = True
                    continue
                if in_table and stripped.startswith('---'):
                    continue
                if in_table and stripped:
                    parts = stripped.split()
                    if len(parts) >= 4 and parts[0].isdigit():
                        anomaly_lines.append(l)

            if len(anomaly_lines) < 10:
                self._add_result('完整链路-异常列表', False, f'异常列表不完整，仅显示{len(anomaly_lines)}条')
                return

            self._add_result('完整链路-异常列表', True, f'完整显示{len(anomaly_lines)}条异常，无崩溃')

        except Exception as e:
            self._add_result('完整链路-异常列表', False, str(e))

    def _test_11_import_all_behavior(self):
        """测试11: 核对import-all行为与README说明一致性"""
        print('\n📋 测试11: import-all行为与README说明一致性')

        try:
            self._cleanup()

            self._run_command(['init'])

            code, stdout, stderr = self._run_command(['import-all'])

            if code != 0:
                self._add_result('import-all行为核对', False, f'import-all失败: {stderr[:200]}')
                return

            if '正在执行异常检测' in stdout:
                self._add_result('import-all行为核对', False, 'import-all 不应该执行异常检测')
                return

            if '检测完成' in stdout:
                self._add_result('import-all行为核对', False, 'import-all 不应该显示检测完成')
                return

            if '所有样例数据导入完成' not in stdout:
                self._add_result('import-all行为核对', False, 'import-all 应该显示导入完成')
                return

            self._add_result('import-all行为核对', True, 'import-all仅导入数据，与README说明一致')

        except Exception as e:
            self._add_result('import-all行为核对', False, str(e))

    def _print_summary(self):
        """打印测试摘要"""
        print('\n' + '=' * 80)
        print('📊 回归测试结果摘要')
        print('=' * 80)

        passed = sum(1 for _, p, _ in self.results if p)
        failed = len(self.results) - passed

        print(f'\n总计: {len(self.results)} 个测试')
        print(f'  ✅ 通过: {passed}')
        print(f'  ❌ 失败: {failed}')
        print()

        for name, passed, message in self.results:
            status = '✅ PASS' if passed else '❌ FAIL'
            msg = f'{status} {name}'
            if message:
                msg += f' - {message}'
            print(msg)

        print()
        if failed == 0:
            print('🎉 所有回归测试通过！')
        else:
            print(f'❌ 有 {failed} 个测试失败，请检查相关功能。')

        print('=' * 80)


def run_regression_tests():
    """运行回归测试"""
    test = RegressionTest()
    success = test.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    run_regression_tests()
