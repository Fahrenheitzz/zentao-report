#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
团队产出效率分析 - 按月生成（完整版）
从禅道拉取指定月份的任务/Bug数据，按角色分组统计个人效率指标，
生成独立的 HTML 报告。

样式参考：深色渐变头部 + 6概览卡片 + 角色分区表格 + 进度条 + 可展开明细 + 底部图表

用法：
  python generate_efficiency_report.py 202606        # 生成2026年6月
  python generate_efficiency_report.py                  # 默认上月
"""
import json, ssl, urllib.request, hashlib, sys, datetime, calendar
from pathlib import Path

# ── 路径配置 ──────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
CONFIG_FILE  = SCRIPT_DIR / 'zentao_config.json'
OUTPUT_DIR   = SCRIPT_DIR / 'efficiency'
PROJECT_IDS  = [1013]          # 商城3.0
ROLE_ORDER   = ['产品','后端开发','前端开发','移动端开发','测试','其他']

# ── 效率分级阈值 ───────────────────────────────────────────────────────────
EFFICIENCY_THRESHOL = {'高效': 60, '正常': 35}  # >=60% 高效，<35% 迟缓/超期

# ════════════════════════════════════════════════════════════════════════
#  禅道 API 客户端
# ════════════════════════════════════════════════════════════════════════

class ZentaoClient:
    def __init__(self, cf):
        with open(cf) as f:
            self.cfg = json.load(f)
        self.base = self.cfg['url'].rstrip('/')
        self.api  = self.base + '/api.php/v1'
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        self.ctx = ctx
        self._auth()

    def _auth(self):
        pw = hashlib.md5(self.cfg['password'].encode()).hexdigest()
        d  = json.dumps({'account': self.cfg['username'], 'password': pw}).encode()
        r  = urllib.request.Request(self.api + '/tokens', data=d,
                                   headers={'Content-Type': 'application/json'})
        self.token = json.loads(urllib.request.urlopen(r, context=self.ctx).read())['token']

    def get(self, path, params=None):
        h = {'Token': self.token, 'Content-Type': 'application/json'}
        if params:
            qs = '&'.join(k + '=' + str(v) for k, v in params.items())
            url = self.api + path + '?' + qs
        else:
            url = self.api + path
        req = urllib.request.Request(url, headers=h, method='GET')
        try:
            return json.loads(urllib.request.urlopen(req, context=self.ctx).read())
        except Exception as e:
            print(f'  [WARN] {path} -> {e}')
            return {}

# ════════════════════════════════════════════════════════════════════════
#  任务角色分类（复用 generate_iteration_reports 的逻辑）
# ════════════════════════════════════════════════════════════════════════

def classify_task(t):
    """根据任务的 type 和 name 字段判断角色分类"""
    tp = (t.get('type') or '').lower()
    nm = (t.get('name') or '').lower()
    if tp.startswith('ab'): return '产品'
    if tp.startswith('a_dev') and 'front' not in tp: return '后端开发'
    if 'front' in tp or tp.startswith('a_dev2_front'): return '前端开发'
    if any(k in tp for k in ['ios','android','mobile','app']): return '移动端开发'
    if tp.startswith('ae') or 'test' in tp: return '测试'
    if any(k in nm for k in ['test','用例','冒烟']): return '测试'
    if any(k in nm for k in ['前端','front','h5','vue','react']): return '前端开发'
    if any(k in nm for k in ['需求','调研','设计']): return '产品'
    return '后端开发'

# ════════════════════════════════════════════════════════════════════════
#  数据拉取
# ════════════════════════════════════════════════════════════════════════

def fetch_month_data(client, year, month):
    """拉取指定年月的所有任务和Bug，返回 (tasks_list, bugs_list)"""
    month_str = f'{year}-{month:02d}'
    all_tasks = []
    all_bugs  = []

    for project_id in PROJECT_IDS:
        exc_res = client.get(f'/projects/{project_id}/executions', {'limit': 100})
        executions = exc_res.get('executions', []) if isinstance(exc_res, dict) else []

        for exc in executions:
            exc_id   = exc.get('id')
            exc_begin = (exc.get('begin', '') or '')[:7]
            exc_end   = (exc.get('end', '') or '')[:7]
            if not (exc_begin <= month_str <= exc_end):
                continue

            # 拉任务（分页）
            page = 1
            while True:
                res = client.get(f'/executions/{exc_id}/tasks', {'page': page, 'limit': 100})
                tasks = res.get('tasks', []) if isinstance(res, dict) else []
                if not tasks: break
                for t in tasks:
                    finished = (t.get('finishedDate', '') or '')[:7]
                    deadline = (t.get('deadline', '') or '')[:7]
                    opened   = (t.get('openedDate', '') or '')[:7]
                    if month_str in (finished, deadline, opened):
                        # 附上迭代名
                        t['_excName'] = exc.get('name', '')
                        t['_excId']   = exc_id
                        all_tasks.append(t)
                page += 1
                if len(tasks) < 100: break

            # 拉Bug
            bugs_res = client.get(f'/executions/{exc_id}/bugs', {'limit': 2000})
            bugs = bugs_res.get('bugs', []) if isinstance(bugs_res, dict) else []
            for b in bugs:
                resolved = (b.get('resolvedDate', '') or '')[:7]
                opened   = (b.get('openedDate', '') or '')[:7]
                if month_str in (resolved, opened):
                    all_bugs.append(b)

    print(f'  任务 {len(all_tasks)} 条 / Bug {len(all_bugs)} 条')
    return all_tasks, all_bugs

# ════════════════════════════════════════════════════════════════════════
#  数据聚合 & 计算
# ════════════════════════════════════════════════════════════════════════

def get_person_name(t):
    """从任务中提取负责人姓名"""
    assigned = t.get('assignedTo', '') or ''
    if isinstance(assigned, dict):
        rn = assigned.get('realname', '')
        if rn: return rn
        return assigned.get('account', '') or '未分配'
    if assigned and assigned != 'closed':
        return assigned
    return '未分配'


def calc_overdue_count(tasks):
    """统计超期任务数（截止日期 < 今天 且 未完成）"""
    today = datetime.date.today().isoformat()
    cnt = 0
    for t in tasks:
        status = (t.get('status') or '')
        if status == 'done': continue
        dl = t.get('deadline', '') or ''
        if dl and dl < today:
            cnt += 1
    return cnt


def build_person_stats(name, tasks, bugs_resolved, bugs_open):
    """
    计算单人的效率指标。
    返回字典包含所有截图中的字段。
    """
    done_tasks  = [t for t in tasks if (t.get('status') or '') == 'done']
    doing_tasks = [t for t in tasks if (t.get('status') or '') == 'doing']
    wait_tasks  = [t for t in tasks if (t.get('status') or '') == 'wait']

    done_consumed = sum(float(t.get('consumed', 0) or 0) for t in done_tasks)
    open_estimate = sum(float(t.get('estimate', 0) or 0) for t in doing_tasks) + \
                    sum(float(t.get('estimate', 0) or 0) for t in wait_tasks)
    open_consumed = sum(float(t.get('consumed', 0) or 0) for t in doing_tasks) + \
                    sum(float(t.get('consumed', 0) or 0) for t in wait_tasks)

    total_hours = done_consumed + open_estimate
    remaining   = max(0.0, open_estimate - open_consumed)

    rate = round(done_consumed / total_hours * 100, 1) if total_hours > 0 else 0.0

    if rate >= EFFICIENCY_THRESHOL['高效']:
        level = '高效'
    elif rate < EFFICIENCY_THRESHOL['正常']:
        level = '迟缓'
    else:
        level = '正常'

    overdue = calc_overdue_count(tasks)

    return {
        'name':         name,
        'total_tasks':  len(tasks),
        'done_count':   len(done_tasks),
        'doing_count':  len(doing_tasks),
        'wait_count':   len(wait_tasks),
        'done_consumed': round(done_consumed, 1),
        'open_estimate': round(open_estimate, 1),
        'open_consumed': round(open_consumed, 1),
        'total_hours':  round(total_hours, 1),
        'remaining':    round(remaining, 1),
        'rate':         rate,
        'level':        level,
        'overdue':      overdue,
        'bugs_resolved':bugs_resolved,
        'bugs_open':    bugs_open,
        'done_tasks':   done_tasks,
        'doing_tasks':  doing_tasks,
        'wait_tasks':   wait_tasks,
    }


def aggregate_by_role(tasks, bugs):
    """将任务按人员→角色聚合，返回 role -> [person_stats, ...]"""
    # 按 assignedTo 归集任务
    person_tasks = {}  # name -> [task]
    for t in tasks:
        nm = get_person_name(t)
        person_tasks.setdefault(nm, []).append(t)

    # 按 resolvedBy 归集Bug
    person_bugs_resolved = {}  # name -> count
    person_bugs_open     = {}  # name -> count
    for b in bugs:
        rb = b.get('resolvedBy', '') or ''
        ob = b.get('openedBy', '') or ''
        if isinstance(rb, dict): rb = rb.get('realname', '') or rb.get('account', '')
        if isinstance(ob, dict): ob = ob.get('realname', '') or ob.get('account', '')
        status = b.get('status', '')
        if rb:
            person_bugs_resolved[rb] = person_bugs_resolved.get(rb, 0) + 1
        if status not in ('closed','resolved') and ob:
            person_bugs_open[ob] = person_bugs_open.get(ob, 0) + 1

    # 构建每人统计
    role_data = {}  # role -> [stats_dict, ...]
    for nm, tlist in person_tasks.items():
        role = classify_task(tlist[0]) if tlist else '其他'
        ps = build_person_stats(
            nm, tlist,
            person_bugs_resolved.get(nm, 0),
            person_bugs_open.get(nm, 0),
        )
        role_data.setdefault(role, []).append(ps)

    # 每个角色内按完成率降序
    for role in role_data:
        role_data[role].sort(key=lambda x: x['rate'], reverse=True)

    return role_data


def compute_overview(role_data):
    """计算顶部6个概览卡片的数据"""
    total_done   = sum(ps['done_count']   for people in role_data.values() for ps in people)
    total_doing  = sum(ps['doing_count']  for people in role_data.values() for ps in people)
    total_wait   = sum(ps['wait_count']   for people in role_data.values() for ps in people)
    total_people = sum(len(people)        for people in role_data.values())
    total_consumed = sum(ps['done_consumed'] for people in role_data.values() for ps in people)
    total_remaining= sum(ps['remaining']     for people in role_data.values() for ps in people)
    total_overdue  = sum(ps['overdue']      for people in role_data.values() for ps in people)
    return {
        'done':       total_done,
        'in_progress':total_doing + total_wait,
        'people':     total_people,
        'consumed_h': round(total_consumed, 1),
        'remain_h':   round(total_remaining, 1),
        'overdue':    total_overdue,
    }

# ════════════════════════════════════════════════════════════════════════
#  HTML 模板
# ════════════════════════════════════════════════════════════════════════

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;background:#f0f2f5;color:#333;padding:20px;min-width:1100px}

/* 头部 */
.header{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);color:#fff;border-radius:16px;padding:32px 36px;margin-bottom:24px;position:relative;overflow:hidden}
.header::before{content:'';position:absolute;top:-50%;right:-10%;width:400px;height:400px;background:radial-gradient(circle,rgba(79,172,254,.15),transparent);border-radius:50%}
.header h1{font-size:28px;font-weight:800;margin-bottom:8px;position:relative;z-index:1}
.header .sub{font-size:13px;color:rgba(255,255,255,.65);margin-bottom:18px;position:relative;z-index:1}
.refresh-btn{display:inline-block;background:rgba(255,255,255,.12);color:#fff;border:1px solid rgba(255,255,255,.22);padding:5px 16px;border-radius:20px;font-size:12px;cursor:pointer;transition:.2s;text-decoration:none;position:relative;z-index:1}
.refresh-btn:hover{background:rgba(255,255,255,.22)}

/* 概览卡片 */
.overview{display:flex;gap:14px;margin-bottom:24px;flex-wrap:nowrap}
.ov-card{background:#fff;border-radius:14px;padding:18px 22px;min-width:155px;flex:1;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.06);transition:transform .15s}
.ov-card:hover{transform:translateY(-2px)}
.ov-num{font-size:34px;font-weight:900;line-height:1.2}
.ov-lbl{font-size:12px;color:#888;margin-top:4px}
.c-green{color:#10b981}.c-orange{color:#f59e0b}.c-dark{color:#374151}.c-blue{color:#2563eb}.c-red{color:#ef4444}

/* 角色标签行 */
.role-tabs{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}
.role-tab{background:#fff;border-radius:12px;padding:14px 20px;min-width:160px;cursor:pointer;border:2px solid transparent;box-shadow:0 1px 4px rgba(0,0,0,.06);transition:all .15s}
.role-tab:hover{border-color:#2563eb;box-shadow:0 4px 12px rgba(37,99,235,.12)}
.role-tab.active{border-color:#2563eb;background:#eff6ff}
.rt-name{font-size:15px;font-weight:700;margin-bottom:4px;display:flex;align-items:center;gap:6px}
.rt-dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.rt-info{font-size:11.5px;color:#666}
.rt-info span{color:#10b981;font-weight:600}
.rt-doing{color:#f59e0b;font-weight:600}

/* 角色区块 */
.role-section{display:none;background:#fff;border-radius:14px;margin-bottom:20px;box-shadow:0 1px 6px rgba(0,0,0,.06);overflow:hidden}
.role-section.visible{display:block}
.rs-head{padding:14px 22px;font-size:15px;font-weight:700;border-bottom:1px solid #eee;display:flex;align-items:center;gap:10px}
.rs-bar{width:4px;height:18px;border-radius:2px;display:inline-block}
.rs-sub{font-size:12px;color:#888;font-weight:400;margin-left:auto}

/* 表格 */
.table-wrap{overflow-x:auto}
.ptable{width:100%;border-collapse:collapse;font-size:13px}
.ptable th{background:#fafafa;color:#555;padding:10px 14px;text-align:left;font-weight:600;font-size:12px;border-bottom:2px solid #eaeaea;white-space:nowrap}
.ptable td{padding:11px 14px;border-bottom:1px solid #f3f3f3;vertical-align:middle}
.ptable tr:hover td{background:#fafbff}
.idx-col{color:#aaa;width:40px;font-weight:600}
.name-col{font-weight:700;min-width:70px}
.num-col{text-align:center}
.hrs-done{color:#10b981;font-weight:700}
.hrs-total{color:#ea580c;font-weight:700}
.hrs-est{color:#555}
.hrs-spent{color:#9ca3af}
.hrs-left{color:#374151}

/* 进度条 */
.pbar-wrap{display:flex;align-items:center;gap:8px;min-width:120px}
.pbar-bg{flex:1;height:10px;background:#e5e7eb;border-radius:5px;overflow:hidden}
.pbar-fill{height:100%;border-radius:5px;transition:width .3s}
.pbar-pct{font-size:12px;font-weight:700;min-width:42px;text-align:right}
.pct-high{color:#10b981}.pct-mid{color:#2563eb}.pct-low{color:#ef4444}

/* 效率标签 */
.tag{padding:2px 10px;border-radius:4px;font-size:11.5px;font-weight:700;white-space:nowrap}
.tag-high{background:#d1fae5;color:#059669}
.tag-norm{background:#dbeafe;color:#2563eb}
.tag-slow{background:#fee2e2;color:#dc2626}

/* 展开明细 */
.detail-row{display:none;background:#fafbff}
.detail-row.expanded{display:table-row}
.detail-cell{padding:10px 14px 14px 54px}
.detail-group{margin-bottom:8px}
.dg-title{font-size:12px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;gap:4px;color:#555;padding:4px 0}
.dg-title:hover{color:#2563eb}
.dg-arrow{transition:transform .2s;font-size:10px}
.dg-arrow.open{transform:rotate(90deg)}
.dg-body{display:none;padding:4px 0 4px 18px;font-size:11.5px;color:#666}
.dg-body.show{display:block}
.tlink{color:#2563eb;text-decoration:none}
.tlink:hover{text-decoration:underline}

/* 图表区 */
.charts{display:flex;gap:20px;margin-top:28px}
.chart-box{background:#fff;border-radius:14px;padding:20px;flex:1;box-shadow:0 1px 6px rgba(0,0,0,.06)}
.chart-box h3{font-size:14px;font-weight:700;margin-bottom:16px;color:#333}
.chart-canvas{width:100%;height:340px}
"""

