#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""禅道报告中心 - 本地服务器
提供静态文件服务 + /api/refresh 接口触发报告生成
用法：python server.py
访问：http://localhost:8000
"""

import os
import subprocess
import threading
import time
import json

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 任务状态存储 {task_id: {status, logs, progress}}
tasks = {}
lock = threading.Lock()


def run_scripts(task_id):
    """后台运行报告生成脚本，实时捕获输出"""
    try:
        script = os.path.join(BASE_DIR, 'generate_all.py')
        proc = subprocess.Popen(
            ['python', script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=BASE_DIR,
            encoding='utf-8',
            errors='replace'
        )
        # 实时读取输出，估算进度
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line.strip():
                with lock:
                    tasks[task_id]['logs'].append(line.strip())
                    # 根据输出关键词估算进度
                    l = line.strip()
                    if '连接' in l or 'API' in l:
                        tasks[task_id]['progress'] = 10
                    elif '获取' in l or '迭代' in l:
                        tasks[task_id]['progress'] = 30
                    elif '生成' in l or '报告' in l:
                        tasks[task_id]['progress'] = 60
                    elif '完成' in l or 'Done' in l:
                        tasks[task_id]['progress'] = 100
        proc.wait()
        with lock:
            tasks[task_id]['status'] = 'done'
            tasks[task_id]['progress'] = 100
    except Exception as e:
        with lock:
            tasks[task_id]['status'] = 'error'
            tasks[task_id]['logs'].append(f'错误: {e}')


@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    # 禁止访问敏感文件
    if filename.endswith('.json') and 'config' in filename.lower():
        return jsonify({'error': 'forbidden'}), 403
    return send_from_directory(BASE_DIR, filename)


@app.route('/api/refresh', methods=['POST'])
def refresh():
    """触发报告生成，返回 task_id"""
    task_id = str(int(time.time() * 1000))
    with lock:
        tasks[task_id] = {'status': 'running', 'logs': [], 'progress': 0}
    t = threading.Thread(target=run_scripts, args=(task_id,), daemon=True)
    t.start()
    return jsonify({'task_id': task_id})


@app.route('/api/refresh/<task_id>/stream')
def stream(task_id):
    """SSE 流式返回生成进度"""
    def generate():
        last = 0
        while True:
            with lock:
                if task_id not in tasks:
                    yield f"data: {json.dumps({'error': '任务不存在'})}\n\n"
                    break
                task = tasks[task_id]
                new_logs = task['logs'][last:]
                last = len(task['logs'])
            for log in new_logs:
                # 过滤敏感信息（账号密码等）
                safe_log = log
                yield f"data: {json.dumps({'log': safe_log, 'progress': task['progress']}, ensure_ascii=False)}\n\n"
            with lock:
                if task['status'] in ('done', 'error'):
                    yield f"data: {json.dumps({'status': task['status'], 'progress': 100}, ensure_ascii=False)}\n\n"
                    break
            time.sleep(0.3)

    return Response(generate(), mimetype='text/event-stream',
                   headers={
                       'Cache-Control': 'no-cache',
                       'X-Accel-Buffering': 'no',
                       'Connection': 'keep-alive'
                   })


@app.route('/api/refresh/<task_id>')
def get_status(task_id):
    """获取任务状态（备用，非 SSE 方式）"""
    with lock:
        if task_id not in tasks:
            return jsonify({'error': '任务不存在'}), 404
        return jsonify(tasks[task_id])


if __name__ == '__main__':
    print('\n' + '=' * 50)
    print('  禅道报告中心 - 本地服务器')
    print('  访问地址：http://localhost:8000')
    print('  Ctrl+C 停止服务')
    print('=' * 50 + '\n')
    app.run(host='0.0.0.0', port=8000, debug=False)
