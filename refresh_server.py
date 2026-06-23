#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报告刷新服务 - 供HTML页面调用，触发重新生成报告
用法：python refresh_server.py  （保持运行）
      或后台运行：pythonw refresh_server.py
"""
import http.server, json, subprocess, threading, os, sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

SCRIPT_DIR = Path(__file__).parent
PORT = 8899
REPORT_SCRIPTS = [
    "generate_index.py",
    "generate_iteration_reports.py",
    "generate_efficiency_report.py",
]

def run_scripts():
    """在后台线程中运行所有报告生成脚本"""
    results = {}
    for script in REPORT_SCRIPTS:
        script_path = SCRIPT_DIR / script
        if not script_path.exists():
            results[script] = {"ok": False, "msg": "文件不存在"}
            continue
        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=str(SCRIPT_DIR),
                capture_output=True, text=True, timeout=300
            )
            results[script] = {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-500:] if proc.stdout else "",
                "stderr": proc.stderr[-300:] if proc.stderr else "",
            }
        except subprocess.TimeoutExpired:
            results[script] = {"ok": False, "msg": "超时（>300s）"}
        except Exception as e:
            results[script] = {"ok": False, "msg": str(e)}
    return results


class RefreshHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{self.date_time_string()}] {args[0] if args else ''}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/refresh" or path == "/api/refresh":
            # 触发刷新
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            # 在后台线程运行，立即返回
            threading.Thread(target=run_scripts, daemon=True).start()
            self.wfile.write(json.dumps({"ok": True, "msg": "刷新任务已启动，请稍候..."}).encode())
            return

        elif path == "/status" or path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            # 简单返回报告文件时间
            info = {}
            for script in REPORT_SCRIPTS:
                sp = SCRIPT_DIR / script
                info[script] = {"exists": sp.exists()}
            self.wfile.write(json.dumps(info).encode())
            return

        elif path == "/health" or path == "/ping":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        return self.do_GET()


def main():
    server = http.server.HTTPServer(("127.0.0.1", PORT), RefreshHandler)
    print("=" * 50)
    print(f"报告刷新服务已启动")
    print(f"  地址: http://127.0.0.1:{PORT}")
    print(f"  触发: 点击报告页面中的「实时刷新」按钮")
    print(f"  手动: 浏览器访问 http://127.0.0.1:{PORT}/refresh")
    print(f"  停止: Ctrl+C")
    print("=" * 50)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")


if __name__ == "__main__":
    main()