JS = """
function toggleRole(roleKey){
    // 切换角色tab激活状态
    document.querySelectorAll('.role-tab').forEach(function(el){
        el.classList.remove('active');
    });
    var tab=document.getElementById('rtab-'+roleKey);
    if(tab) tab.classList.add('active');
    // 切换区块显示
    document.querySelectorAll('.role-section').forEach(function(el){
        el.classList.remove('visible');
    });
    var sec=document.getElementById('rsec-'+roleKey);
    if(sec) sec.classList.add('visible');
}
function togglePerson(pid){
    var row=document.getElementById('detail-'+pid);
    if(row){ row.classList.toggle('expanded'); }
}
function toggleGroup(gid){
    var body=document.getElementById('dg-'+gid);
    var arrow=document.getElementById('da-'+gid);
    if(body){ body.classList.toggle('show'); }
    if(arrow){ arrow.classList.toggle('open'); }
}
// 默认展开第一个角色
document.addEventListener('DOMContentLoaded',function(){
    var firstRole=document.querySelector('.role-tab');
    if(firstRole) firstRole.click();
});
"""

ROLE_COLORS = {
    '产品':'#8b5cf6','后端开发':'#3b82f6','前端开发':'#06b6d4',
    '移动端开发':'#f59e0b','测试':'#10b981','其他':'#6b7280',
}


