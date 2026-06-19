#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
团队产出效率分析 - 按月生成
从禅道拉取指定月份的任务/Bug数据，按角色分组统计个人效率指标，
生成独立的 HTML 报告。

用法：
  python generate_efficiency_report.py 202606        # 生成2026年6月
  python generate_efficiency_report.py                  # 默认上月
"""
import sys
print("脚本开始执行...", file=sys.stderr)
import json, ssl, urllib.request, urllib.parse, hashlib, datetime, calendar
from pathlib import Path
print("导入完成...", file=sys.stderr)

# ── 路径 ────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / 'zentao_config.json'
OUTPUT_DIR  = SCRIPT_DIR / 'efficiency'

# ── 角色关键词映射（按任务标题/名称判断角色）────────────────────────────
ROLE_KEYWORDS = {
    '产品':   ['产品', '需求', '原型', 'PRD', '调研', '设计'],
    '后端开发': ['后端', '接口', 'API', '数据库', '服务端', 'Java', 'Python', 'Go'],
    '前端开发': ['前端', '页面', 'H5', 'Web', 'Vue', 'React', 'CSS', 'JS'],
    '移动端开发': ['移动端', 'APP', 'iOS', 'Android', '小程序', 'Flutter'],
    '测试':     ['测试', '用例', '压测', '自动化'],
}
# ── 项目配置 ──────────────────────────────────────────────────────────────
# 要统计的项目ID列表（可从禅道获取，或手动指定）
PROJECT_IDS = [1013]  # 商城3.0
# 账号 → 角色（优先级高于关键词判断）
ACCOUNT_ROLE = {}

# ── 效率分级阈值 ───────────────────────────────────────────────────────────
EFFICIENCY_THRESHOL = {'高效': 60, '迟缓': 35}   # 完成率 >=60% 高效，<35% 迟缓，其余正常

# ════════════════════════════════════════════════════════════════════════
#  禅道 API 客户端（复用 generate_iteration_reports.py 的逻辑）
# ════════════════════════════════════════════════════════════════════════

from generate_iteration_reports import ZentaoClient
# ════════════════════════════════════════════════════════════════════════
#  数据拉取：指定月份的所有任务 / Bug
# ════════════════════════════════════════════════════════════════════════

def fetch_month_tasks(client, year, month):
    """拉取指定年月的全部任务（通过项目迭代）"""
    # 计算月份起止日期
    start = f'{year}-{month:02d}-01'
    last_day = calendar.monthrange(year, month)[1]
    end   = f'{year}-{month:02d}-{last_day:02d}'
    print(f'  任务时间范围: {start} ~ {end}')

    month_tasks = []
    
    # 遍历所有配置的项目
    for project_id in PROJECT_IDS:
        print(f'  正在获取项目 {project_id} 的迭代...')
        # 获取项目的所有迭代
        executions_res = client.get(f'/projects/{project_id}/executions', {'limit': 100})
        executions = executions_res.get('executions', []) if isinstance(executions_res, dict) else []
        
        for exc in executions:
            exc_id = exc.get('id')
            # 检查迭代是否在目标月份内
            exc_start = (exc.get('begin', '') or '')[:7]
            exc_end   = (exc.get('end', '') or '')[:7]
            if exc_start <= f'{year}-{month:02d}' <= exc_end:
                # 获取该迭代的任务
                page = 1
                while True:
                    res = client.get(f'/executions/{exc_id}/tasks', {'page': page, 'limit': 100})
                    tasks = res.get('tasks', []) if isinstance(res, dict) else []
                    if not tasks:
                        break
                    for t in tasks:
                        # 检查任务是否属于该月
                        finished = (t.get('finishedDate', '') or '')[:7]
                        deadline = (t.get('deadline', '') or '')[:7]
                        opened   = (t.get('openedDate', '') or '')[:7]
                        if f'{year}-{month:02d}' in (finished, deadline, opened):
                            month_tasks.append(t)
                    page += 1
    
    print(f'  属于 {year}-{month:02d} 的任务: {len(month_tasks)} 条')
    return month_tasks


def fetch_month_bugs(client, year, month):
    """拉取指定年月的全部 Bug（通过项目迭代）"""
    month_bugs = []
    
    # 遍历所有配置的项目
    for project_id in PROJECT_IDS:
        # 获取项目的所有迭代
        executions_res = client.get(f'/projects/{project_id}/executions', {'limit': 100})
        executions = executions_res.get('executions', []) if isinstance(executions_res, dict) else []
        
        for exc in executions:
            exc_id = exc.get('id')
            # 检查迭代是否在目标月份内
            exc_start = (exc.get('begin', '') or '')[:7]
            exc_end   = (exc.get('end', '') or '')[:7]
            if exc_start <= f'{year}-{month:02d}' <= exc_end:
                # 获取该迭代的Bug
                bugs_res = client.get(f'/executions/{exc_id}/bugs', {'limit': 1000})
                bugs = bugs_res.get('bugs', []) if isinstance(bugs_res, dict) else []
                
                for b in bugs:
                    # 检查Bug是否属于该月
                    resolved = (b.get('resolvedDate', '') or '')[:7]
                    opened   = (b.get('openedDate', '') or '')[:7]
                    if f'{year}-{month:02d}' in (resolved, opened):
                        month_bugs.append(b)
    
    print(f'  属于 {year}-{month:02d} 的 Bug: {len(month_bugs)} 条')
    return month_bugs


# ════════════════════════════════════════════════════════════════════════
#  角色判断
# ════════════════════════════════════════════════════════════════════════

def detect_role(task_name, account):
    """根据任务名称和账号判断角色"""
    if account in ACCOUNT_ROLE:
        return ACCOUNT_ROLE[account]
    name = task_name or ''
    for role, kws in ROLE_KEYWORDS.items():
        for kw in kws:
            if kw in name:
                return role
    return '后端开发'   # 默认


def get_real_name(task, field='openedBy'):
    """从任务的 openedBy/assignedTo 等字段提取真实姓名"""
    val = task.get(field, '') or ''
    # 可能是 dict（如 {'account':'A80369','realname':'朱姣红'}）
    if isinstance(val, dict):
        return val.get('realname', '') or val.get('account', '')
    return val


# ════════════════════════════════════════════════════════════════════════
#  效率计算
# ════════════════════════════════════════════════════════════════════════

def calc_efficiency(tasks):
    """
    输入某人所属的任务列表，返回效率指标字典。
    完成率 = 已完成消耗 / (已完成消耗 + 未完成预估)
    """
    done_tasks = [t for t in tasks if (t.get('status') or '') == 'done']
    open_tasks = [t for t in tasks if (t.get('status') or '') in ('wait', 'doing')]

    done_consumed = sum(float(t.get('consumed', 0) or 0) for t in done_tasks)
    open_estimate = sum(float(t.get('estimate', 0) or 0) for t in open_tasks)

    total_hours = done_consumed + open_estimate
    rate = round(done_consumed / total_hours * 100, 1) if total_hours > 0 else 0

    if rate >= EFFICIENCY_THRESHOL['高效']:
        level = '高效'
    elif rate < EFFICIENCY_THRESHOL['迟缓']:
        level = '迟缓'
    else:
        level = '正常'

    return {
        'done_count':    len(done_tasks),
        'open_count':    len(open_tasks),
        'done_consumed': round(done_consumed, 1),
        'open_estimate': round(open_estimate, 1),
        'total_hours':   round(total_hours, 1),
        'rate':           rate,
        'level':          level,
        'done_tasks':    done_tasks,
        'open_tasks':    open_tasks,
    }


# ════════════════════════════════════════════════════════════════════════
#  HTML 生成
# ════════════════════════════════════════════════════════════════════════

CSS_STYLE = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    background: #f1f5f9; color: #1e293b; padding: 20px; }
h1 { text-align:center; font-size:26px; font-weight:800; margin-bottom:6px;
    background:linear-gradient(135deg,#2563eb,#7c5cfc); -webkit-background-clip:text;
    -webkit-text-fill-color:transparent; background-clip:text; }
.sub { text-align:center; color:#64748b; font-size:13px; margin-bottom:24px; }
.back-link { display:block; text-align:center; margin-bottom:18px; }
.back-link a { color:#2563eb; text-decoration:none; font-size:13px; }
.back-link a:hover { text-decoration:underline; }
/* 总览卡片 */
.overview { display:flex; gap:16px; justify-content:center; flex-wrap:wrap; margin-bottom:28px; }
.ov-card { background:#fff; border-radius:14px; padding:20px 28px; min-width:180px;
    box-shadow:0 2px 8px rgba(0,0,0,.06); text-align:center; }
.ov-val { font-size:32px; font-weight:900; }
.ov-lbl { font-size:12px; color:#64748b; margin-top:4px; }
/* 角色区块 */
.role-section { background:#fff; border-radius:14px; margin-bottom:22px;
    box-shadow:0 2px 8px rgba(0,0,0,.06); overflow:hidden; }
.role-header { padding:16px 24px; font-size:16px; font-weight:700; cursor:pointer;
    border-bottom:1px solid #e2e8f0; display:flex; align-items:center; gap:10px;
    user-select:none; transition:background .15s; }
.role-header:hover { background:#f8fafc; }
.role-arrow { transition:transform .25s; display:inline-block; font-size:12px; color:#9ca3af; }
.role-arrow.expanded { transform:rotate(90deg); }
.role-summary { margin-left:auto; font-size:12px; color:#64748b; font-weight:400; }
.role-body { padding:12px 16px 20px; }
/* 个人行 */
.person-row { border:1px solid #e2e8f0; border-radius:10px; margin-bottom:10px; overflow:hidden; }
.person-header { display:flex; align-items:center; padding:12px 16px; cursor:pointer;
    background:#f8fafc; transition:background .15s; gap:12px; }
.person-header:hover { background:#f1f5f9; }
.person-arrow { font-size:11px; color:#9ca3af; transition:transform .25s; }
.person-arrow.expanded { transform:rotate(90deg); }
.person-name { font-weight:700; font-size:14px; }
.person-stats { margin-left:auto; display:flex; gap:14px; font-size:12px; color:#475569; }
.pstat { display:flex; align-items:center; gap:3px; }
.pstat-val { font-weight:700; font-size:13px; }
.level-高效 { color:#16a34a; background:#dcfce7; padding:2px 8px; border-radius:4px; font-size:11px; }
.level-正常 { color:#2563eb; background:#dbeafe; padding:2px 8px; border-radius:4px; font-size:11px; }
.level-迟缓 { color:#dc2626; background:#fee2e2; padding:2px 8px; border-radius:4px; font-size:11px; }
/* 任务表格 */
.person-tasks { display:none; padding:8px 16px 14px; }
.person-tasks.expanded { display:block; }
.task-table { width:100%; border-collapse:collapse; font-size:12px; }
.task-table th { background:#f1f5f9; color:#475569; padding:7px 10px; text-align:left;
    font-weight:600; font-size:11px; border-bottom:2px solid #e2e8f0; }
.task-table td { padding:7px 10px; border-bottom:1px solid #f1f5f9; }
.task-table tr:hover td { background:#f8fafc; }
.status-done { color:#22c55e; font-weight:600; }
.status-doing { color:#f59e0b; font-weight:600; }
.status-wait { color:#6b7280; font-weight:600; }
"""

