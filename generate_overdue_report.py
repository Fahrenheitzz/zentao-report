#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
延期任务统计报告 - 按日生成
从禅道拉取所有超期未完成任务，按人员分组统计，生成独立的 HTML 报告。

用法：
  python generate_overdue_report.py              # 生成今日报告
  python generate_overdue_report.py 2026-06-22   # 生成指定日期
"""
import json, ssl, urllib.request, hashlib, sys, datetime
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / 'zentao_config.json'
OUTPUT_DIR = Path(__file__).parent

# ════════════════════════════════════════════════════════════════════════
#  复用 ZentaoClient
# ════════════════════════════════════════════════════════════════════════
sys.path.insert(0, str(Path(__file__).parent))
from generate_iteration_reports import ZentaoClient


def get_today_str():
    if len(sys.argv) >= 2:
        return sys.argv[1]
    return datetime.date.today().strftime('%Y-%m-%d')


# ════════════════════════════════════════════════════════════════════════
#  数据拉取：超期未完成任务
# ════════════════════════════════════════════════════════════════════════
STATUS_MAP = {
    'wait': '待处理', 'doing': '进行中', 'done': '已完成',
    'closed': '已关闭', 'pause': '已暂停', 'cancel': '已取消',
}
PRIORITY_MAP = {
    '1': '1-紧急', '2': '2-高', '3': '3-中', '4': '4-低',
}


def fetch_overdue_tasks(client):
    """拉取所有超期未完成任务（deadline < today 且 status not in done/closed）"""
    today = datetime.date.today().strftime('%Y-%m-%d')

    # 通过项目获取迭代，再获取每个迭代的任务
    project_id = 1013
    all_tasks = []

    # 获取项目下的迭代
    executions_res = client.get(f'/projects/{project_id}/executions', {'limit': 200})
    executions = executions_res.get('executions', []) if isinstance(executions_res, dict) else []

    for exc in executions:
        exc_id = exc.get('id')
        exc_name = exc.get('name', '')
        tasks_res = client.get(f'/executions/{exc_id}/tasks', {'limit': 500})
        tasks_list = tasks_res.get('tasks', []) if isinstance(tasks_res, dict) else []
        for t in tasks_list:
            t['_execution_name'] = exc_name
            t['_execution_id'] = exc_id
            all_tasks.append(t)

    # 也获取主项目的直接任务（不在任何迭代中）
    main_tasks_res = client.get(f'/projects/{project_id}/tasks', {'limit': 500})
    main_tasks = main_tasks_res.get('tasks', []) if isinstance(main_tasks_res, dict) else []
    for t in main_tasks:
        if not any(t.get('id') == et.get('id') for et in all_tasks):
            t['_execution_name'] = ''
            t['_execution_id'] = None
            all_tasks.append(t)

    print(f'  全量任务: {len(all_tasks)} 条')

    # 过滤超期任务
    overdue = []
    for t in all_tasks:
        status = t.get('status', '')
        deadline = t.get('deadline', '') or ''
        # 超期条件：有截止日期、截止日期在今天之前、状态未完成/关闭
        if status in ('done', 'closed'):
            continue
        if not deadline:
            continue
        if deadline < today:
            overdue.append(t)

    print(f'  超期任务: {len(overdue)} 条')
    return overdue


def aggregate_by_person(overdue_tasks):
    """按负责人聚合"""
    persons = {}  # realname -> {tasks:[], stats:{status_count, priority_count}}
    for t in overdue_tasks:
        assigned_to = t.get('assignedTo', '') or ''
        if isinstance(assigned_to, dict):
            name = assigned_to.get('realname', '') or assigned_to.get('account', '未知')
        elif assigned_to == 'closed':
            name = '已关闭'
        else:
            name = assigned_to if assigned_to else '未分配'

        if name not in persons:
            persons[name] = {'tasks': [], 'status_counts': {}, 'priority_counts': {},
                             'total_overdue_h': 0}

        persons[name]['tasks'].append(t)

        # 状态统计
        status = t.get('status', 'wait')
        sl = STATUS_MAP.get(status, status)
        persons[name]['status_counts'][sl] = persons[name]['status_counts'].get(sl, 0) + 1

        # 优先级统计
        pri = str(t.get('priority', '3'))
        pl = PRIORITY_MAP.get(pri, pri + '-未知')
        persons[name]['priority_counts'][pl] = persons[name]['priority_counts'].get(pl, 0) + 1

        # 超期时长估算（基于消耗工时）
        consumed = float(t.get('consumed', 0) or 0)
        persons[name]['total_overdue_h'] += consumed

    return persons


def calc_overview(person_data, overdue_tasks):
    """计算概览数据"""
    total = len(overdue_tasks)
    status_total = {}
    priority_total = {}
    person_set = set()

    for pname, pd in person_data.items():
        if pname in ('未分配', '已关闭'):
            continue
        person_set.add(pname)
        for s, c in pd['status_counts'].items():
            status_total[s] = status_total.get(s, 0) + c
        for p, c in pd['priority_counts'].items():
            priority_total[p] = priority_total.get(p, 0) + c

    return {
        'total': total,
        'pending': status_total.get('待处理', 0),
        'doing': status_total.get('进行中', 0),
        'overdue': total,
        'people': len(person_set),
        'status_dist': status_total,
        'priority_dist': priority_total,
    }


# ════════════════════════════════════════════════════════════════════════
#  HTML 模板
# ════════════════════════════════════════════════════════════════════════
CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;background:#f5f7fa;color:#333;padding:20px;min-width:1100px}

/* 头部 */
.header{background:linear-gradient(135deg,#dc2626,#b91c1c,#991b1b);color:#fff;border-radius:16px;padding:24px 32px;margin-bottom:24px;position:relative;overflow:hidden}
.header::before{content:'';position:absolute;top:-50%;right:-10%;width:400px;height:400px;background:radial-gradient(circle,rgba(255,255,255,.08),transparent);border-radius:50%}
.header-inner{display:flex;align-items:center;justify-content:space-between;gap:16px;position:relative;z-index:1}
.header-left{display:flex;align-items:center;gap:14px;min-width:0}
.header-center{text-align:center;flex:1;min-width:0}
.header-right{flex-shrink:0}
.home-btn{display:inline-flex;align-items:center;gap:5px;padding:6px 16px;
    background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.25);
    color:#fff;border-radius:20px;font-size:12px;text-decoration:none;
    transition:.25s;white-space:nowrap;flex-shrink:0}
.home-btn:hover{background:rgba(255,255,255,.28)}
.header h1{font-size:26px;font-weight:800;margin-bottom:4px;display:flex;align-items:center;justify-content:center;gap:8px}
.header .sub{font-size:12px;color:rgba(255,255,255,.6);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:center}
.refresh-btn{display:inline-flex;align-items:center;gap:5px;background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.25);padding:6px 18px;border-radius:20px;font-size:12px;cursor:pointer;transition:.2s;text-decoration:none;white-space:nowrap;flex-shrink:0}
.refresh-btn:hover{background:rgba(255,255,255,.28)}

/* 概览卡片 */
.overview{display:flex;gap:16px;margin-bottom:24px;flex-wrap:nowrap}
.ov-card{background:#fff;border-radius:14px;padding:18px 22px;min-width:140px;flex:1;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.06);transition:transform .15s}
.ov-card:hover{transform:translateY(-2px)}
.ov-num{font-size:36px;font-weight:900;line-height:1.2}
.ov-lbl{font-size:12px;color:#888;margin-top:4px}
.c-red{color:#ef4444}.c-orange{color:#f97316}.c-blue{color:#3b82f6}.c-dark{color:#374151}.c-green{color:#10b981}

/* 图表区域 */
.charts-row{display:flex;gap:20px;margin-top:28px}
.chart-box{background:#fff;border-radius:14px;padding:20px;flex:1;box-shadow:0 1px 6px rgba(0,0,0,.06)}
.chart-title{font-size:14px;font-weight:700;margin-bottom:16px;color:#333;text-align:center}
.chart-canvas{width:100%;height:340px}
.chart-canvas canvas{width:100%!important;height:100%!important}

/* 明细区域 */
.detail-section{background:#fff;border-radius:14px;padding:24px;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:24px}
.detail-header{font-size:16px;font-weight:700;color:#374151;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.person-row{border:1px solid #e5e7eb;border-radius:10px;margin-bottom:10px;overflow:hidden;transition:box-shadow .15s}
.person-row:hover{box-shadow:0 2px 8px rgba(0,0,0,.08)}
.person-head{padding:14px 18px;cursor:pointer;display:flex;align-items:center;justify-content:space-between;background:#fafbfc;transition:background .15s}
.person-head:hover{background:#f3f4f6}
.pn-name{font-size:14px;font-weight:700;color:#1e293b}
.pn-tags{display:flex;gap:8px;flex-wrap:wrap}
.tag{display:inline-block;padding:2px 10px;border-radius:10px;font-size:11px;font-weight:600}
.tag-wait{background:#fee2e2;color:#dc2626}
.tag-doing{background:#dbeafe;color:#2563eb}
.tag-pri-high{background:#fef3c7;color:#d97706}
.tag-pri-mid{background:#f3e8ff;color:#7c3aed}
.tag-pri-low{background:#ecfdf5;color:#059669}
.tag-h{background:#f0fdf4;color:#15803d}
.pn-detail{display:none;padding:16px 18px;border-top:1px solid #eee;background:#fff}
.detail-table{width:100%;border-collapse:collapse}
.detail-table th{text-align:left;font-size:11px;color:#6b7280;font-weight:600;padding:8px 10px;border-bottom:2px solid #f0f0f0;background:#fafafa}
.detail-table td{font-size:12px;padding:10px;border-bottom:1px solid #f3f4f6;color:#374151}
.detail-table tr:last-child td{border-bottom:none}
.task-name{max-width:350px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#1e293b;font-weight:500}
.exp-arrow{font-size:11px;color:#9ca3af;transition:transform .2s}
.exp-arrow.open{transform:rotate(90deg)}

/* 页脚 */
.ft{text-align:center;margin-top:40px;padding-top:20px;border-top:1px solid #eee;color:#9ca3af;font-size:11px;letter-spacing:1px}
"""