def make_progress_bar(rate):
    """生成进度条HTML"""
    color_class = 'pct-high' if rate >= 60 else ('pct-mid' if rate >= 35 else 'pct-low')
    fill_color = '#10b981' if rate >= 60 else ('#2563eb' if rate >= 35 else '#ef4444')
    return (
        f'<div class="pbar-wrap">'
        f'<div class="pbar-bg"><div class="pbar-fill" style="width:{rate}%;background:{fill_color}"></div></div>'
        f'<span class="pbar-pct {color_class}">{rate}%</span>'
        f'</div>'
    )


def make_tag(level):
    cls = {'高效':'tag-high','正常':'tag-norm','迟缓':'tag-slow'}.get(level,'tag-norm')
    return f'<span class="tag {cls}">{level}</span>'


def make_task_links(tasks, label):
    """生成任务链接列表"""
    if not tasks:
        return ''
    items = []
    for t in tasks:
        tid  = t.get('id','')
        name = (t.get('name','') or '').replace('<','&lt;').replace('>','&gt;')
        exc_name = t.get('_excName','')
        consumed = t.get('consumed',0) or 0
        est = t.get('estimate',0) or 0
        info = f'{consumed}h/{est}h' if float(est)>0 else f'{consumed}h'
        items.append(
            f'<span style="margin-right:10px"><a class="tlink" href="#">#{tid}</a> '
            f'{name} <span style="color:#aaa">({info})</span></span>'
        )
    return '<br>'.join(items)