JS_SCRIPT = """
function toggleRole(id){
    var body = document.getElementById('role-'+id);
    var arrow = document.getElementById('role-arrow-'+id);
    if(!body || !arrow) return;
    var exp = body.classList.contains('expanded');
    if(exp){ body.classList.remove('expanded'); arrow.classList.remove('expanded'); }
    else { body.classList.add('expanded'); arrow.classList.add('expanded'); }
}
function togglePerson(id){
    var tasks = document.getElementById('pt-'+id);
    var arrow = document.getElementById('pa-'+id);
    if(!tasks || !arrow) return;
    var exp = tasks.classList.contains('expanded');
    if(exp){ tasks.classList.remove('expanded'); arrow.classList.remove('expanded'); }
    else { tasks.classList.add('expanded'); arrow.classList.add('expanded'); }
}
"""


def make_task_rows(tasks, kind='done'):    # kind: 'done' | 'open'
    rows = ''
    for t in tasks:
        tid   = t.get('id', '')
        title = t.get('name', '') or ''
        status= t.get('status', '')
        slabel = {'done':'已完成','doing':'进行中','wait':'未开始'}.get(status, status)
        sclas = {'done':'status-done','doing':'status-doing','wait':'status-wait'}.get(status, '')
        consumed = t.get('consumed', 0) or 0
        estimate = t.get('estimate', 0) or 0
        deadline = t.get('deadline', '') or '-'
        rows += '<tr>'
        rows += '<td>%s</td>' % tid
        rows += '<td style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="%s">%s</td>' % (title, title)
        rows += '<td class="%s">%s</td>' % (sclas, slabel)
        rows += '<td>%s</td>' % consumed
        rows += '<td>%s</td>' % estimate
        rows += '<td>%s</td>' % deadline
        rows += '</tr>'
    if not rows:
        rows = '<tr><td colspan="6" style="color:#9ca3af;text-align:center;padding:16px">暂无数据</td></tr>'
    return rows