def build_html(today_str, person_data, overview):
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ov = overview

    parts = []
    parts.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    parts.append('<title>延期任务统计报告</title>')
    parts.append('<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>')
    parts.append(f'<style>{CSS}</style></head><body>')

    # ── 头部 ──
    parts.append(f'''
<div class="header">
  <div class="header-inner">
    <div class="header-left">
      <a class="home-btn" href="../index.html">← 返回报告中心</a>
    </div>
    <div class="header-center">
      <h1>⏰ 延期任务统计报告</h1>
      <p class="sub">数据截至: {today_str} | 全平台超期任务追踪 | 共 {ov["total"]} 个延期任务</p>
    </div>
    <div class="header-right">
      <a class="refresh-btn" href="#" onclick="triggerRefresh();return false;">⟳ 实时刷新</a>
    </div>
  </div>
</div>''')

    # ── 概览卡片 ──
    parts.append('<div class="overview">')
    cards = [
        (f'{ov["total"]}', '超期任务总数', 'c-red'),
        (f'{ov["pending"]}', '待处理', 'c-orange'),
        (f'{ov["doing"]}', '进行中', 'c-blue'),
        (f'{ov["overdue"]}', '超期', 'c-red'),
        (f'{ov["people"]}', '涉及人员', 'c-dark'),
    ]
    for num, lbl, color_class in cards:
        parts.append(f'<div class="ov-card"><div class="ov-num {color_class}">{num}</div><div class="ov-lbl">{lbl}</div></div>')
    parts.append('</div>')

    # ── 图表区域 ──
    parts.append('<div class="charts-row">')
    # 左：人员柱状图
    sorted_persons = sorted(
        [(k, v) for k, v in person_data.items() if k not in ('未分配', '已关闭')],
        key=lambda x: len(x[1]['tasks']), reverse=True
    )
    p_names = [p[0][:4] for p in sorted_persons]
    p_counts = [len(p[1]['tasks']) for p in sorted_persons]
    bar_colors = ['#ef4444','#f97316','#f59e0b','#3b82f6','#8b5cf6','#10b981','#06b6d4']

    parts.append(f'''<div class="chart-box">
  <div class="chart-title">📊 超期任务按人员分布</div>
  <div class="chart-canvas"><canvas id="chartPerson"></canvas></div>
</div>''')

    # 中：状态饼图
    status_labels = list(ov['status_dist'].keys())
    status_values = list(ov['status_dist'].values())
    pie_status_colors = ['#ef4444', '#22c55e']
    parts.append(f'''<div class="chart-box">
  <div class="chart-title">📈 任务状态分布</div>
  <div class="chart-canvas"><canvas id="chartStatus"></canvas></div>
</div>''')

    # 右：优先级饼图
    pri_labels = list(ov['priority_dist'].keys())
    pri_values = list(ov['priority_dist'].values())
    parts.append(f'''<div class="chart-box">
  <div class="chart-title">🎯 优先级分布</div>
  <div class="chart-canvas"><canvas id="chartPriority"></canvas></div>
</div>''')

    parts.append('</div>')

    # ── 明细区域 ──
    parts.append('<div class="detail-section">')
    parts.append('<div class="detail-header">👥 按负责人明细 （点击展开）</div>')

    for idx, (pname, pdata) in enumerate(sorted_persons):
        tasks = pdata['tasks']
        scounts = pdata['status_counts']
        pcounts = pdata['priority_counts']

        tags_html = ''
        for s, c in scounts.items():
            cls = 'tag-wait' if s == '待处理' else 'tag-doing'
            tags_html += f'<span class="tag {cls}">{s}{c}</span>'
        for p, c in pcounts.items():
            if '高' in p or '紧急' in p:
                cls = 'tag-pri-high'
            elif '中' in p:
                cls = 'tag-pri-mid'
            else:
                cls = 'tag-pri-low'
            tags_html += f'<span class="tag {cls}">{p}{c}</span>'

        # 超期工时
        oh = round(pdata['total_overdue_h'], 1)
        tags_html += f'<span class="tag tag-h">超期{oh}h</span>'

        parts.append(f'''
<div class="person-row">
  <div class="person-head" onclick="togglePerson({idx})">
    <span style="display:flex;align-items:center;gap:8px">
      <span class="exp-arrow" id="arrow{idx}">▶</span>
      <span class="pn-name">{pname}</span>
    </span>
    <span class="pn-tags">{tags_html}</span>
  </div>
  <div class="pn-detail" id="detail{idx}" style="display:none">
    <table class="detail-table">
      <thead><tr>
        <th>#</th><th>任务名称</th><th>状态</th><th>优先级</th><th>截止日期</th><th>迭代</th><th>消耗/预估(h)</th>
      </tr></thead>
      <tbody>''')

        for ti, t in enumerate(tasks, 1):
            tname = t.get('name', '')
            ts = STATUS_MAP.get(t.get('status', ''), t.get('status', ''))
            tp = PRIORITY_MAP.get(str(t.get('priority', '')), t.get('priority', ''))
            tdl = t.get('deadline', '-')
            tex = t.get('_execution_name', '-')
            tc = t.get('consumed', 0) or 0
            te = t.get('estimate', 0) or 0
            parts.append(f'''<tr>
          <td>{ti}</td><td class="task-name" title="{tname.replace(chr(34), '&quot;')}">{tname}</td>
          <td>{ts}</td><td>{tp}</td><td>{tdl}</td><td>{tex}</td><td>{tc}/{te}</td>
        </tr>''')

        parts.append('''</tbody></table>
  </div>
</div>''')

    parts.append('</div>')

    # ── 页脚 ──
    parts.append(f'<div class="ft">延期任务统计报告 · {now_str}</div>')

    # ── JS ──
    import json as _json
    bar_colors_list = bar_colors[:len(p_names)]

    # 将所有数据序列化为 JS 变量，避免 f-string 花括号嵌套问题
    data_vars = {
        'pNames': p_names,
        'pCounts': p_counts,
        'barColors': bar_colors_list,
        'statusLabels': status_labels,
        'statusValues': status_values,
        'statusColors': pie_status_colors,
        'priLabels': pri_labels,
        'priValues': pri_values,
    }

    js = """
// 展开/收起明细
function togglePerson(idx){
    var d=document.getElementById('detail'+idx);
    var a=document.getElementById('arrow'+idx);
    if(d.style.display==='block'){d.style.display='none';a.classList.remove('open');}
    else{d.style.display='block';a.classList.add('open');}
}

// 刷新
function triggerRefresh(){
    var btn=document.querySelector('.refresh-btn');
    if(!btn) return;
    btn.innerHTML='<span>&#8987; 刷新中...</span>';
    fetch('http://127.0.0.1:8899/refresh?report=overdue').then(function(r){return r.text();}).catch(function(){});
    setTimeout(function(){location.reload();},8000);
}

// 图表
document.addEventListener('DOMContentLoaded', function(){
    try {
        Chart.defaults.font.family='-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif';
        Chart.defaults.font.size=11;
        Chart.defaults.color='#666';

        // 人员柱状图
        new Chart(document.getElementById('chartPerson'),{
            type:'bar',
            data:{
                labels: __PNAMES__,
                datasets:[{
                    label:'超期数',
                    data: __PCOUNTS__,
                    backgroundColor: __BARCOLORS__,
                    borderRadius:6,
                    borderSkipped:false
                }]
            },
            options:{
                responsive:true,
                maintainAspectRatio:false,
                plugins:{legend:{display:false},title:{display:false}},
                scales:{y:{beginAtZero:true,ticks:{stepSize:1}}}
            }
        });

        // 状态饼图
        new Chart(document.getElementById('chartStatus'),{
            type:'pie',
            data:{
                labels: __STATUSLABELS__,
                datasets:[{
                    data: __STATUSVALUES__,
                    backgroundColor: __STATUSCOLORS__
                }]
            },
            options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}}}
        });

        // 优先级饼图
        new Chart(document.getElementById('chartPriority'),{
            type:'pie',
            data:{
                labels: __PRILABELS__,
                datasets:[{
                    data: __PRIVALUES__,
                    backgroundColor:['#ef4444','#f59e0b','#3b82f6','#8b5cf6','#10b981','#06b6d4']
                }]
            },
            options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}}}
        });
    } catch(e) { console.error('Chart init error:', e); }
});
"""

    # 用实际数据替换占位符（避免 f-string 嵌套）
    for key, val in data_vars.items():
        placeholder = '__' + key.upper() + '__'
        js = js.replace(placeholder, _json.dumps(val, ensure_ascii=False))

    parts.append('<script>' + js + '</script>')
    parts.append('</body></html>')
    return '\n'.join(parts)