def make_detail_rows(person, idx):
    """生成可展开的明细行HTML"""
    pid = f'p{idx}'
    gid_done  = f'{pid}-done'
    gid_doing = f'{pid}-doing'
    gid_bug   = f'{pid}-bug'

    html = f'''
<tr id="detail-{pid}" class="detail-row">
  <td colspan="10">
    <div class="detail-cell">
      <div class="detail-group">
        <div class="dg-title" onclick="toggleGroup('{gid_done}')">
          <span class="dg-arrow" id="da-{gid_done}">&#9654;</span>
          当月已完成任务 ({person['done_count']}项)
        </div>
        <div class="dg-body" id="dg-{gid_done}">
          {make_task_links(person['done_tasks'],'已完成') or '<span style="color:#aaa">无</span>'}
        </div>
      </div>
      <div class="detail-group">
        <div class="dg-title" onclick="toggleGroup('{gid_doing}')">
          <span class="dg-arrow" id="da-{gid_doing}">&#9654;</span>
          进行中任务 ({person['doing_count']}+{person['wait_count']}项)
        </div>
        <div class="dg-body" id="dg-{gid_doing}">
          {make_task_links(person['doing_tasks']+person['wait_tasks'],'进行中') or '<span style="color:#aaa">无</span>'}
        </div>
      </div>
      <div class="detail-group">
        <div class="dg-title" onclick="toggleGroup('{gid_bug}')">
          <span class="dg-arrow" id="da-{gid_bug}">&#9654;</span>
          Bug ({person['bugs_resolved']}解决 + {person['bugs_open']}活跃)
        </div>
        <div class="dg-body" id="dg-{gid_bug}">
          <span style="color:#aaa">暂无Bug明细数据</span>
        </div>
      </div>
    </div>
  </td>
</tr>'''
    return html