def make_html(year, month, role_data):
    """
    role_data: { '产品': [{'name','stats',...}, ...], ... }
    """
    month_label = '%s年%s月' % (year, month)
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    # 总览统计
    total_people = sum(len(v) for v in role_data.values())
    total_done    = sum(sum(p['stats']['done_count']    for p in v) for v in role_data.values())
    total_open    = sum(sum(p['stats']['open_count']    for p in v) for v in role_data.values())
    total_hours   = sum(sum(p['stats']['total_hours']   for p in v) for v in role_data.values())
    level_cnt = {'高效':0,'正常':0,'迟缓':0}
    for v in role_data.values():
        for p in v:
            level_cnt[p['stats']['level']] += 1

    parts = []
    parts.append('<!DOCTYPE html><html lang="zh-CN"><head>')
    parts.append('<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">')
    parts.append('<title>团队产出效率 - %s</title>' % month_label)
    parts.append('<style>%s</style>' % CSS_STYLE)
    parts.append('<script>%s</script>' % JS_SCRIPT)
    parts.append('</head><body>')

    parts.append('<h1>🚀 团队产出效率</h1>')
    parts.append('<p class="sub">%s · 统计生成时间：%s · <a href="../index.html">← 返回首页</a></p>' % (month_label, now_str))

    # 总览卡片
    parts.append('<div class="overview">')
    cards = [
        ('总人数', total_people, '#7c5cfc'),
        ('总完成任务', total_done, '#22c55e'),
        ('进行中任务', total_open, '#f59e0b'),
        ('总工时(h)', total_hours, '#2563eb'),
    ]
    for lbl, val, clr in cards:
        parts.append('<div class="ov-card">'
            '<div class="ov-val" style="color:%s">%s</div>' % (clr, val) +
            '<div class="ov-lbl">%s</div></div>' % lbl)
    parts.append('</div>')

    # 各角色区块
    role_idx = 0
    for role, people in role_data.items():
        role_done  = sum(p['stats']['done_count']    for p in people)
        role_hours = sum(p['stats']['total_hours']   for p in people)
        role_summary = '共 %d 人 · 完成任务 %d · 总工时 %.1fh' % (len(people), role_done, role_hours)
        role_id = 'role-%d' % role_idx

        parts.append('<div class="role-section">')
        parts.append('<div class="role-header" onclick="toggleRole(%d)">' % role_idx)
        parts.append('<span class="role-arrow" id="role-arrow-%d">&#9654;</span>' % role_idx)
        parts.append('<span>%s</span>' % role)
        parts.append('<span class="role-summary">%s</span>' % role_summary)
        parts.append('</div>')
        parts.append('<div class="role-body" id="%s">' % role_id)

        for pi, person in enumerate(people):
            nm    = person['name']
            s     = person['stats']
            pid   = 'role%d-p%d' % (role_idx, pi)
            pcls  = 'level-' + s['level']

            parts.append('<div class="person-row">')
            parts.append("<div class=\"person-header\" onclick=\"togglePerson('%s')\">" % pid)
            parts.append('<span class="person-arrow" id="pa-%s">&#9654;</span>' % pid)
            parts.append('<span class="person-name">%s</span>' % nm)
            parts.append('<div class="person-stats">')
            parts.append('<span class="pstat">完成率 <span class="pstat-val">%s%%</span></span>' % s['rate'])
            parts.append('<span class="pstat">总工时 <span class="pstat-val">%sh</span></span>' % s['total_hours'])
            parts.append('<span class="pstat">已完成 <span class="pstat-val">%s</span></span>' % s['done_count'])
            parts.append('<span class="pstat">进行中 <span class="pstat-val">%s</span></span>' % s['open_count'])
            parts.append('<span class="%s">%s</span>' % (pcls, s['level']))
            parts.append('</div></div>')   # close person-stats + person-header

            # 任务明细（默认收起）
            parts.append('<div class="person-tasks" id="pt-%s">' % pid)
            # 已完成任务
            parts.append('<div style="font-size:12px;font-weight:600;color:#22c55e;margin:8px 0 4px;">✅ 已完成任务</div>')
            parts.append('<table class="task-table"><thead><tr>'
                '<th>ID</th><th>任务名称</th><th>状态</th><th>消耗(h)</th><th>预估(h)</th><th>截止日期</th>'
                '</tr></thead><tbody>%s</tbody></table>' % make_task_rows(s['done_tasks'], 'done'))
            # 进行中任务
            parts.append('<div style="font-size:12px;font-weight:600;color:#f59e0b;margin:12px 0 4px;">🔄 进行中任务</div>')
            parts.append('<table class="task-table"><thead><tr>'
                '<th>ID</th><th>任务名称</th><th>状态</th><th>消耗(h)</th><th>预估(h)</th><th>截止日期</th>'
                '</tr></thead><tbody>%s</tbody></table>' % make_task_rows(s['open_tasks'], 'open'))
            parts.append('</div>')   # close person-tasks
            parts.append('</div>')   # close person-row

        parts.append('</div></div>')   # close role-body + role-section
        role_idx += 1

    parts.append('</body></html>')
    return '\n'.join(parts)


