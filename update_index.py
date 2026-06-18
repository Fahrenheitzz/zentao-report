import re

filepath = r'D:\workbuddy\PM work\zentao-report\index.html'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 修改「查看报告」按钮的链接
# 将 href="'+TODAY+'/未完成测试任务_详细任务.html?project='+e.project_id+'"
# 改为 href="'+TODAY+'/迭代'+e.id+'_执行进展报告.html"'
old_report_link = r'''href="'+TODAY+'/未完成测试任务_详细任务.html?project='+e.project_id+'"'''
new_report_link = r'''href="'+TODAY+'/迭代'+e.id+'_执行进展报告.html"'''

if old_report_link in content:
    content = content.replace(old_report_link, new_report_link)
    print('✅ 已修改「查看报告」按钮链接')
else:
    print('⚠️ 未找到旧的「查看报告」按钮链接，尝试其他方式...')
    # 尝试找到包含「查看报告」的行
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if '查看报告' in line and 'ov-vl' in line:
            print(f'  找到在 line {i+1}: {line.strip()[:100]}...')
            # 替换这一行
            lines[i] = line.replace(
                r'''href="'+TODAY+'/未完成测试任务_详细任务.html?project='+e.project_id+'"''',
                r'''href="'+TODAY+'/迭代'+e.id+'_执行进展报告.html"'''
            )
    content = '\n'.join(lines)

# 2. 在「更新时间」后面添加「实时更新」按钮
# 找到 <div class="dt">...</div> 这一行，在它后面添加按钮
old_dt = r'''    <div class="dt"><span>2026-06-17 更新</span></div>'''
new_dt = r'''    <div class="dt"><span id="updateTime">2026-06-17 更新</span> <button class="refresh-btn" onclick="location.reload()">🔄 实时更新</button></div>'''

if old_dt in content:
    content = content.replace(old_dt, new_dt)
    print('✅ 已添加「实时更新」按钮（刷新页面）')
else:
    print('⚠️ 未找到「更新时间」行，尝试其他方式...')
    # 尝试找到包含「更新」的行
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if '更新' in line and 'class="dt"' in line:
            print(f'  找到在 line {i+1}: {line.strip()[:100]}...')
            # 替换这一行
            lines[i] = line.replace(
                r'''<div class="dt"><span>''',
                r'''<div class="dt"><span id="updateTime">'''
            ).replace(
                r'''</span></div>''',
                r'''</span> <button class="refresh-btn" onclick="location.reload()">🔄 实时更新</button></div>'''
            )
    content = '\n'.join(lines)

# 3. 添加 .refresh-btn 样式（在 <style> 标签内）
# 找到 </style> 标签，在它前面添加样式
refresh_btn_css = '''
.refresh-btn{padding:4px 14px;border-radius:12px;font-size:11px;font-weight:600;border:1px solid rgba(124,92,252,0.3);background:rgba(124,92,252,0.12);color:#a78bfa;cursor:pointer;transition:all .3s;margin-left:8px}
.refresh-btn:hover{background:rgba(124,92,252,0.25);color:#fff}
'''
if '.refresh-btn{' not in content:
    content = content.replace('</style>', refresh_btn_css + '</style>')
    print('✅ 已添加 .refresh-btn 样式')
else:
    print('⚠️ .refresh-btn 样式已存在')

# 保存修改
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print('\n✅ 修改完成！')
print('   文件:', filepath)