def make_role_table(role_key, people):
    """生成一个角色的完整表格HTML"""
    # 计算角色汇总
    r_done   = sum(p['done_count'] for p in people)
    r_dh     = sum(p['done_consumed'] for p in people)
    r_doing  = sum(p['doing_count']+p['wait_count'] for p in people)

    rows = ''
    for i, p in enumerate(people):
        rows += f'''<tr style="cursor:pointer" onclick="togglePerson('p{role_key}-{i}')">
  <td class="idx-col">{i+1}</td>
  <td class="name-col">{p['name']}</td>
  <td class="num-col">{p['total_tasks']}</td>
  <td>{make_progress_bar(p['rate'])}</td>
  <td class="num-col hrs-total">{p['total_hours']}h</td>
  <td class="num-col hrs-done">{p['done_consumed']}h</td>
  <td class="num-col hrs-est">{p['open_estimate']}h</td>
  <td class="num-col hrs-spent">{p['open_consumed']}h</td>
  <td class="num-col hrs-left">{p['remaining']}h</td>
  <td>{make_tag(p['level'])}</td>
</tr>'''
        rows += make_detail_rows(p, f'{role_key}-{i}')

    return (
        f'<div class="role-section" id="rsec-{role_key}">'
        f'<div class="rs-head">'
        f'<span class="rs-bar" style="background:{ROLE_COLORS.get(role_key,"#999")}"></span>'
        f'<span>{role_key}</span>'
        f'<span class="rs-sub">{len(people)}人 · 当月完成 {r_done} 任务 · 消耗 {r_dh:.1f}h</span>'
        f'</div>'
        f'<div class="table-wrap">'
        f'<table class="ptable">'
        f'<thead><tr>'
        f'<th>#</th><th>人员</th><th>总任务</th><th>完成率</th>'
        f'<th>总工时</th><th>已完成消耗</th><th>未完成预估</th>'
        f'<th>未完成已耗</th><th>未完剩余</th><th>效率</th>'
        f'</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table></div></div>'
    )