# ════════════════════════════════════════════════════════════════════════
#  main
# ════════════════════════════════════════════════════════════════════════

def main():
    import traceback
    try:
        # 解析月份参数
        if len(sys.argv) >= 2:
            arg = sys.argv[1]
            year  = int(arg[:4])
            month = int(arg[4:6])
        else:
            today = datetime.date.today()
            if today.month == 1:
                year, month = today.year - 1, 12
            else:
                year, month = today.year, today.month - 1
        month_str = '%s%02d' % (year, month)
        print('=' * 50)
        print('团队产出效率分析')
        print('  月份: %s年%s月' % (year, month))
        print('=' * 50)

        client = ZentaoClient(str(CONFIG_FILE))
        print('已连接禅道 API')

        # 拉取数据
        tasks = fetch_month_tasks(client, year, month)
        bugs  = fetch_month_bugs(client, year, month)

        # 按人员聚合任务
        # account → realname 映射
        acc2name = {}
        for t in tasks:
            for field in ('openedBy', 'assignedTo', 'finishedBy'):
                v = t.get(field, '') or ''
                if isinstance(v, dict):
                    acc  = v.get('account', '')
                    name = v.get('realname', '') or acc
                else:
                    acc  = v
                    name = v
                if acc and acc not in acc2name:
                    acc2name[acc] = name

        # 按人员归集任务
        person_tasks = {}   # name → [task, ...]
        for t in tasks:
            # 以 assignedTo 为主要归属人
            assigned = t.get('assignedTo', '') or ''
            if isinstance(assigned, dict):
                nm = assigned.get('realname', '') or assigned.get('account', '未知')
            else:
                nm = acc2name.get(assigned, assigned) if assigned else '未分配'
            if not nm or nm == 'closed':
                nm = '未分配'
            person_tasks.setdefault(nm, []).append(t)

        # 统计每人解决的 Bug 数
        person_bugs = {}   # name → count
        for b in bugs:
            resolved_by = b.get('resolvedBy', '') or ''
            if isinstance(resolved_by, dict):
                nm = resolved_by.get('realname', '') or resolved_by.get('account', '')
            else:
                nm = resolved_by
            if nm:
                person_bugs[nm] = person_bugs.get(nm, 0) + 1

        # 按角色分组
        role_data = {}   # role → [{'name', 'stats', 'bugs'}, ...]
        for nm, tlist in person_tasks.items():
            # 取该人第一个任务判断角色
            role = detect_role((tlist[0].get('name','') if tlist else ''), '')
            role_data.setdefault(role, []).append({
                'name': nm,
                'tasks': tlist,
                'stats': calc_efficiency(tlist),
                'bugs':  person_bugs.get(nm, 0),
            })

        # 每个角色内按完成率降序
        for role in role_data:
            role_data[role].sort(key=lambda x: x['stats']['rate'], reverse=True)

        print('人员汇总:')
        for role, people in role_data.items():
            print('  %s: %d 人' % (role, len(people)))

        # 生成 HTML
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        html = make_html(year, month, role_data)
        out = OUTPUT_DIR / ('效率分析_%s.html' % month_str)
        out.write_text(html, encoding='utf-8')
        print('已写入 %s (%d KB)' % (out, len(html) // 1024))

        print('完成！')
    except Exception as e:
        print(f'错误: {e}')
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
