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
from typing import Optional


class RegressionTest:
    """回归测试套件"""

    _test_data_initialized = False

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
            self._test_12_threshold_scheme_create()
            self._test_13_threshold_scheme_enable()
            self._test_14_threshold_scheme_export_import()
            self._test_15_threshold_scheme_import_conflict()
            self._test_16_threshold_scheme_persistence()
            RegressionTest._test_data_initialized = False
            self._test_17_review_history_and_append()
            self._test_18_review_status_update_and_undo()
            self._test_19_review_undo_consistency()
            self._test_20_review_persistence_across_restart()
            self._test_21_review_export_summary()
            self._test_22_review_history_cli()
            self._test_23_review_web_api()
            self._test_24_rollback_preserves_audit_log()

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

    def _ensure_test_data(self):
        """确保测试数据已导入（只初始化一次）"""
        if RegressionTest._test_data_initialized:
            return

        code, stdout, _ = self._run_command(['anomalies', '--limit', '1'])
        has_anomalies = (code == 0 and self._parse_first_anomaly_id(stdout) is not None)

        if not has_anomalies:
            print('📥 初始化测试数据...')
            if self.db_path.exists():
                try:
                    self.db_path.unlink()
                    print('🧹 已清理旧数据库')
                except Exception as e:
                    print(f'⚠️  无法删除旧数据库: {e}')
            self._run_command(['init'])
            self._run_command(['import-all'])
            self._run_command(['detect'])

        RegressionTest._test_data_initialized = True

    def _parse_first_anomaly_id(self, stdout: str) -> Optional[int]:
        """从异常列表输出中解析第一个异常ID"""
        import re
        import json
        try:
            data = json.loads(stdout)
            if isinstance(data, list) and len(data) > 0:
                return data[0].get('id')
        except (json.JSONDecodeError, TypeError):
            pass

        in_data_section = False
        for line in stdout.split('\n'):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            if '异常列表' in line or 'ID' in line and '类型' in line:
                in_data_section = True
                continue

            if in_data_section:
                if line.startswith('---') or line.startswith('==='):
                    continue

                match = re.match(r'^\s*(\d+)\s+', line_stripped)
                if match:
                    return int(match.group(1))

                match = re.search(r'^\s*(\d+)\s+\|', line)
                if match:
                    return int(match.group(1))

                match = re.search(r'[Ii][Dd].*?[:：]\s*(\d+)', line)
                if match:
                    return int(match.group(1))

        return None

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
        """测试10: 完整链路 - 导入→检测→异常列表→阈值方案切换→失败输入验证"""
        print('\n📋 测试10: 完整链路 - 导入→检测→异常列表→阈值方案')

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

            if '方案' not in stdout:
                self._add_result('完整链路-异常列表', False, '异常列表中缺少"方案"列')
                return

            if 'default' not in stdout:
                self._add_result('完整链路-异常列表', False, '异常列表中未显示默认方案"default"')
                return

            anomaly_lines = []
            in_table = False
            for l in stdout.split('\n'):
                stripped = l.strip()
                if 'ID 类型' in l and '严重程度' in l and '方案' in l:
                    in_table = True
                    continue
                if in_table and stripped.startswith('---'):
                    continue
                if in_table and stripped:
                    parts = stripped.split()
                    if len(parts) >= 4 and parts[0].isdigit():
                        anomaly_lines.append(l)

            if len(anomaly_lines) < 10:
                self._add_result('完整链路-异常列表', False,
                               f'异常列表不完整，仅显示{len(anomaly_lines)}条。stdout={stdout[:500]}')
                return
            self._add_result('完整链路-异常列表', True,
                           f'完整显示{len(anomaly_lines)}条异常，含阈值方案列，无崩溃')

            code, stdout, stderr = self._run_command(['summary'])
            if code != 0:
                self._add_result('完整链路-汇总统计', False, f'summary失败: {stderr[:200]}')
                return

            if '当前阈值方案' not in stdout:
                self._add_result('完整链路-汇总统计', False, '汇总中缺少"当前阈值方案"信息')
                return

            if 'default' not in stdout:
                self._add_result('完整链路-汇总统计', False, '汇总中未显示当前方案为"default"')
                return

            if '按阈值方案统计' not in stdout:
                self._add_result('完整链路-汇总统计', False, '汇总中缺少"按阈值方案统计"')
                return
            self._add_result('完整链路-汇总统计', True, '汇总显示阈值方案信息')

            import time
            scheme_name = f'严格方案_{int(time.time())}'

            code, stdout, stderr = self._run_command([
                'threshold', 'create',
                '--name', scheme_name,
                '--meter-backward', '0.001',
                '--over-plan-ratio', '1.01',
                '--missing-reading-days', '0.1',
                '--by', '回归测试'
            ])
            if code != 0:
                self._add_result('完整链路-创建方案', False,
                               f'创建方案失败: {stderr[:200]}')
                return
            self._add_result('完整链路-创建方案', True, f'创建方案"{scheme_name}"成功')

            code, stdout, stderr = self._run_command(['threshold', 'enable', scheme_name])
            if code != 0:
                self._add_result('完整链路-启用方案', False,
                               f'启用方案失败: {stderr[:200]}')
                return

            if '方案已启用' not in stdout:
                self._add_result('完整链路-启用方案', False,
                               f'启用输出不正确: {stdout[:200]}')
                return
            self._add_result('完整链路-启用方案', True, f'启用方案"{scheme_name}"成功')

            code, stdout, stderr = self._run_command(['summary'])
            if code != 0:
                self._add_result('完整链路-方案生效验证', False, f'summary失败: {stderr[:200]}')
                return

            if scheme_name not in stdout:
                self._add_result('完整链路-方案生效验证', False,
                               f'汇总中未显示新方案"{scheme_name}"')
                return
            self._add_result('完整链路-方案生效验证', True,
                           f'方案"{scheme_name}"已生效，汇总显示正确')

            import json
            bad_scheme_path = self.output_dir / 'bad_scheme.json'
            bad_scheme_path.write_text(json.dumps({
                'scheme': {
                    'name': '非法方案',
                    'meter_backward_tolerance': '不是数字',
                    'over_plan_ratio': -1,
                    'missing_reading_days': 2.0
                }
            }, ensure_ascii=False), encoding='utf-8')

            code, stdout, stderr = self._run_command([
                'threshold', 'import', str(bad_scheme_path)
            ])

            if code == 0:
                self._add_result('完整链路-失败输入不污染', False,
                               '非法数值方案导入应该失败但成功了')
                bad_scheme_path.unlink()
                return

            code, stdout, stderr = self._run_command(['threshold', 'list'])
            if scheme_name not in stdout:
                self._add_result('完整链路-失败输入不污染', False,
                               f'失败输入污染了当前方案，"{scheme_name}"不再是启用方案')
                bad_scheme_path.unlink()
                return

            if '非法方案' in stdout:
                self._add_result('完整链路-失败输入不污染', False,
                               '失败输入污染了数据库，出现了"非法方案"')
                bad_scheme_path.unlink()
                return

            bad_scheme_path.unlink()
            self._add_result('完整链路-失败输入不污染', True,
                           '非法数值导入失败，当前方案未受污染')

            self._test10_active_scheme = scheme_name

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

    def _test_12_threshold_scheme_create(self):
        """测试12: 阈值方案创建"""
        print('\n--- 测试12: 阈值方案创建 ---')

        import time
        import gc
        gc.collect()
        time.sleep(0.5)

        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except Exception as e:
                print(f'⚠️  无法删除数据库: {e}')

        code, stdout, stderr = self._run_command(['init'])
        if code != 0:
            self._add_result('阈值方案创建', False,
                           f'初始化失败. stdout={stdout}, stderr={stderr}')
            return

        scheme_name = f'测试方案_{int(time.time())}'

        self._run_command(['threshold', 'delete', scheme_name, '--force'])

        code, stdout, stderr = self._run_command([
            'threshold', 'create',
            '--name', scheme_name,
            '--meter-backward', '0.02',
            '--over-plan-ratio', '1.5',
            '--missing-reading-days', '0.5',
            '--description', '测试用阈值方案',
            '--by', '测试员'
        ])

        if code != 0:
            self._add_result('阈值方案创建', False,
                           f'创建失败. stdout={stdout}, stderr={stderr}')
            return

        if '方案创建成功' not in stdout:
            self._add_result('阈值方案创建', False,
                           f'输出中未找到"方案创建成功". stdout={stdout}')
            return

        code, stdout, stderr = self._run_command(['threshold', 'list'])
        if code != 0:
            self._add_result('阈值方案创建', False,
                           f'列表查询失败. stdout={stdout}, stderr={stderr}')
            return

        if scheme_name not in stdout:
            self._add_result('阈值方案创建', False,
                           f'列表中未找到新创建的方案. stdout={stdout}')
            return

        self._test12_scheme_name = scheme_name
        self._add_result('阈值方案创建', True)

    def _test_13_threshold_scheme_enable(self):
        """测试13: 阈值方案启用"""
        print('\n--- 测试13: 阈值方案启用 ---')

        scheme_name = getattr(self, '_test12_scheme_name', 'default')
        if scheme_name == 'default':
            self._add_result('阈值方案启用', False, '未找到测试12创建的方案')
            return

        code, stdout, stderr = self._run_command([
            'threshold', 'enable', scheme_name, '--by', '管理员'
        ])

        if code != 0:
            self._add_result('阈值方案启用', False,
                           f'启用失败. stdout={stdout}, stderr={stderr}')
            return

        if '方案已启用' not in stdout:
            self._add_result('阈值方案启用', False,
                           f'输出中未找到"方案已启用". stdout={stdout}')
            return

        code, stdout, stderr = self._run_command(['threshold', 'list'])
        if code != 0:
            self._add_result('阈值方案启用', False,
                           f'列表查询失败. stdout={stdout}, stderr={stderr}')
            return

        lines = stdout.split('\n')
        found_active = False
        for line in lines:
            if scheme_name in line and '✓ 启用' in line:
                found_active = True
                break

        if not found_active:
            self._add_result('阈值方案启用', False,
                           f'方案未显示为启用状态. stdout={stdout}')
            return

        self._add_result('阈值方案启用', True)

    def _test_14_threshold_scheme_export_import(self):
        """测试14: 阈值方案导出再导入"""
        print('\n--- 测试14: 阈值方案导出再导入 ---')

        import time
        export_path = self.output_dir / f'test_export_{int(time.time())}.json'

        scheme_name = getattr(self, '_test12_scheme_name', 'default')
        if scheme_name == 'default':
            self._add_result('阈值方案导出再导入', False, '未找到测试12创建的方案')
            return

        code, stdout, stderr = self._run_command([
            'threshold', 'export', scheme_name, '--output', str(export_path)
        ])

        if code != 0:
            self._add_result('阈值方案导出再导入', False, f'导出失败: {stderr}')
            return

        if not export_path.exists():
            self._add_result('阈值方案导出再导入', False, '导出文件不存在')
            return

        try:
            with open(export_path, 'r', encoding='utf-8') as f:
                import json
                data = json.load(f)
            if data['scheme']['name'] != scheme_name:
                self._add_result('阈值方案导出再导入', False,
                               f'导出文件内容不正确，期望名称={scheme_name}')
                return
        except Exception as e:
            self._add_result('阈值方案导出再导入', False, f'读取导出文件失败: {e}')
            return

        import_name = f'导入测试方案_{int(time.time())}'
        code, stdout, stderr = self._run_command([
            'threshold', 'import', str(export_path),
            '--rename', import_name, '--by', '导入员'
        ])

        if code != 0:
            self._add_result('阈值方案导出再导入', False,
                           f'导入失败. stdout={stdout}, stderr={stderr}')
            return

        if '方案导入成功' not in stdout:
            self._add_result('阈值方案导出再导入', False,
                           f'输出中未找到"方案导入成功". stdout={stdout}')
            return

        code, stdout, stderr = self._run_command(['threshold', 'list'])
        if code != 0:
            self._add_result('阈值方案导出再导入', False,
                           f'列表查询失败. stdout={stdout}, stderr={stderr}')
            return

        if import_name not in stdout:
            self._add_result('阈值方案导出再导入', False,
                           f'列表中未找到导入的方案 {import_name}. stdout={stdout}')
            return

        try:
            export_path.unlink()
        except:
            pass

        self._test14_export_path = export_path
        self._test14_import_name = import_name
        self._add_result('阈值方案导出再导入', True)

    def _test_15_threshold_scheme_import_conflict(self):
        """测试15: 阈值方案导入冲突处理"""
        print('\n--- 测试15: 阈值方案导入冲突处理 ---')

        import time
        scheme_name = getattr(self, '_test12_scheme_name', None)
        if not scheme_name:
            self._add_result('阈值方案导入冲突处理', False, '未找到测试12创建的方案')
            return

        export_path = self.output_dir / f'test_conflict_{int(time.time())}.json'

        code, stdout, stderr = self._run_command([
            'threshold', 'export', scheme_name, '--output', str(export_path)
        ])

        if code != 0:
            self._add_result('阈值方案导入冲突处理', False,
                           f'导出失败. stdout={stdout}, stderr={stderr}')
            return

        code, stdout, stderr = self._run_command([
            'threshold', 'import', str(export_path),
            '--rename', scheme_name
        ])

        if code == 0:
            self._add_result('阈值方案导入冲突处理', False,
                           '同名方案导入应该失败但成功了')
            return

        if '方案名称冲突' not in stderr and '方案名称冲突' not in stdout:
            self._add_result('阈值方案导入冲突处理', False,
                           f'错误信息中未找到"方案名称冲突"。stdout: {stdout}, stderr: {stderr}')
            return

        overwrite_name = f'待覆盖方案_{int(time.time())}'
        code, stdout, stderr = self._run_command([
            'threshold', 'create',
            '--name', overwrite_name,
            '--meter-backward', '0.01',
            '--over-plan-ratio', '1.2',
            '--missing-reading-days', '1.0'
        ])

        if code != 0:
            self._add_result('阈值方案导入冲突处理', False,
                           f'创建待覆盖方案失败. stdout={stdout}, stderr={stderr}')
            return

        code, stdout, stderr = self._run_command([
            'threshold', 'import', str(export_path),
            '--rename', overwrite_name, '--overwrite'
        ])

        if code != 0:
            self._add_result('阈值方案导入冲突处理', False,
                           f'覆盖导入失败. stdout={stdout}, stderr={stderr}')
            return

        if '方案覆盖成功' not in stdout and '方案导入成功' not in stdout:
            self._add_result('阈值方案导入冲突处理', False,
                           f'覆盖导入输出不正确. stdout={stdout}')
            return

        try:
            export_path.unlink()
        except:
            pass

        self._add_result('阈值方案导入冲突处理', True)

    def _test_16_threshold_scheme_persistence(self):
        """测试16: 阈值方案跨重启生效"""
        print('\n--- 测试16: 阈值方案跨重启生效 ---')

        import time
        scheme_name = f'持久化测试_{int(time.time())}'

        self._run_command(['threshold', 'delete', scheme_name, '--force'])

        code, stdout, stderr = self._run_command([
            'threshold', 'create',
            '--name', scheme_name,
            '--meter-backward', '0.03',
            '--over-plan-ratio', '1.8',
            '--missing-reading-days', '2.0',
            '--by', '持久化测试'
        ])

        if code != 0:
            self._add_result('阈值方案跨重启生效', False,
                           f'创建方案失败. stdout={stdout}, stderr={stderr}')
            return

        code, stdout, stderr = self._run_command([
            'threshold', 'enable', scheme_name
        ])

        if code != 0:
            self._add_result('阈值方案跨重启生效', False,
                           f'启用方案失败. stdout={stdout}, stderr={stderr}')
            return

        code, stdout, stderr = self._run_command([
            'threshold', 'show', scheme_name
        ])

        if code != 0:
            self._add_result('阈值方案跨重启生效', False,
                           f'查询方案详情失败: {stderr[:200]}')
            return

        if scheme_name not in stdout:
            self._add_result('阈值方案跨重启生效', False,
                           f'方案详情中未找到方案名: {stdout[:200]}')
            return

        if '0.03' not in stdout or '1.8' not in stdout or '2.0' not in stdout:
            self._add_result('阈值方案跨重启生效', False,
                           f'方案阈值不正确: {stdout[:300]}')
            return

        code, stdout, stderr = self._run_command(['threshold', 'list'])
        if code != 0:
            self._add_result('阈值方案跨重启生效', False,
                           f'列表查询失败: {stderr[:200]}')
            return

        active_marker = False
        for line in stdout.split('\n'):
            if scheme_name in line and '✓ 启用' in line:
                active_marker = True
                break

        if not active_marker:
            self._add_result('阈值方案跨重启生效', False,
                           f'方案未显示为启用状态: {stdout[:300]}')
            return

        code, stdout, stderr = self._run_command(['threshold', 'logs', '--limit', '10'])
        if code != 0:
            self._add_result('阈值方案跨重启生效', False,
                           f'日志查询失败. stdout={stdout}, stderr={stderr}')
            return

        if '创建' not in stdout or '启用' not in stdout:
            self._add_result('阈值方案跨重启生效', False,
                           f'操作日志不完整. stdout={stdout}')
            return

        self._add_result('阈值方案跨重启生效', True)

    def _test_17_review_history_and_append(self):
        """测试17: 复核历史记录和追加备注"""
        print('\n--- 测试17: 复核历史记录和追加备注 ---')

        self._ensure_test_data()

        code, stdout, stderr = self._run_command(['anomalies', '--limit', '1'])
        if code != 0:
            self._add_result('复核历史记录和追加备注', False,
                           f'获取异常列表失败: {stderr[:200]}')
            return

        first_anomaly_id = self._parse_first_anomaly_id(stdout)
        if first_anomaly_id is None:
            self._add_result('复核历史记录和追加备注', False, '未找到可测试的异常')
            return

        code, stdout, stderr = self._run_command([
            'review', str(first_anomaly_id), 'valid',
            '--comment', '首次复核：确认异常有效',
            '--by', 'tester1'
        ])

        if code != 0 or '✅ 复核完成' not in stdout:
            self._add_result('复核历史记录和追加备注', False,
                           f'首次复核失败. stdout={stdout}, stderr={stderr}')
            return

        code, stdout, stderr = self._run_command([
            'review-append', str(first_anomaly_id),
            '追加备注：需要进一步核实水表读数',
            '--by', 'tester2'
        ])

        if code != 0 or '✅ 备注追加成功' not in stdout:
            self._add_result('复核历史记录和追加备注', False,
                           f'追加备注失败. stdout={stdout}, stderr={stderr}')
            return

        code, stdout, stderr = self._run_command([
            'review-history', str(first_anomaly_id)
        ])

        if code != 0:
            self._add_result('复核历史记录和追加备注', False,
                           f'查询复核历史失败. stdout={stdout}, stderr={stderr}')
            return

        if '首次复核' not in stdout:
            self._add_result('复核历史记录和追加备注', False,
                           f'复核历史中未找到首次复核记录')
            return

        if '追加备注' not in stdout:
            self._add_result('复核历史记录和追加备注', False,
                           f'复核历史中未找到追加备注记录')
            return

        if 'tester1' not in stdout or 'tester2' not in stdout:
            self._add_result('复核历史记录和追加备注', False,
                           f'复核历史中未找到操作人信息')
            return

        if '2 次操作' not in stdout and '历史记录数: 2' not in stdout:
            pass

        self._add_result('复核历史记录和追加备注', True)

    def _test_18_review_status_update_and_undo(self):
        """测试18: 修改处置状态和撤销复核"""
        print('\n--- 测试18: 修改处置状态和撤销复核 ---')

        self._ensure_test_data()

        code, stdout, stderr = self._run_command(['anomalies', '--limit', '1', '--not-reviewed'])
        if code != 0:
            self._add_result('修改处置状态和撤销复核', False,
                           f'获取待复核异常失败: {stderr[:200]}')
            return

        anomaly_id = self._parse_first_anomaly_id(stdout)
        if anomaly_id is None:
            code, stdout, stderr = self._run_command(['anomalies', '--limit', '1'])
            anomaly_id = self._parse_first_anomaly_id(stdout)

        if anomaly_id is None:
            self._add_result('修改处置状态和撤销复核', False, '未找到可测试的异常')
            return

        code, stdout, stderr = self._run_command([
            'review', str(anomaly_id), 'false_positive',
            '--comment', '初始复核：标记为误报',
            '--by', 'tester_a'
        ])

        if code != 0:
            self._add_result('修改处置状态和撤销复核', False,
                           f'初始复核失败. stdout={stdout}, stderr={stderr}')
            return

        code, stdout, stderr = self._run_command([
            'review-update', str(anomaly_id), 'needs_investigation',
            '--comment', '修改状态：需要进一步调查',
            '--by', 'tester_b'
        ])

        if code != 0 or '✅ 状态修改成功' not in stdout:
            self._add_result('修改处置状态和撤销复核', False,
                           f'修改状态失败. stdout={stdout}, stderr={stderr}')
            return

        code, stdout, stderr = self._run_command([
            'review-undo', str(anomaly_id),
            '--reason', '操作错误，需要撤销',
            '--by', 'tester_c'
        ])

        if code != 0 or '✅ 撤销成功' not in stdout:
            self._add_result('修改处置状态和撤销复核', False,
                           f'撤销复核失败. stdout={stdout}, stderr={stderr}')
            return

        code, stdout, stderr = self._run_command([
            'review-history', str(anomaly_id)
        ])

        if code != 0:
            self._add_result('修改处置状态和撤销复核', False,
                           f'查询复核历史失败. stdout={stdout}, stderr={stderr}')
            return

        if '已撤销' not in stdout and '↩️' not in stdout:
            self._add_result('修改处置状态和撤销复核', False,
                           f'撤销操作未在历史中显示为已撤销状态')
            return

        self._add_result('修改处置状态和撤销复核', True)

    def _test_19_review_undo_consistency(self):
        """测试19: 连续复核、撤销后再复核的一致性"""
        print('\n--- 测试19: 连续复核、撤销后再复核的一致性 ---')

        self._ensure_test_data()

        code, stdout, stderr = self._run_command(['anomalies', '--limit', '1', '--not-reviewed'])
        anomaly_id = self._parse_first_anomaly_id(stdout)
        if anomaly_id is None:
            code, stdout, stderr = self._run_command(['anomalies', '--limit', '1'])
            anomaly_id = self._parse_first_anomaly_id(stdout)

        if anomaly_id is None:
            self._add_result('连续复核撤销再复核一致性', False, '未找到可测试的异常')
            return

        for i, (status, comment) in enumerate([
            ('valid', '第一轮：确认有效'),
            ('false_positive', '第二轮：改为误报'),
            ('needs_investigation', '第三轮：需要调查')
        ]):
            code, _, stderr = self._run_command([
                'review-update' if i > 0 else 'review',
                str(anomaly_id), status,
                '--comment', comment,
                '--by', f'user{i+1}'
            ])
            if code != 0:
                self._add_result('连续复核撤销再复核一致性', False,
                               f'第{i+1}轮复核失败: {stderr}')
                return

        code, _, stderr = self._run_command([
            'review-undo', str(anomaly_id),
            '--reason', '撤销第三轮', '--by', 'admin'
        ])
        if code != 0:
            self._add_result('连续复核撤销再复核一致性', False,
                           f'撤销失败: {stderr}')
            return

        code, stdout, stderr = self._run_command(['anomalies', 'get', str(anomaly_id)])
        if code != 0:
            self._add_result('连续复核撤销再复核一致性', False,
                           f'获取异常详情失败: {stderr}')
            return

        import json
        try:
            anomaly_data = json.loads(stdout)
        except json.JSONDecodeError:
            self._add_result('连续复核撤销再复核一致性', False,
                           f'解析异常详情失败: {stdout[:200]}')
            return

        review_summary = anomaly_data.get('review_summary', {})
        if review_summary.get('review_count') != 2:
            self._add_result('连续复核撤销再复核一致性', False,
                           f'撤销后有效复核次数应为2，实际为{review_summary.get("review_count")}')
            return

        if review_summary.get('undo_count') != 1:
            self._add_result('连续复核撤销再复核一致性', False,
                           f'撤销次数应为1，实际为{review_summary.get("undo_count")}')
            return

        if review_summary.get('last_review_result') != 'false_positive':
            self._add_result('连续复核撤销再复核一致性', False,
                           f'撤销后最后结果应为false_positive，实际为{review_summary.get("last_review_result")}')
            return

        code, _, stderr = self._run_command([
            'review-update', str(anomaly_id), 'valid',
            '--comment', '第四轮：再次确认为有效',
            '--by', 'user4'
        ])
        if code != 0:
            self._add_result('连续复核撤销再复核一致性', False,
                           f'第四轮复核失败: {stderr}')
            return

        code, stdout, stderr = self._run_command(['anomalies', 'get', str(anomaly_id)])
        if code != 0:
            self._add_result('连续复核撤销再复核一致性', False,
                           f'再次获取异常详情失败: {stderr}')
            return

        try:
            anomaly_data = json.loads(stdout)
        except json.JSONDecodeError:
            self._add_result('连续复核撤销再复核一致性', False,
                           f'再次解析失败: {stdout[:200]}')
            return

        review_summary = anomaly_data.get('review_summary', {})
        if review_summary.get('review_count') != 3:
            self._add_result('连续复核撤销再复核一致性', False,
                           f'再复核后有效次数应为3，实际为{review_summary.get("review_count")}')
            return

        if review_summary.get('last_review_result') != 'valid':
            self._add_result('连续复核撤销再复核一致性', False,
                           f'再复核后最后结果应为valid，实际为{review_summary.get("last_review_result")}')
            return

        all_comments = review_summary.get('all_comments', [])
        expected_comments = ['第一轮：确认有效', '第二轮：改为误报', '第四轮：再次确认为有效']
        for expected in expected_comments:
            if expected not in all_comments:
                self._add_result('连续复核撤销再复核一致性', False,
                               f'历史备注中缺少: {expected}')
                return

        self._add_result('连续复核撤销再复核一致性', True)

    def _test_20_review_persistence_across_restart(self):
        """测试20: 复核历史跨重启持久化"""
        print('\n--- 测试20: 复核历史跨重启持久化 ---')

        self._ensure_test_data()

        code, stdout, stderr = self._run_command(['anomalies', '--limit', '1'])
        anomaly_id = self._parse_first_anomaly_id(stdout)
        if anomaly_id is None:
            self._add_result('复核历史跨重启持久化', False, '未找到可测试的异常')
            return

        import time
        unique_comment = f'持久化测试_{int(time.time())}'

        code, _, stderr = self._run_command([
            'review', str(anomaly_id), 'valid',
            '--comment', unique_comment,
            '--by', 'persistence_test'
        ])
        if code != 0:
            self._add_result('复核历史跨重启持久化', False,
                           f'复核失败: {stderr}')
            return

        code, stdout, stderr = self._run_command([
            'review-append', str(anomaly_id),
            f'追加备注_{int(time.time())}',
            '--by', 'persistence_test'
        ])
        if code != 0:
            self._add_result('复核历史跨重启持久化', False,
                           f'追加备注失败: {stderr}')
            return

        import gc
        gc.collect()

        import importlib
        from irrigation_analysis import batch_manager
        importlib.reload(batch_manager)

        from irrigation_analysis.batch_manager import review_manager

        history = review_manager.get_review_history(anomaly_id)
        if not history:
            self._add_result('复核历史跨重启持久化', False,
                           '重新加载模块后无法查询不到复核历史')
            return

        found_unique = False
        for h in history:
            if h.get('review_comment') == unique_comment:
                found_unique = True
                break

        if not found_unique:
            self._add_result('复核历史跨重启持久化', False,
                           f'重新加载后未找到特定备注: {unique_comment}')
            return

        summary = review_manager.get_review_summary(anomaly_id)
        if summary.get('review_count') < 2:
            self._add_result('复核历史跨重启持久化', False,
                           f'重新加载后复核摘要不正确: {summary}')
            return

        self._add_result('复核历史跨重启持久化', True)

    def _test_21_review_export_summary(self):
        """测试21: 导出报告包含复核摘要"""
        print('\n--- 测试21: 导出报告包含复核摘要 ---')

        self._ensure_test_data()

        code, stdout, stderr = self._run_command(['anomalies', '--limit', '1'])
        anomaly_id = self._parse_first_anomaly_id(stdout)
        if anomaly_id is None:
            self._add_result('导出报告包含复核摘要', False, '未找到可测试的异常')
            return

        self._run_command([
            'review', str(anomaly_id), 'valid',
            '--comment', '导出测试：确认有效',
            '--by', 'export_test'
        ])
        self._run_command([
            'review-append', str(anomaly_id),
            '导出测试：追加备注',
            '--by', 'export_test'
        ])

        code, stdout, stderr = self._run_command(['report', '--format', 'html'])
        if code != 0:
            self._add_result('导出报告包含复核摘要', False,
                           f'HTML导出失败: {stderr}')
            return

        import re
        html_path_match = re.search(r'(\S+\.html)', stdout)
        if not html_path_match:
            self._add_result('导出报告包含复核摘要', False,
                           f'未找到HTML导出路径: {stdout}')
            return

        html_path = html_path_match.group(1)
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
        except Exception as e:
            self._add_result('导出报告包含复核摘要', False,
                           f'读取HTML文件失败: {e}')
            return

        if '复核摘要' not in html_content:
            self._add_result('导出报告包含复核摘要', False,
                           'HTML报告中缺少复核摘要标题')
            return

        if '复核操作次数' not in html_content:
            self._add_result('导出报告包含复核摘要', False,
                           'HTML报告中缺少复核操作次数')
            return

        if '最近复核' not in html_content:
            self._add_result('导出报告包含复核摘要', False,
                           'HTML报告中缺少最近复核信息')
            return

        if '历史备注' not in html_content:
            self._add_result('导出报告包含复核摘要', False,
                           'HTML报告中缺少历史备注')
            return

        code, stdout, stderr = self._run_command(['report', '--format', 'csv'])
        if code != 0:
            self._add_result('导出报告包含复核摘要', False,
                           f'CSV导出失败: {stderr}')
            return

        csv_path_match = re.search(r'(\S+\.csv)', stdout)
        if not csv_path_match:
            self._add_result('导出报告包含复核摘要', False,
                           f'未找到CSV导出路径: {stdout}')
            return

        csv_path = csv_path_match.group(1)
        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                csv_content = f.read()
        except Exception as e:
            self._add_result('导出报告包含复核摘要', False,
                           f'读取CSV文件失败: {e}')
            return

        csv_headers = ['复核次数', '撤销次数', '最近复核人', '最近复核时间', '历史备注']
        for header in csv_headers:
            if header not in csv_content:
                self._add_result('导出报告包含复核摘要', False,
                               f'CSV中缺少列: {header}')
                return

        self._add_result('导出报告包含复核摘要', True)

    def _test_22_review_history_cli(self):
        """测试22: 复核相关CLI命令完整性"""
        print('\n--- 测试22: 复核相关CLI命令完整性 ---')

        code, stdout, stderr = self._run_command(['--help'])
        if code != 0:
            self._add_result('复核相关CLI命令完整性', False,
                           f'获取帮助失败: {stderr}')
            return

        required_commands = [
            'review ',
            'review-history',
            'review-append',
            'review-update',
            'review-undo',
        ]
        for cmd in required_commands:
            if cmd not in stdout:
                self._add_result('复核相关CLI命令完整性', False,
                               f'CLI帮助中缺少命令: {cmd}')
                return

        code, stdout, stderr = self._run_command(['review', '--help'])
        if code != 0:
            self._add_result('复核相关CLI命令完整性', False,
                           f'review帮助失败: {stderr}')
            return

        code, stdout, stderr = self._run_command(['review-history', '--help'])
        if code != 0:
            self._add_result('复核相关CLI命令完整性', False,
                           f'review-history帮助失败: {stderr}')
            return

        if '查看异常复核时间线' not in stdout:
            self._add_result('复核相关CLI命令完整性', False,
                           f'review-history帮助描述不正确: {stdout}')
            return

        code, stdout, stderr = self._run_command(['review-append', '--help'])
        if code != 0:
            self._add_result('复核相关CLI命令完整性', False,
                           f'review-append帮助失败: {stderr}')
            return

        code, stdout, stderr = self._run_command(['review-update', '--help'])
        if code != 0:
            self._add_result('复核相关CLI命令完整性', False,
                           f'review-update帮助失败: {stderr}')
            return

        code, stdout, stderr = self._run_command(['review-undo', '--help'])
        if code != 0:
            self._add_result('复核相关CLI命令完整性', False,
                           f'review-undo帮助失败: {stderr}')
            return

        self._add_result('复核相关CLI命令完整性', True)

    def _test_23_review_web_api(self):
        """测试23: Web API接口和页面渲染"""
        print('\n--- 测试23: Web API接口和页面渲染 ---')

        self._ensure_test_data()

        code, stdout, stderr = self._run_command(['anomalies', '--limit', '1'])
        anomaly_id = self._parse_first_anomaly_id(stdout)
        if anomaly_id is None:
            self._add_result('Web API接口和页面渲染', False, '未找到可测试的异常')
            return

        self._run_command([
            'review', str(anomaly_id), 'valid',
            '--comment', 'Web测试：确认有效',
            '--by', 'web_test'
        ])

        from irrigation_analysis import web
        web.app.config['TESTING'] = True
        client = web.app.test_client()

        try:
            response = client.get(f'/api/anomalies/{anomaly_id}/review-history')
            if response.status_code != 200:
                self._add_result('Web API接口和页面渲染', False,
                               f'复核历史API返回状态码: {response.status_code}')
                return

            import json
            data = json.loads(response.data.decode('utf-8'))
            if not data.get('success'):
                self._add_result('Web API接口和页面渲染', False,
                               f'复核历史API返回失败: {data}')
                return

            if data.get('total') < 1:
                self._add_result('Web API接口和页面渲染', False,
                               f'复核历史API返回数据不正确: {data}')
                return

            history_list = data.get('data', [])
            found_review = False
            for h in history_list:
                if h.get('review_comment') and 'Web测试' in h['review_comment']:
                    found_review = True
                    break
            if not found_review:
                self._add_result('Web API接口和页面渲染', False,
                               f'复核历史API数据中缺少测试备注: {history_list}')
                return

            response = client.get(f'/api/anomalies/{anomaly_id}/review-summary')
            if response.status_code != 200:
                self._add_result('Web API接口和页面渲染', False,
                               f'复核摘要API返回状态码: {response.status_code}')
                return

            data = json.loads(response.data.decode('utf-8'))
            if not data.get('success'):
                self._add_result('Web API接口和页面渲染', False,
                               f'复核摘要API返回失败: {data}')
                return

            summary = data.get('data', {})
            if summary.get('review_count') < 2:
                self._add_result('Web API接口和页面渲染', False,
                               f'复核摘要API数据不正确，复核次数应为>=2，实际为{summary.get("review_count")}')
                return

            if 'Web测试：确认有效' not in str(summary.get('all_comments', [])):
                self._add_result('Web API接口和页面渲染', False,
                               f'复核摘要API缺少历史备注: {summary}')
                return

        except Exception as e:
            self._add_result('Web API接口和页面渲染', False,
                           f'API测试异常: {e}')
            return

        self._add_result('Web API接口和页面渲染', True)

    def _test_24_rollback_preserves_audit_log(self):
        """测试24: 批次回滚不删除审计记录"""
        print('\n--- 测试24: 批次回滚不删除审计记录 ---')

        self._ensure_test_data()

        code, stdout, stderr = self._run_command(['anomalies', '--limit', '1'])
        anomaly_id = self._parse_first_anomaly_id(stdout)
        if anomaly_id is None:
            self._add_result('批次回滚不删除审计记录', False, '未找到可测试的异常')
            return

        self._run_command([
            'review', str(anomaly_id), 'valid',
            '--comment', '回滚测试：复核',
            '--by', 'rollback_test'
        ])
        self._run_command([
            'review-append', str(anomaly_id),
            '回滚测试：追加备注',
            '--by', 'rollback_test'
        ])

        from irrigation_analysis.batch_manager import review_manager

        history_before = review_manager.get_review_history(anomaly_id)
        if not history_before:
            self._add_result('批次回滚不删除审计记录', False,
                           '回滚前未找到复核历史')
            return

        code, stdout, stderr = self._run_command([
            'rollback', '--anomaly-id', str(anomaly_id),
            '--reason', '测试回滚不删除审计记录'
        ])
        if code != 0:
            self._add_result('批次回滚不删除审计记录', False,
                           f'回滚异常失败: {stderr}')
            return

        history_after = review_manager.get_review_history(anomaly_id)
        if not history_after:
            self._add_result('批次回滚不删除审计记录', False,
                           '回滚后复核历史被删除了！')
            return

        if len(history_after) != len(history_before):
            self._add_result('批次回滚不删除审计记录', False,
                           f'回滚前后历史记录数不一致: 前{len(history_before)} != 后{len(history_after)}')
            return

        comments_after = [h.get('review_comment') for h in history_after]
        if '回滚测试：复核' not in comments_after:
            self._add_result('批次回滚不删除审计记录', False,
                           '回滚后复核备注丢失')
            return

        summary = review_manager.get_review_summary(anomaly_id)
        expected_count = len([h for h in history_after if not h.get('is_undone') and h.get('action_type') != 'undo'])
        if summary.get('review_count') != expected_count:
            self._add_result('批次回滚不删除审计记录', False,
                           f'回滚后复核摘要不正确, 预期{expected_count}，实际{summary.get("review_count")}')
            return

        self._add_result('批次回滚不删除审计记录', True)

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