def make_role_tabs(role_data):
    """生成角色标签行HTML"""
    tabs = ''
    for role in ROLE_ORDER:
        people = role_data.get(role, [])
        if not people: continue
        done_cnt = sum(p['done_count'] for p in people)
        dh = sum(p['done_consumed'] for p in people)
        doing_cnt = sum(p['doing_count']+p['wait_count'] for p in people)
        clr = ROLE_COLORS.get(role,'#999')
        tabs += (
            f'<div class="role-tab" id="rtab-{role}" onclick="toggleRole(\'{role}\')">'
            f'<div class="rt-name"><span class="rt-dot" style="background:{clr}"></span>{role}</div>'
            f'<div class="rt-info">{len(people)}人 · 完成<span>{done_cnt}</span>个/{dh:.1f}h · 进行中<span class="rt-doing">{doing_cnt}</span>个</div>'
            f'</div>'
        )
    return tabs


def make_chart_js(role_data):
    """生成Chart.js图表数据和初始化代码"""
    # ---- 左图: 人员堆叠柱状图 ----
    all_people = []
    for role in ROLE_OPTIONS:
        for p in role_data.get(role, []):
            all_people.append(p)

    p_names = [p['name'][:4] for p in all_people]
    p_done  = [p['done_consumed'] for p in all_people]
    p_spent = [p['open_consumed'] for p in all_people]
    p_left  = [p['remaining'] for p in all_people]

    # ---- 右图: 角色分组柱状图 ----
    r_labels = [r for r in ROLE_OPTIONS if r in role_data]
    r_done2  = [sum(p['done_consumed'] for p in role_data[r]) for r in r_labels]
    r_est2   = [sum(p['open_estimate'] for p in role_data[r]) for r in r_labels]

    lines = []
    lines.append('<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>')
    lines.append('<script>')
    lines.append('(function(){')
    lines.append("Chart.defaults.font.family='-apple-system,\"Segoe UI\",\"PingFang SC\",\"Microsoft YaHei\",sans-serif';")
    lines.append('Chart.defaults.font.size=11;')
    lines.append("Chart.defaults.color='#666';")
    lines.append('var ctx1=document.getElementById(\'chart1\').getContext(\'2d\');')
    ds1a = "label:'已完成消耗',data:%s,backgroundColor:'#10b981'" % json.dumps(p_done)
    ds1b = "label:'进行中已耗',data:%s,backgroundColor:'#3b82f6'" % json.dumps(p_spent)
    ds1c = "label:'进行中剩余',data:%s,backgroundColor:'#d1d5db'" % json.dumps(p_left)
    lines.append("new Chart(ctx1,{type:'bar',data:{labels:%s,datasets:[{%s},{%s},{%s}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top'},title:{display:false}},scales:{x:{stacked:true},y:{stacked:true,title:{display:true,text:'工时(h)'}}}}});" % (
        json.dumps(p_names), ds1a, ds1b, ds1c))
    lines.append('var ctx2=document.getElementById(\'chart2\').getContext(\'2d\');')
    ds2a = "label:'已完成消耗',data:%s,backgroundColor:'#10b981'" % json.dumps(r_done2)
    ds2b = "label:'进行中预估',data:%s,backgroundColor:'#f59e0b'" % json.dumps(r_est2)
    lines.append("new Chart(ctx2,{type:'bar',data:{labels:%s,datasets:[{%s},{%s}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top'},title:{display:false}},scales:{y:{title:{display:true,text:'工时(h)'}}}}});" % (
        json.dumps(r_labels), ds2a, ds2b))
    lines.append('})();')
    lines.append('</script>')

    return '\n'.join(lines)


