#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试脚本 - 简化版效率报告"""
import sys
print("开始执行...", flush=True)

try:
    from generate_iteration_reports import ZentaoClient
    print("导入ZentaoClient成功", flush=True)
    
    CONFIG_FILE = 'zentao_config.json'
    print(f"正在连接禅道...", flush=True)
    
    client = ZentaoClient(CONFIG_FILE)
    print("连接成功!", flush=True)
    
    # 简单测试API调用
    print("测试API调用...", flush=True)
    result = client.get('/projects/1013/executions', {'limit': 10})
    print(f"API返回: {type(result)}", flush=True)
    
    if isinstance(result, dict):
        executions = result.get('executions', [])
        print(f"获取到 {len(executions)} 个迭代", flush=True)
    
    print("测试完成!", flush=True)
    
except Exception as e:
    print(f"错误: {e}", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)
