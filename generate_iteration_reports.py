#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成每个迭代的执行进展分析报告页面
参考 yang-chad.github.io/tasks 的迭代报告样式（浅色主题 + 蓝色主色）
特性：Tab按分类切换 + 每类内按人折叠面板展示任务明细
"""
import json, hashlib, urllib.request, ssl
from datetime import datetime
from pathlib import Path

CONFIG_FILE = r'C:\Users\A80369\.zentao\config.json'
OUTPUT_DIR  = Path(r'D:\workbuddy\PM work\zentao-report')
PROJECT_IDS   = [1013, 4047]
PROJECT_NAMES  = {1013: '商城3.0', 4047: '格力官网'}
CATEGORIES    = ['产品', '后端开发', '前端开发', '移动端开发', '测试']
CAT_ICONS     = {'产品': '\U0001f4cb', '后端开发': '\u2699', '前端': '\U0001f338',
                 '移动端开发': '\U0001f4f1', '测试': '\U0001f52c'}

# 需求阶段中文标签映射
STAGE_LABEL_ZH = {
    "wait": "未开始",
    "projected": "已立项",
    "developing": "开发中",
    "developed": "开发完成",
    "testing": "测试中",
    "tested": "测试完成",
    "verified": "已验证",
    "released": "已发布",
    "closed": "已关闭",
}

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
            print('  [WARN] %s -> %s' % (path, e))
            return {}

def classify_task(t):
    tp = (t.get('type') or '').lower()
    nm = (t.get('name') or '').lower()
    if tp.startswith('ab'): return '产品'
    if tp.startswith('a_dev') and 'front' not in tp: return '后端开发'
    if 'front' in tp or tp.startswith('a_dev2_front'): return '前端'
    if any(k in tp for k in ['ios','android','mobile','app']): return '移动端开发'
    if tp.startswith('ae') or 'test' in tp: return '测试'
    if any(k in nm for k in ['test','用例','冒烟']): return '测试'
    if any(k in nm for k in ['前端','front','h5','vue','react']): return '前端'
    if any(k in nm for k in ['需求','调研','设计']): return '产品'
    return '后端开发'

def g_status(s):
    m = {'wait':'待处理','doing':'进行中','done':'已完成','pause':'暂停','cancel':'已取消'}
    return m.get(s, s or '-')

def g_pri(p):
    m = {'1':'紧急','2':'高','3':'中','4':'低'}
    return m.get(p, p or '-')

def fetch_iteration_data(client, exc):
    eid = exc['id']
    data = {'exc': exc, 'tasks': [], 'stories': [], 'bugs': []}
    detail = client.get('/executions/%d' % eid)
    data['detail'] = detail.get('execution', {})

    page = 1
    while True:
        res = client.get('/executions/%d/tasks' % eid, {'page': page, 'limit': 100})
        ts = res.get('tasks', [])
        if not ts: break
        for t in ts:
            t['_st'] = t.get('status', 'wait')
            rn = t.get('assignedToRealName', '') or ''
            if not rn and isinstance(t.get('assignedTo'), dict):
                rn = t['assignedTo'].get('realname', '')
            t['_rn'] = rn
            t['_dl'] = t.get('deadline', '') or ''
            t['_cat'] = classify_task(t)
        data['tasks'].extend(ts)
        if len(ts) < 100: break
        page += 1

    stories_res = client.get('/executions/%d/stories' % eid)
    data['stories'] = stories_res.get('stories', [])
    bugs_res = client.get('/executions/%d/bugs' % eid)
    data['bugs'] = bugs_res.get('bugs', [])
    return data

def calc_time_progress(begin_str, end_str, today_str):
    try:
        begin = datetime.strptime(begin_str[:10], '%Y-%m-%d')
        end   = datetime.strptime(end_str[:10], '%Y-%m-%d')
        today = datetime.strptime(today_str, '%Y-%m-%d')
        total_days = (end - begin).days
        elapsed   = max((today - begin).days, 0)
        pct = min(int(elapsed / total_days * 100), 99) if total_days > 0 else 0
        return pct, elapsed, total_days
    except:
        return 0, 0, 0

# ============================================================
# CSS 模板
# ============================================================
CSS_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>迭代执行进展报告</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Microsoft YaHei','PingFang SC','Segoe UI',sans-serif;
    background:#f3f4f6;min-height:100vh;color:#1f2937;padding:16px}
.header{background:linear-gradient(135deg,#2563eb,#3b82f6,#60a5fa);
    border-radius:12px 12px 0 0;padding:28px 32px;color:#fff;text-align:center;
    box-shadow:0 4px 20px rgba(37,99,235,0.25);position:relative}
.header-icon{font-size:36px;margin-bottom:8px}
.header h1{font-size:22px;font-weight:800;letter-spacing:0.5px;margin-bottom:6px}
.header .sub{opacity:0.85;font-size:13px}
.refresh-btn{display:inline-block;margin-top:10px;padding:5px 18px;border-radius:20px;
    background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.35);color:#fff;
    font-size:12px;text-decoration:none;transition:all .2s}
.refresh-btn:hover{background:rgba(255,255,255,0.3)}
.home-btn{position:absolute;left:20px;top:50%;transform:translateY(-50%);
    padding:5px 14px;border-radius:20px;
    background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.3);color:#fff;
    font-size:12px;text-decoration:none;transition:all .2s;white-space:nowrap}
.home-btn:hover{background:rgba(255,255,255,0.28)}
.card-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;
    padding:20px;background:#fff;border-radius:0 0 12px 12px;margin-bottom:20px;
    box-shadow:0 1px 3px rgba(0,0,0,0.06)}
.stat-card{text-align:center;padding:18px 12px;border-radius:10px;
    background:#f8fafc;border:1px solid #e2e8f0;transition:all .2s}
.stat-card:hover{box-shadow:0 4px 12px rgba(0,0,0,0.08);transform:translateY(-2px)}
.stat-card .sc-icon{font-size:24px;margin-bottom:6px}
.sc-label{font-size:13px;color:#6b7280;margin-bottom:4px}
.sc-value{font-size:30px;font-weight:800}
.sc-sub{font-size:12.5px;color:#9ca3af;margin-top:4px}
.progress-bar{height:6px;border-radius:3px;background:#e5e7eb;margin-top:8px;overflow:hidden}
.progress-fill{height:100%;border-radius:3px;transition:width .6s ease}
.info-row{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
.info-box{background:#fff;border-radius:12px;padding:18px 22px;box-shadow:0 1px 3px rgba(0,0,0,0.06)}
.info-box-title{font-size:15px;font-weight:700;display:flex;align-items:center;gap:6px;margin-bottom:10px}
.risk-box{background:#fef2f2;border-color:#fecaca}
.risk-box .info-box-title{color:#dc2626}
.highlight-box{background:#f0fdf4;border-color:#bbf7d0}
.highlight-box .info-box-title{color:#16a34a}
.info-list{padding-left:18px;font-size:13px;line-height:1.8;color:#374151}
.info-list li{margin-bottom:2px}
.chart-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin-bottom:20px}
.chart-card{background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.06)}
.chart-title{font-size:14px;font-weight:700;color:#374151;margin-bottom:14px;display:flex;align-items:center;gap:6px}
canvas{width:100%!important;max-height:320px}
.section{background:#fff;border-radius:12px;padding:22px;margin-bottom:32px;box-shadow:0 1px 3px rgba(0,0,0,0.06)}
.section-title{font-size:17px;font-weight:800;color:#111827;margin-bottom:14px;display:flex;align-items:center;gap:6px}
.story-stats{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px}
.sstat{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 24px;text-align:center;min-width:90px}
.sstat-val{font-size:26px;font-weight:800}
.sstat-lbl{font-size:11px;color:#6b7280;margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{background:#f1f5f9;color:#475569;padding:9px 12px;text-align:left;font-weight:600;font-size:11.5px;border-bottom:2px solid #e2e8f0;white-space:nowrap}
td{padding:9px 12px;border-bottom:1px solid #f1f5f9;white-space:nowrap}
tr:hover td{background:#f8fafc}
.tab-bar{display:flex;gap:0;background:#f1f5f9;border-radius:10px;padding:4px;margin-bottom:16px;overflow-x:auto}
.tab-btn{flex:1;padding:8px 14px;border:none;background:transparent;border-radius:8px;
    font-size:12.5px;font-weight:600;color:#64748b;cursor:pointer;transition:all .2s;text-align:center;white-space:nowrap}
.tab-btn.active{background:#fff;color:#2563eb;box-shadow:0 1px 3px rgba(0,0,0,0.1)}
.tab-btn:hover:not(.active){background:#e2e8f0}
.tab-content{display:none}.tab-content.active{display:block}
.sw{color:#ef4444;font-weight:700}.sd{color:#22c55e;font-weight:700}
.ss{color:#6b7280;font-weight:700}
.ot{color:#dc2626;font-weight:700;font-size:11px;background:#fef2f2;padding:1px 6px;border-radius:4px}
.story-detail-header{display:flex;align-items:center;padding:10px 16px;cursor:pointer;
    background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;margin:12px 0 8px;user-select:none;transition:background .15s}
.story-detail-header:hover{background:#f1f5f9}
.sd-arrow{font-size:12px;color:#9ca3af;margin-right:8px;transition:transform .25s;width:16px;text-align:center;display:inline-block}
.sd-arrow.expanded{transform:rotate(90deg)}
.story-detail-body{display:none;padding:0}
.story-detail-body.expanded{display:block}
.tn{color:#2563eb;font-weight:600;font-size:11.5px}
.p1{color:#ef4444}.p2{color:#f97316}.p3{color:#eab308}.p4{color:#6b7280}
.stat-row{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px}
.stat-item{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 18px;text-align:center;min-width:80px}
.stat-num{font-size:22px;font-weight:800}
.stat-label{font-size:11px;color:#6b7280;margin-top:2px}
.bug-tabs{display:flex;gap:12px;margin-bottom:14px}
.bug-tab{padding:8px 22px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;
    transition:all .2s;border:1px solid #e2e8f0;background:#f8fafc;color:#475569}
.bug-tab.active{background:#fef2f2;border-color:#fecaca;color:#dc2626}
.bug-tab.all-active{background:#f0f9ff;border-color:#bfdbfe;color:#0369a1}
.bug-open{background:#fef2f2 !important}
.dtbl th{font-size:11px}.dtbl td{font-size:11.5px}
.person-group{border:1px solid #e2e8f0;border-radius:10px;margin-bottom:12px;overflow:hidden;background:#fff;transition:box-shadow .2s}
.person-group:hover{box-shadow:0 2px 8px rgba(0,0,0,0.08)}
.person-header{display:flex;align-items:center;padding:14px 20px;cursor:pointer;
    background:#f8fafc;border-bottom:1px solid #e2e8f0;user-select:none;
    transition:background .15s;font-size:14px}
.person-header:hover{background:#f1f5f9}
.ph-arrow{font-size:12px;color:#9ca3af;margin-right:10px;transition:transform .25s;width:16px;text-align:center;display:inline-block}
.ph-arrow.expanded{transform:rotate(90deg)}
.ph-name{font-weight:700;font-size:15px;color:#111827;min-width:70px}
.ph-stats{margin-left:auto;display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:#6b7280}
.ph-stat-val{font-weight:700;margin-right:3px}
.ph-stat-wait{color:#ef4444}.ph-stat-doing{color:#22c55e}
.ph-stat-est{color:#6b7280}.ph-stat-con{color:#8b5cf6}.ph-stat-lft{color:#06b6d4}.ph-stat-od{color:#dc2626;font-weight:700;background:rgba(220,38,38,0.08);padding:2px 6px;border-radius:4px}
.person-tasks{display:none;padding:0}
.person-tasks.expanded{display:block}
.person-tasks table{border-radius:0;border-top:none;margin:0}
.footer{text-align:center;padding:20px;color:#9ca3af;font-size:11.5px}
@media(max-width:768px){
    .card-grid{grid-template-columns:repeat(2,1fr)}.chart-row,.info-row{grid-template-columns:1fr}
    .header h1{font-size:16px}
}'''

# ============================================================
# JS 模板
# ============================================================
JS_TEMPLATE = r'''
<script>
var ITER_DATA = {tasks: __TASKS_JSON__, stories: __STORIES_JSON__, bugs: __BUGS_JSON__};
var TODAY = "__TODAY__";

/* 阶段标签映射 */
var STAGE_LABELS = {
    "wait": "未开始",
    "projected": "已立项",
    "developing": "开发中",
    "developed": "开发完成",
    "testing": "测试中",
    "tested": "测试完成",
    "verified": "已验证",
    "released": "已发布",
    "closed": "已关闭",
    "unknown": "未知"
};

function switchTab(btn, cat){
    document.querySelectorAll(".tab-btn").forEach(function(b){ b.classList.remove("active"); });
    btn.classList.add("active");
    document.querySelectorAll(".tab-content").forEach(function(c){ c.classList.remove("active"); });
    var tc = document.getElementById("tab-" + cat);
    if(tc) tc.classList.add("active");
}

function showBugTab(type){
    if(type === "open"){
        document.getElementById("btOpen").className = "bug-tab active";
        document.getElementById("btAll").className = "bug-tab all-active";
        document.getElementById("bugOpenContent").style.display = "";
        document.getElementById("bugAllContent").style.display = "none";
    }else{
        document.getElementById("btOpen").className = "bug-tab";
        document.getElementById("btAll").className = "bug-tab active all-active";
        document.getElementById("bugOpenContent").style.display = "none";
        document.getElementById("bugAllContent").style.display = "";
    }
}

function togglePerson(pid){
    var arrow = document.getElementById(pid + "-arrow");
    var tasks = document.getElementById(pid + "-tasks");
    if(!arrow || !tasks) return;
    var isExpanded = tasks.classList.contains("expanded");
    if(isExpanded){
        tasks.classList.remove("expanded");
        arrow.classList.remove("expanded");
        tasks.style.display = "none";
    }else{
        tasks.classList.add("expanded");
        arrow.classList.add("expanded");
        tasks.style.display = "";
    }

function toggleStoryDetail(){
    var body = document.getElementById("storyDetailBody");
    var arrow = document.getElementById("sdArrow");
    if(!body || !arrow) return;
    var isExp = body.classList.contains("expanded");
    if(isExp){
        body.classList.remove("expanded");
        arrow.classList.remove("expanded");
        body.style.display = "none";
    } else {
        body.classList.add("expanded");
        arrow.classList.add("expanded");
        body.style.display = "block";
    }
}

/* ===== 图表1：需求阶段分布（横向柱状图） ===== */
(function(){
    var cv = document.getElementById("stageChart"); if(!cv) return;
    var ctx = cv.getContext("2d");
    var stages = {};
    ITER_DATA.stories.forEach(function(s){ 
        var st = s.stage || "unknown"; 
        stages[st] = (stages[st] || 0) + 1; 
    });
    var entries = Object.entries(stages).sort(function(a,b){ return b[1] - a[1]; });
    if(entries.length === 0) return;
    var clrs = ["#3b82f6","#8b5cf6","#ec4899","#f59e0b","#22c55e","#06b6d4","#6366f1","#14b8a6"];
    new Chart(cv, {
        type: "bar",
        data: {
            labels: entries.map(function(e){ return STAGE_LABELS[e[0]] || e[0]; }),
            datasets: [{
                label: "需求数",
                data: entries.map(function(e){ return e[1]; }),
                backgroundColor: clrs.slice(0, entries.length),
                borderRadius: 4,
                barThickness: 18
            }]
        },
        options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { beginAtZero: true, ticks: { stepSize: 1, font: { size: 12 } } },
                y: { ticks: { font: { size: 13 } } }
            }
        }
    });
})();

/* ===== 图表2：任务状态分布（横向柱状图） ===== */
(function(){
    var cv = document.getElementById("statusChart"); if(!cv) return;
    var ctx = cv.getContext("2d");
    var stats = {};
    ITER_DATA.tasks.forEach(function(t){ var s = t._st || "wait"; stats[s] = (stats[s] || 0) + 1; });
    var labels = {wait:"待处理",doing:"进行中",done:"已完成",pause:"暂停",cancel:"取消"};
    var entries = Object.entries(stats).map(function(kv){ return { l: labels[kv[0]] || kv[0], v: kv[1] }; });
    if(entries.length === 0) return;
    var colors = {"待处理":"#ef4444","进行中":"#22c55e","已完成":"#3b82f6","暂停":"#f59e0b","取消":"#6b7280"};
    new Chart(cv, {
        type: "bar",
        data: {
            labels: entries.map(function(e){ return e.l; }),
            datasets: [{
                label: "任务数",
                data: entries.map(function(e){ return e.v; }),
                backgroundColor: entries.map(function(e){ return colors[e.l] || "#94a3b8"; }),
                borderRadius: 4,
                barThickness: 20
            }]
        },
        options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { beginAtZero: true, ticks: { stepSize: 1, font: { size: 12 } } },
                y: { ticks: { font: { size: 13 } } }
            }
        }
    });
})();

/* ===== 图表3：任务类型分布（环形饼图） ===== */
(function(){
    var cv = document.getElementById("typeChart"); if(!cv) return;
    var dist = {};
    ITER_DATA.tasks.forEach(function(t){ var c = t._cat || "其他"; dist[c] = (dist[c] || 0) + 1; });
    var entries = Object.entries(dist).sort(function(a,b){ return b[1] - a[1]; });
    if(entries.length === 0) return;
    var clrs = ["#3b82f6","#22c55e","#f59e0b","#8b5cf6","#ec4899","#06b6d4","#6366f1","#14b8a6"];
    new Chart(cv, {
        type: "doughnut",
        data: {
            labels: entries.map(function(e){ return e[0]; }),
            datasets: [{
                data: entries.map(function(e){ return e[1]; }),
                backgroundColor: clrs.slice(0, entries.length),
                borderWidth: 2,
                borderColor: "#fff"
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "45%",
            plugins: {
                legend: { position: "bottom", labels: { font: { size: 12 }, padding: 16 } }
            }
        }
    });
})();
</script>
'''

# ============================================================
# 主函数：生成报告HTML
# ============================================================
def make_report_html(data, today, out_path):
    """生成迭代报告HTML：Tab按类切换 + 每类内按人可折叠展开任务清单"""
    exc     = data['exc']
    detail  = data['detail']
    tasks   = data['tasks']
    stories = data['stories']
    bugs    = data['bugs']
    eid     = exc['id']
    ename   = exc.get('name', '')
    pname   = exc.get('project_name', '')
    begin   = exc.get('begin', '') or detail.get('begin', '')
    end     = exc.get('end', '') or detail.get('end', '')
    status  = exc.get('status', '') or detail.get('status', '')
    progress = exc.get('progress', '0') or detail.get('progress', '0')

    time_pct, time_elapsed, time_total = calc_time_progress(begin, end, today)
    sys_pct = int(float(str(progress).replace('%',''))) if progress else 0

    # ---- 需求统计 ----
    story_by_status = {}
    for s in stories:
        st = s.get('status', 'unknown')
        story_by_status[st] = story_by_status.get(st, 0) + 1
    story_active  = story_by_status.get('active', 0) + story_by_status.get('developing', 0)
    story_closed  = story_by_status.get('closed', 0)
    story_changed = story_by_status.get('changed', 0)
    story_draft   = story_by_status.get('draft', 0)
    story_total   = len(stories)

    # ---- 任务统计 ----
    task_doing = sum(1 for t in tasks if t['_st'] == 'doing')
    task_wait  = sum(1 for t in tasks if t['_st'] == 'wait')
    task_done  = sum(1 for t in tasks if t['_st'] in ('done', 'closed'))
    task_total = len(tasks)
    task_completion = int(task_done / task_total * 100) if task_total > 0 else 0
    bug_open   = sum(1 for b in bugs if b.get('status') not in ('closed','resolved'))
    bug_closed = len(bugs) - bug_open
    overdue_tasks = [t for t in tasks if t.get('_dl') and t.get('_dl') < today and t['_st'] in ('wait','doing')]
    members = set(t['_rn'] for t in tasks if t['_rn'])
    member_count = len(members)

    # ---- 按分类统计任务 ----
    cat_stats = {c: [] for c in CATEGORIES}
    for t in tasks:
        c = t.get('_cat', '后端开发')
        if c in cat_stats:
            cat_stats[c].append(t)

    # ---- 需求明细表行 ----
    story_rows = ''
    for s in stories[:50]:
        sid = s.get('id', '-')
        spri = s.get('pri', '-') or '-'
        stitle = s.get('title', '-') or '-'
        sstatus = s.get('status', '-') or '-'
        sstage_raw = s.get("stage", "-") or "-"
        sstage = STAGE_LABEL_ZH.get(sstage_raw, sstage_raw) if sstage_raw != "-" else "-"
        openedBy = s.get('openedBy', '')
        if isinstance(openedBy, dict):
            openedBy = openedBy.get('realname', openedBy.get('account', '-'))
        elif not isinstance(openedBy, str):
            openedBy = str(openedBy)
        if not openedBy or openedBy == 'None':
            openedBy = '-'
        linked_count = sum(1 for t in tasks if str(t.get('story')) == str(sid))
        pri_color_map = {'1': '#ef4444', '2': '#f97316', '3': '#eab308', '4': '#6b7280'}
        spri_color = pri_color_map.get(str(spri), '#6b7280')
        stitle_escaped = stitle.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
        story_rows += ('<tr><td>%s</td><td><span style="color:%s;font-weight:600">P%s</span></td>'
            '<td style="text-align:left;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="%s">%s <span style="color:#3b82f6;font-size:11px;margin-left:4px">%d个任务</span></td>'
            '<td>%s</td><td>%s</td><td style="color:#6b7280">%s</td></tr>') % (
            sid, spri_color, spri, stitle_escaped, stitle, linked_count, sstatus, sstage, openedBy)

    # ---- 风险预警 & 进展亮点 ----
    risk_items = []
    if overdue_tasks:
        risk_items.append('延期任务 %d 个，需重点跟进' % len(overdue_tasks))
        for ot in overdue_tasks[:3]:
            risk_items.append('- %s (#%s)' % (ot.get('name', ''), ot.get('id', '')))
    if task_completion < 50 and time_pct > 70:
        risk_items.append('时间进度 %d%% 但完成率仅 %d%%，进度严重滞后' % (time_pct, task_completion))
    if not risk_items:
        risk_items.append('当前无明显风险')

    highlight_items = []
    highlight_items.append('已完成/已关闭任务 %d 个（%d%%）' % (task_done, task_completion))
    if task_doing > 0:
        highlight_items.append('进行中任务 %d 个，团队在推进' % task_doing)
    highlight_items.append('需求规模适中（%d个），便于管理' % story_total)
    if member_count > 0:
        highlight_items.append('%d 位成员参与协作' % member_count)

    risk_html = '\n'.join('<li>%s</li>' % r for r in risk_items)
    highlight_html = '\n'.join('<li>%s</li>' % h for h in highlight_items)

    # ---- Bug 表格 ----
    bug_open_rows = ''
    open_bugs = [b for b in bugs if b.get('status') not in ('closed','resolved')]
    for b in open_bugs:
        bug_open_rows += '<tr><td>#%s</td><td style="text-align:left">%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
            b.get('id','-'), b.get('title','-'), b.get('severity','-'),
            b.get('status','-'), b.get('openedBy','-'))
    bug_all_rows = ''
    for b in bugs[:30]:
        bs = b.get('status','')
        row_cls = 'bug-open' if bs not in ('closed','resolved') else ''
        bug_all_rows += '<tr class="%s"><td>#%s</td><td style="text-align:left">%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
            row_cls, b.get('id','-'), b.get('title','-'), b.get('severity','-'),
            bs, b.get('openedBy','-'))

    if bug_open_rows:
        bug_open_content = ('<table><thead><tr><th>ID</th><th>标题</th><th>严重程度</th><th>状态</th><th>创建人</th></tr></thead>'
            '<tbody>%s</tbody></table>') % bug_open_rows
    else:
        bug_open_content = '<div style="text-align:center;color:#22c55e;padding:20px;font-size:14px">✅ 无未关闭 Bug</div>'
    bug_all_content = ('<table><thead><tr><th>ID</th><th>标题</th><th>严重程度</th><th>状态</th><th>创建人</th></tr></thead>'
        '<tbody>%s</tbody></table>') % bug_all_rows if bug_all_rows else ''

    # ---- 数据JSON ----
    tasks_json   = json.dumps(tasks, ensure_ascii=False)
    stories_json = json.dumps(stories, ensure_ascii=False)
    bugs_json    = json.dumps(bugs, ensure_ascii=False)

    # ================================================================
    # 构建 Tab内容：每个分类 -> 统计卡片 + 按人可折叠面板
    # ================================================================
    btn_info = {}
    tab_content_html = ''
    for cat in CATEGORIES:
        ct = cat_stats[cat]
        btn_info[cat] = {
            'members': len(set(t['_rn'] for t in ct if t['_rn'])),
            'count': len(ct)
        }
        icon = CAT_ICONS.get(cat, '📋')
        c_wait = sum(1 for t in ct if t['_st'] == 'wait')
        c_doing = sum(1 for t in ct if t['_st'] == 'doing')
        c_overdue = sum(1 for t in ct if t.get('_dl') and t.get('_dl') < today and t['_st'] in ('wait','doing'))
        c_est = sum(t.get('estimate', 0) or 0 for t in ct)
        c_con = sum(t.get('consumed', 0) or 0 for t in ct)
        c_lft = sum(t.get('left', 0) or 0 for t in ct)

        # 该分类下按人分组
        tasks_by_person = {}
        for t in ct:
            rn = t.get('_rn', '') or '未分配'
            if rn not in tasks_by_person:
                tasks_by_person[rn] = []
            tasks_by_person[rn].append(t)
        sorted_persons = sorted(tasks_by_person.items(), key=lambda x: len(x[1]), reverse=True)

        # Tab content 开始
        active_cls = ' active' if cat == CATEGORIES[0] else ''
        tab_content_html += ('<div class="tab-content' + active_cls + '" id="tab-%s">'
            '<div class="stat-row">'
            '<div class="stat-item"><div class="stat-num sw">%s</div><div class="stat-label">待处理</div></div>'
            '<div class="stat-item"><div class="stat-num sd">%s</div><div class="stat-label">进行中</div></div>'
            '<div class="stat-item"><div class="stat-num ss">%s</div><div class="stat-label">延期</div></div>'
            '<div class="stat-item"><div class="stat-num" style="color:#6b7280">%sh</div><div class="stat-label">预估工时</div></div>'
            '<div class="stat-item"><div class="stat-num" style="color:#8b5cf6">%sh</div><div class="stat-label">已耗工时</div></div>'
            '<div class="stat-item"><div class="stat-num" style="color:#06b6d4">%sh</div><div class="stat-label">剩余工时</div></div>'
            '</div>') % (cat, c_wait, c_doing, c_overdue, c_est, c_con, c_lft)

        # 按人折叠面板
        if sorted_persons:
            for pidx, (pname, ptasks) in enumerate(sorted_persons):
                pid = cat + '-p' + str(pidx)
                p_wait = sum(1 for t in ptasks if t['_st'] == 'wait')
                p_doing = sum(1 for t in ptasks if t['_st'] == 'doing')
                p_total = len(ptasks)
                p_est = sum(t.get('estimate', 0) or 0 for t in ptasks)
                p_con = sum(t.get('consumed', 0) or 0 for t in ptasks)
                p_lft = sum(t.get('left', 0) or 0 for t in ptasks)
                p_overdue = sum(1 for t in ptasks if t.get("_dl") and t["_dl"] < today and t["_st"] in ("wait", "doing"))

                task_rows = ''
                for t in ptasks:
                    cls = 'sw' if t['_st'] == 'wait' else 'sd' if t['_st'] == 'doing' else 'ss'
                    pcl = 'p' + str(t.get('pri') or '3')
                    dl = t.get('_dl') or '-'
                    dl_cell = '<td>%s</td>' % dl
                    if dl != '-' and dl < today and t['_st'] in ('wait','doing'):
                        dl_cell = '<td><span class="ot">%s</span></td>' % dl
                    tn = (t.get('name','')).replace('"','&quot;').replace('<','&lt;').replace('>','&gt;')
                    task_rows += ('<tr><td class="tn">%s</td>'
                        '<td style="text-align:left;max-width:360px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="%s">%s</td>'
                        '<td class="%s">%s</td><td class="%s">%s</td>%s<td>%s</td><td>%s</td><td>%s</td></tr>') % (
                        t.get('id','-'), tn, t.get('name','-'),
                        cls, g_status(t['_st']), pcl, g_pri(t.get('pri')),
                        dl_cell, t.get('estimate',0), t.get('consumed',0), t.get('left',0))

                expand_mark = ''
                display_style = 'display:none'

                od_span = ('<span class="ph-stat-od">延期<span class="ph-stat-val">' + str(p_overdue) + '</span></span>') if p_overdue > 0 else ''
                tab_content_html += (
                    '<div class="person-group">'
                    '<div class="person-header" onclick="togglePerson(\'' + pid + '\')">'
                    '<span class="ph-arrow' + expand_mark + '" id="' + pid + '-arrow">&#9654;</span>'
                    '<span class="ph-name">' + pname + '</span>'
                    '<div class="ph-stats">'
                    '<span>共<span class="ph-stat-val">' + str(p_total) + '</span>个</span>'
                    '<span class="ph-stat-wait">待处理<span class="ph-stat-val">' + str(p_wait) + '</span></span>'
                    '<span class="ph-stat-doing">进行中<span class="ph-stat-val">' + str(p_doing) + '</span></span>'
                    + od_span +
                    '<span class="ph-stat-est">预估<span class="ph-stat-val">' + str(p_est) + 'h</span></span>'
                    '<span class="ph-stat-con">消耗<span class="ph-stat-val">' + str(p_con) + 'h</span></span>'
                    '<span class="ph-stat-lft">剩余<span class="ph-stat-val">' + str(p_lft) + 'h</span></span>'
                    '</div></div>'
                    '<div class="person-tasks' + expand_mark + '" id="' + pid + '-tasks" style="' + display_style + '">'
                    '<table class="dtbl"><thead><tr><th>ID</th><th>任务名称</th><th>状态</th><th>优先级</th>'
                    '<th>截止日期</th><th>预估(h)</th><th>消耗(h)</th><th>剩余(h)</th></tr></thead>'
                    '<tbody>' + task_rows + '</tbody></table></div></div>')
        else:
            tab_content_html += '<div style="text-align:center;color:#9ca3af;padding:30px;font-size:14px">该分类暂无任务数据</div>'

        tab_content_html += '</div>'  # close tab-content

    # ---- Tab按钮栏 ----
    tab_btns = ''
    for cat in CATEGORIES:
        bi = btn_info[cat]
        icon = CAT_ICONS.get(cat, '📋')
        active_mark = ' active' if cat == '产品' else ''
        tab_btns += ('<button class="tab-btn%s" onclick="switchTab(this,\'%s\')">%s %s(%s人/%s条)</button>') % (
            active_mark, cat, icon, cat+'任务', bi['members'], bi['count'])

    # ================================================================
    # 组装完整 HTML
    # ================================================================
    parts = []

    # 1. CSS + Head
    parts.append(CSS_TEMPLATE)

    # 2. Body开始
    parts.append('</style>')
    parts.append('<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>')
    parts.append('</head>')
    parts.append('<body>')


    # 3. Header
    parts.append(('<div class="header"><div class="header-icon">&#128202;</div>'
        '<h1>%s 【2026】执行进展分析报告</h1>'
        '<div class="sub">执行ID: %s | %s ~ %s | 生成时间: %s | %s</div>'
        '<a class="home-btn" href="../index.html">&#127968; 返回首页</a>'
        '<a class="refresh-btn" href="#">&#128260; 实时刷新禅道数据</a></div>') % (
        ename, eid, begin, end, today, pname))

    # 4. 统计卡片
    parts.append('<div class="card-grid">')
    parts.append(('<div class="stat-card"><div class="sc-icon">&#9201;</div>'
        '<div class="sc-label">时间进度</div>'
        '<div class="sc-value" style="color:#2563eb">%s%%</div>'
        '<div class="progress-bar"><div class="progress-fill" style="width:%s%%;background:linear-gradient(90deg,#2563eb,#60a5fa)"></div></div>'
        '<div class="sc-sub">已过 %s/%s 天</div></div>') % (time_pct, time_pct, time_elapsed, time_total))
    parts.append(('<div class="stat-card"><div class="sc-icon">&#128640;</div>'
        '<div class="sc-label">系统进度</div>'
        '<div class="sc-value" style="color:#f59e0b">%s%%</div>'
        '<div class="progress-bar"><div class="progress-fill" style="width:%s%%;background:linear-gradient(90deg,#f59e0b,#fbbf24)"></div></div>'
        '<div class="sc-sub">状态: %s</div></div>') % (sys_pct, sys_pct, status))
    parts.append(('<div class="stat-card"><div class="sc-icon">&#128203;</div>'
        '<div class="sc-label">需求总数</div>'
        '<div class="sc-value" style="color:#8b5cf6">%s</div>'
        '<div class="sc-sub">active: %s | closed: %s</div></div>') % (story_total, story_active, story_closed))
    parts.append(('<div class="stat-card"><div class="sc-icon">&#128736;</div>'
        '<div class="sc-label">任务总数</div>'
        '<div class="sc-value" style="color:#3b82f6">%s</div>'
        '<div class="sc-sub">进行中: %s | 待处理: %s | <span style="color:#ef4444;font-weight:700">延期: %s</span></div></div>') % (task_total, task_doing, task_wait, len(overdue_tasks)))
    parts.append(('<div class="stat-card"><div class="sc-icon">&#128026;</div>'
        '<div class="sc-label">Bug总数</div>'
        '<div class="sc-value" style="color:#ef4444">%s</div>'
        '<div class="sc-sub">未关闭: %s | 已关/已延: %s</div></div>') % (len(bugs), bug_open, bug_closed))
    parts.append('</div>')

    # 5. 风险/亮点
    parts.append('<div class="info-row">')
    parts.append(('<div class="info-box risk-box"><div class="info-box-title">&#9888;&#65039; 风险预警</div>'
        '<ul class="info-list">%s</ul></div>') % risk_html)
    parts.append(('<div class="info-box highlight-box"><div class="info-box-title">&#9989; 进展亮点</div>'
        '<ul class="info-list">%s</ul></div>') % highlight_html)
    parts.append('</div>')

    # 6. 图表区域
    parts.append(('<div class="chart-row"><div class="chart-card"><div class="chart-title">&#128202; 需求阶段分布</div>'
        '<canvas id="stageChart"></canvas></div>'
        '<div class="chart-card"><div class="chart-title">&#128202; 任务状态分布</div>'
        '<canvas id="statusChart"></canvas></div>'
        '<div class="chart-card"><div class="chart-title">&#128202; 任务类型分布</div>'
        '<canvas id="typeChart"></canvas></div></div>'))

    # 7. 需求分析（统计卡片 + 可展开明细，同一个 section）
    parts.append(('<div class="section"><div class="section-title">&#128203; 需求分析（%s 个）</div>'
        '<div class="story-stats">'
        '<div class="sstat"><div class="sstat-val" style="color:#3b82f6">%s</div><div class="sstat-lbl">active</div></div>'
        '<div class="sstat"><div class="sstat-val" style="color:#22c55e">%s</div><div class="sstat-lbl">closed</div></div>'
        '<div class="sstat"><div class="sstat-val" style="color:#f59e0b">%s</div><div class="sstat-lbl">changed</div></div>'
        '<div class="sstat"><div class="sstat-val" style="color:#6b7280">%s</div><div class="sstat-lbl">draft</div></div>'
        '</div>'
        '<div class="story-detail-header" onclick="toggleStoryDetail()">'
        '<span class="sd-arrow" id="sdArrow">&#9654;</span>需求明细（共 %s 个，点击展开）</div>'
        '<div class="story-detail-body" id="storyDetailBody">'
        '<table><thead><tr><th>ID</th><th>优先级</th><th>标题</th><th>状态</th><th>阶段</th><th>创建人</th></tr></thead>'
        '<tbody>%s</tbody></table></div></div>') % (
        story_total, story_active, story_closed, story_changed, story_draft, story_total, story_rows))

    # 8. 任务分析明细（Tab切换 + 按人折叠）
    parts.append(('<div class="section"><div class="section-title">&#128722; 任务分析明细（%s 人活跃 / 按5类分组）</div>'
        '<div class="tab-bar">%s</div>%s</div>') % (member_count, tab_btns, tab_content_html))

    # 9. Bug 分析
    parts.append('<div class="section"><div class="section-title">&#128026; Bug 分析（' + str(len(bugs)) + ' 个）</div>')
    parts.append('<div class="bug-tabs">')
    parts.append('<div class="bug-tab active" id="btOpen" onclick="showBugTab(\'open\')">&#128308; 未关闭 Bug (' + str(bug_open) + ')</div>')
    parts.append('<div class="bug-tab all-active" id="btAll" onclick="showBugTab(\'all\')">&#128203; 全部 Bug (' + str(len(bugs)) + ')</div></div>')
    parts.append('<div id="bugOpenContent">' + bug_open_content + '</div>')
    parts.append('<div id="bugAllContent" style="display:none">' + bug_all_content + '</div></div>')

    # 10. 底部
    parts.append(('<div class="footer">禅道任务报告中心 · 自动生成于 %s · %s</div>') % (today, pname))

    # 11. JavaScript
    js = JS_TEMPLATE.replace('__TASKS_JSON__', tasks_json).replace(
        '__STORIES_JSON__', stories_json).replace('__BUGS_JSON__', bugs_json).replace('__TODAY__', today)
    parts.append(js)

    # 12. 结束标签
    parts.append('\n</body>\n</html>')

    full_html = ''.join(parts)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(full_html, encoding='utf-8')
    return len(full_html)


def main():
    print('=' * 55)
    print('迭代执行进展报告生成器')
    print('=' * 55)

    client = ZentaoClient(CONFIG_FILE)
    print('已连接禅道 API')

    all_excs = []
    for pid in PROJECT_IDS:
        pname = PROJECT_NAMES[pid]
        page = 1
        while True:
            res = client.get('/projects/%d/executions' % pid, {'page': page, 'limit': 100})
            es = res.get('executions', [])
            if not es: break
            for e in es:
                e['project_id'] = pid
                e['project_name'] = pname
                all_excs.append(e)
            if len(es) < 100: break
            page += 1

    print('共 %d 个迭代' % len(all_excs))

    today = datetime.now().strftime('%Y-%m-%d')
    output_dir = OUTPUT_DIR / today
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    for exc in all_excs:
        status = exc.get('status', '')
        if status not in ('doing', 'undone'):
            continue

        eid = exc['id']
        ename = exc.get('name', '')
        print('\n生成报告: [%s] %s ...' % (eid, ename))

        data = fetch_iteration_data(client, exc)
        fname = '迭代%d_执行进展报告.html' % eid
        fpath = output_dir / fname
        nbytes = make_report_html(data, today, fpath)
        print('  -> %s (%d KB)' % (fname, nbytes // 1024))
        generated.append(fname)

    print('\n' + '=' * 55)
    print('完成！共生成 %d 个迭代报告:' % len(generated))
    for f in generated:
        print('  %s/%s' % (today, f))
    print('目录: %s' % output_dir)
    print('=' * 55)


if __name__ == '__main__':
    main()