def build_html(year, month, role_data, overview):
    """构建完整HTML页面"""
    month_label = f'{year}年{month}月'
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    ov = overview

    parts = []
    parts.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    parts.append(f'<title>{month_label} 团队产出效率分析</title>')
    parts.append(f'<style>{CSS}</style>')
    parts.append(f'</head><body>')

    # ── 头部 ──
    parts.append(f'''
<div class="header">
  <h1>{month_label} 团队产出效率分析</h1>
  <p class="sub">功能:角色分组 · 全量迭代 · {now_str}</p>
  <a class="refresh-btn" href="#" onclick="location.reload()">⟳ 实时刷新</a>
</div>''')

    # ── 概览卡片 ──
    parts.append('<div class="overview">')
    cards = [
        (f'{ov["done"]}','当月已完成','c-green'),
        (f'{ov["in_progress"]}','进行中','c-orange'),
        (f'{ov["people"]}','参与人员','c-dark'),
        (f'{ov["consumed_h"]}h','总消耗工时','c-blue'),
        (f'{ov["remain_h"]}h','剩余工时','c-blue'),
        (f'{ov["overdue"]}','超期任务','c-red'),
    ]
    for val, lbl, cls in cards:
        parts.append(f'<div class="ov-card"><div class="ov-num {cls}">{val}</div><div class="ov-lbl">{lbl}</div></div>')
    parts.append('</div>')

    # ── 角色标签 ──
    parts.append('<div class="role-tabs">')
    parts.append(make_role_tabs(role_data))
    parts.append('</div>')

    # ── 各角色表格 ──
    for role in ROLE_OPTIONS:
        if role in role_data:
            parts.append(make_role_table(role, role_data[role]))

    # ── 图表 ──
    parts.append('<div class="charts">')
    parts.append('<div class="chart-box"><h3>人员消耗工时（已完成+进行中+剩余）</h3>')
    parts.append('<div class="chart-canvas"><canvas id="chart1"></canvas></div></div>')
    parts.append('<div class="chart-box"><h3>各角色完成 vs 进行中</h3>')
    parts.append('<div class="chart-canvas"><canvas id="chart2"></canvas></div></div>')
    parts.append('</div>')

    parts.append(f'<script>{JS}</script>')
    parts.append(make_chart_js(role_data))
    parts.append('</body></html>')

    return '\n'.join(parts)