# ════════════════════════════════════════════════════════════════════════
#  主函数
# ════════════════════════════════════════════════════════════════════════
def main():
    today_str = get_today_str()
    print('=' * 55)
    print('延期任务统计报告')
    print('  日期:', today_str)
    print('=' * 55)

    client = ZentaoClient(str(CONFIG_FILE))
    print('[OK] 禅道连接成功')

    overdue_tasks = fetch_overdue_tasks(client)
    print('[OK] 数据拉取完成')

    person_data = aggregate_by_person(overdue_tasks)
    overview = calc_overview(person_data, overdue_tasks)
    print(f'[OK] 统计完成: 总计={overview["total"]} | 待处理={overview["pending"]} | 进行中={overview["doing"]}')
    print(f'     人员: {list(person_data.keys())}')

    html = build_html(today_str, person_data, overview)

    # 输出到以日期命名的目录
    date_dir = OUTPUT_DIR / today_str
    date_dir.mkdir(parents=True, exist_ok=True)
    out_file = date_dir / '延期任务统计报告.html'
    out_file.write_text(html, encoding='utf-8')
    size_kb = len(html.encode('utf-8')) // 1024
    print(f'\n[OK] 报告已写入: {out_file} ({size_kb} KB)')
    print('完成!')


if __name__ == '__main__':
    main()