ROLE_OPTIONS = ['产品','后端开发','前端开发','移动端开发','测试','其他']

# ════════════════════════════════════════════════════════════════════════
#  main
# ════════════════════════════════════════════════════════════════════════

def main():
    # 解析参数
    if len(sys.argv) >= 2:
        arg = sys.argv[1]; year=int(arg[:4]); month=int(arg[4:6])
    else:
        today=datetime.date.today()
        year, month=(today.year-1, 12) if today.month==1 else (today.year, today.month-1)

    month_label=f'{year}年{month}月'
    print('='*56)
    print(f'团队产出效率分析 - {month_label}')
    print('='*56)

    client=ZentaoClient(str(CONFIG_FILE))
    print('[OK] 禅道连接成功')

    tasks, bugs = fetch_month_data(client, year, month)
    print('[OK] 数据拉取完成')

    role_data = aggregate_by_role(tasks, bugs)
    print('[OK] 角色聚合完成:')
    for role, people in role_data.items():
        print(f'    {role}: {len(people)}人')

    overview = compute_overview(role_data)
    print(f'\n  总览: 已完成={overview["done"]} | 进行中={overview["in_progress"]} | 人员={overview["people"]} | 超期={overview["overdue"]}')

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html = build_html(year, month, role_data, overview)
    out_file = OUTPUT_DIR / f'效率分析_{year}{month:02d}.html'
    out_file.write_text(html, encoding='utf-8')
    size_kb = len(html.encode('utf-8')) // 1024
    print(f'\n[OK] 报告已写入: {out_file} ({size_kb} KB)')
    print('完成!')


if __name__=='__main__':
    try: main()
    except Exception as e:
        print(f'\n错误: {e}')
        import traceback; traceback.print_exc()
        sys.exit(1)
