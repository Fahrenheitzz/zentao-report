#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 index.html v8 — 优化配色和样式
设计语言：
  背景：#0a0e27 → #131736 → #0d1117（类 GitHub Dark 专业感）
  主色：#7c5cfc（紫蓝） #44e5ff（青蓝）
  文字：#e2e8f0（主） #94a3b8（次） #64748b（辅）
  危险：#f97066  成功：#34d399  警告：#fbbf24
"""
import json, hashlib, urllib.request, ssl
from datetime import datetime
from pathlib import Path

SCRIPT_DIR  = Path(__file__).parent
CONFIG_FILE = str(SCRIPT_DIR / 'zentao_config.json')
OUTPUT_DIR  = SCRIPT_DIR
PROJECT_IDS = [1013, 4047]
PROJECT_NAMES = {1013: '商城3.0', 4047: '格力官网'}

# ── 禅道客户端 ─────────────────────────────────────────────────────────────
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
            print('  [错误] GET %s → %s' % (path, e))
            return {}

# ── 获取数据 ─────────────────────────────────────────────────────────────────
def fetch_rich_executions(client):
    all_tasks = []
    all_excs  = []

    for pid in PROJECT_IDS:
        pname = PROJECT_NAMES[pid]
        page = 1
        while True:
            res = client.get('/projects/%d/executions' % pid, {'page': page, 'limit': 100})
            es  = res.get('executions', [])
            if not es:
                break
            for e in es:
                e['project_id']   = pid
                e['project_name']  = pname
                e['_stats'] = {'task_count': 0, 'done_count': 0,
                                'story_count': 0, 'bug_count': 0, 'completion_pct': 0}
                all_excs.append(e)
            if len(es) < 100:
                break
            page += 1

    print('  共 %d 个迭代，开始获取 stats...' % len(all_excs))
    seen_task_ids = set()

    for e in all_excs:
        eid = e['id']
        t_cnt = 0
        d_cnt = 0
        page  = 1
        while True:
            res = client.get('/executions/%d/tasks' % eid, {'page': page, 'limit': 100})
            ts  = res.get('tasks', [])
            if not ts:
                break
            for t in ts:
                tid = t.get('id')
                if tid and tid not in seen_task_ids:
                    seen_task_ids.add(tid)
                    t['_pid']    = e['project_id']
                    t['_pname']  = e['project_name']
                    t['_st']     = t.get('status', 'wait')
                    t['_rn']     = t.get('realname', '') or t.get('assignedTo', '')
                    t['_dl']     = t.get('deadline', '') or ''
                    all_tasks.append(t)
                if t.get('status') in ('done', 'closed'):
                    d_cnt += 1
                t_cnt += 1
            if len(ts) < 100:
                break
            page += 1

        stories = client.get('/executions/%d/stories' % eid).get('stories', [])
        bugs    = client.get('/executions/%d/bugs' % eid).get('bugs', [])
        pct = int(d_cnt / t_cnt * 100) if t_cnt > 0 else 0
        e['_stats'] = {
            'task_count':     t_cnt,
            'done_count':     d_cnt,
            'story_count':    len(stories),
            'bug_count':      len(bugs),
            'completion_pct': pct,
        }

    return all_tasks, all_excs

# ── 生成 HTML ───────────────────────────────────────────────────────────────
def make_html(all_tasks, all_excs, today):
    for t in all_tasks:
        for k in ('_pid', '_pname', '_st', '_rn', '_dl'):
            t.setdefault(k, '')
    for e in all_excs:
        e.setdefault('_stats', {})

    all_tasks_js  = json.dumps(all_tasks, ensure_ascii=False)
    all_excs_js  = json.dumps(all_excs,  ensure_ascii=False)
    project_tasks = {}
    for pid in PROJECT_IDS:
        project_tasks[str(pid)] = [t for t in all_tasks if t.get('_pid') == pid]
    project_tasks_js  = json.dumps(project_tasks, ensure_ascii=False)
    project_names_js = json.dumps(PROJECT_NAMES, ensure_ascii=False)

    # ── CSS（v8 配色）────────────────────────────────────────────────────
    # 设计语言：
    #   背景：#0a0e27 → #131736 → #0d1117
    #   主色：#7c5cfc（紫蓝）  #44e5ff（青蓝）
    #   文字：#e2e8f0（主） #94a3b8（次） #64748b（辅）
    #   危险：#f97066  成功：#34d399  警告：#fbbf24
    css = (
        '*{margin:0;padding:0;box-sizing:border-box}'
        'body{'
            'font-family:-apple-system,BlinkMacSystemFont,"Microsoft YaHei","PingFang SC",sans-serif;'
            'background:linear-gradient(160deg,#0a0e27 0%,#131736 40%,#0d1117 100%);'
            'min-height:100vh;padding:28px 24px 60px;color:#e2e8f0;'
            'background-attachment:fixed'
        '}'
        # 顶部容器
        '.ct{max-width:1280px;margin:0 auto}'
        '.hd{text-align:center;margin-bottom:10px}'
        '.hd .logo{font-size:38px;display:block;margin-bottom:4px;'
            'filter:drop-shadow(0 0 12px rgba(124,92,252,.4))}'
        '.hd h1{font-size:28px;font-weight:800;letter-spacing:1px;'
            'background:linear-gradient(135deg,#7c5cfc,#44e5ff,#a78bfa);'
            '-webkit-background-clip:text;-webkit-text-fill-color:transparent;'
            'background-clip:text}'
        '.hd .sub{color:#64748b;font-size:13px;letter-spacing:2px;margin-top:4px}'
        # 更新时间
        '.dt{text-align:center;margin:16px 0 22px;font-size:12px}'
        '.dt span{display:inline-block;padding:5px 18px;border-radius:20px;'
            'background:rgba(124,92,252,.08);border:1px solid rgba(124,92,252,.2);'
            'color:#a78bfa;font-size:12px}'
        # 项目筛选
        '.fb{display:flex;justify-content:center;gap:8px;margin-bottom:24px;flex-wrap:wrap}'
        '.fn{padding:7px 22px;border-radius:20px;font-size:13px;font-weight:600;'
            'border:1px solid rgba(255,255,255,.08);background:rgba(22,27,51,.6);'
            'color:#64748b;cursor:pointer;transition:all .3s;letter-spacing:.3px}'
        '.fn:hover{background:rgba(124,92,252,.1);border-color:rgba(124,92,252,.3);'
            'color:#a78bfa}'
        '.fn.active{background:linear-gradient(135deg,rgba(124,92,252,.25),rgba(68,229,255,.15));'
            'border-color:rgba(124,92,252,.5);color:#fff;'
            'box-shadow:0 0 16px rgba(124,92,252,.2)}'
        # 分区标题
        '.stit{font-size:13px;font-weight:700;color:#64748b;margin:28px 0 14px;'
            'text-align:center;letter-spacing:3px}'
        # 分类卡片网格
        '.gd{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));'
            'gap:14px;margin-bottom:4px}'
        # 分类卡片
        '.cd{position:relative;display:flex;flex-direction:column;align-items:center;'
            'padding:26px 16px 20px;border-radius:18px;'
            'background:rgba(22,27,51,.7);'
            'border:1px solid rgba(255,255,255,.06);'
            'cursor:pointer;transition:all .35s;overflow:hidden;'
            'text-decoration:none;color:inherit;backdrop-filter:blur(6px)}'
        '.cd::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;'
            'background:linear-gradient(90deg,transparent,#7c5cfc,transparent);'
            'opacity:0;transition:opacity .35s}'
        '.cd:hover{transform:translateY(-5px);'
            'border-color:rgba(124,92,252,.25);'
            'box-shadow:0 16px 40px rgba(0,0,0,.35),0 0 0 1px rgba(124,92,252,.1);'
            'background:rgba(28,33,62,.85)}'
        '.cd:hover::before{opacity:1}'
        '.ci{font-size:36px;margin-bottom:10px;'
            'filter:drop-shadow(0 2px 6px rgba(0,0,0,.3))}'
        '.cn{font-size:13px;font-weight:600;color:#94a3b8;margin-bottom:6px;'
            'letter-spacing:.5px}'
        '.cnu{font-size:32px;font-weight:900;margin-bottom:4px;'
            'text-shadow:0 2px 8px rgba(0,0,0,.3)}'
        '.cdsc{font-size:12px;color:#64748b;text-align:center;line-height:1.6}'
        '.cw{color:#f97066;font-weight:700}'
        '.cdg{color:#34d399;font-weight:700}'
        '.cm{color:#7c5cfc;font-weight:700}'
        '.cpj{margin-top:8px;font-size:11px;color:#475569;line-height:1.5}'
        # 洞察卡片网格
        '.ig{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));'
            'gap:14px;margin-top:20px}'
        # 洞察卡片
        '.icd{display:flex;align-items:center;gap:18px;'
            'padding:20px 22px;border-radius:18px;'
            'background:rgba(22,27,51,.7);'
            'border:1px solid rgba(255,255,255,.06);'
            'cursor:pointer;transition:all .35s;color:inherit;'
            'text-decoration:none;backdrop-filter:blur(6px)}'
        '.icd:hover{transform:translateY(-4px);'
            'border-color:rgba(255,255,255,.12);'
            'box-shadow:0 12px 32px rgba(0,0,0,.3)}'
        '.ici{font-size:38px;min-width:50px;text-align:center;'
            'filter:drop-shadow(0 2px 6px rgba(0,0,0,.3))}'
        '.icbdy{flex:1}'
        '.ict{font-size:15px;font-weight:700;margin-bottom:5px}'
        '.icsu{font-size:12px;color:#64748b;line-height:1.5}'
        '.iov .ict{color:#f97066}'
        '.iwl .ict{color:#fbbf24}'
        # 迭代总览区域
        '.ov-section{margin-top:40px;padding-top:8px}'
        '.ov-header{display:flex;align-items:center;justify-content:space-between;'
            'margin-bottom:16px;flex-wrap:wrap;gap:10px}'
        '.ov-title{font-size:20px;font-weight:800;letter-spacing:.5px;'
            'background:linear-gradient(135deg,#7c5cfc,#44e5ff);'
            '-webkit-background-clip:text;-webkit-text-fill-color:transparent;'
            'background-clip:text}'
        # 汇总统计
        '.ov-sum{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:20px}'
        '.ov-sm{background:rgba(22,27,51,.6);border-radius:14px;'
            'padding:14px 24px;text-align:center;'
            'border:1px solid rgba(255,255,255,.06);'
            'min-width:110px;transition:all .3s}'
        '.ov-sm:hover{border-color:rgba(124,92,252,.2);'
            'box-shadow:0 4px 16px rgba(0,0,0,.2)}'
        '.ov-sn{font-size:26px;font-weight:900;'
            'text-shadow:0 2px 6px rgba(0,0,0,.3)}'
        '.ov-sl{font-size:11px;color:#64748b;margin-top:3px;letter-spacing:.5px}'
        # 项目分组标题
        '.ov-ptl{font-size:14px;font-weight:700;color:#94a3b8;'
            'margin:20px 0 10px;'
            'border-left:3px solid #7c5cfc;padding-left:12px}'
        # 表格
        '.ov-tbl{width:100%;border-collapse:separate;border-spacing:0 4px;'
            'font-size:13px;margin-top:2px}'
        '.ov-tbl thead{position:sticky;top:0}'
        '.ov-tbl th{background:rgba(124,92,252,.1);color:#94a3b8;'
            'padding:10px 14px;text-align:left;font-weight:700;font-size:11px;'
            'letter-spacing:.5px;'
            'border-bottom:2px solid rgba(124,92,252,.15)}'
        '.ov-tbl td{padding:11px 14px;'
            'border-bottom:1px solid rgba(255,255,255,.04);'
            'transition:background .2s}'
        '.ov-tbl tbody tr{transition:all .25s}'
        '.ov-tbl tbody tr:hover td{'
            'background:rgba(124,92,252,.06);'
            'box-shadow:inset 0 0 0 1px rgba(124,92,252,.1)}'
        '.ov-eid{color:#7c5cfc;text-decoration:none;font-weight:700;font-size:13px;'
            'transition:color .2s}'
        '.ov-eid:hover{color:#44e5ff}'
        '.ov-prg{display:inline-block;width:80px;height:8px;'
            'background:rgba(255,255,255,.06);border-radius:5px;'
            'overflow:hidden;vertical-align:middle;margin-right:8px}'
        '.ov-prgf{height:100%;border-radius:5px;transition:width .6s ease}'
        '.ov-pct{font-size:12px;color:#64748b;font-weight:600}'
        '.ov-vl{color:#7c5cfc;font-size:12px;text-decoration:none;font-weight:600;'
            'transition:color .2s}'
        '.ov-vl:hover{color:#44e5ff}'
        # 页脚
        '.ft{text-align:center;margin-top:48px;padding-top:20px;'
            'border-top:1px solid rgba(255,255,255,.04);'
            'color:#4a5568;font-size:11px;letter-spacing:1px}'
    )

    # ── HTML 骨架 ────────────────────────────────────────────────────────
    parts = []
    parts.append('<!DOCTYPE html>')
    parts.append('<html lang="zh-CN"><head><meta charset="UTF-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    parts.append('<title>禅道任务报告中心</title>')
    parts.append('<style>' + css + '</style></head><body>')
    parts.append('<div class="ct">')

    # 头部
    parts.append('<div class="hd">')
    parts.append('<span class="logo">📊</span>')
    parts.append('<h1>禅道任务报告中心</h1>')
    parts.append('<p class="sub">Zentao Task Dashboard</p>')
    parts.append('</div>')
    parts.append('<div class="dt"><span>%s 更新</span></div>' % today)

    # 筛选按钮
    parts.append('<div class="fb">')
    parts.append('<button class="fn active" data-f="all" onclick="setFilter(\'all\')">全部项目</button>')
    parts.append('<button class="fn" data-f="1013" onclick="setFilter(\'1013\')">商城3.0</button>')
    parts.append('<button class="fn" data-f="4047" onclick="setFilter(\'4047\')">格力官网</button>')
    parts.append('</div>')

    # 分类卡片容器
    parts.append('<div id="cg" class="gd"></div>')

    # 数据洞察
    parts.append('<div class="stit">— 数据洞察 —</div>')
    parts.append('<div class="ig">')
    # 延期任务卡片
    parts.append('<a class="icd iov" id="odLink" href="#">')
    parts.append('<div class="ici">🚨</div>')
    parts.append('<div class="icbdy">')
    parts.append('<div class="ict">延期任务</div>')
    parts.append('<div class="icsu" id="odInfo">-- 个延期 / -- 人</div>')
    parts.append('</div></a>')
    # 员工负载卡片
    parts.append('<a class="icd iwl" id="wlLink" href="#">')
    parts.append('<div class="ici">💪</div>')
    parts.append('<div class="icbdy">')
    parts.append('<div class="ict">员工负载</div>')
    parts.append('<div class="icsu" id="wlInfo">按角色分工时分析</div>')
    parts.append('</div></a>')
    parts.append('</div>')

    # 迭代执行进展总览（嵌入）
    parts.append('<div class="ov-section">')
    parts.append('<div class="ov-header">')
    parts.append('<div class="ov-title">📊 迭代执行进展总览</div>')
    parts.append('</div>')
    parts.append('<div id="ovBody"></div>')
    parts.append('</div>')

    # 页脚
    parts.append('<div class="ft">商城3.0 + 格力官网 · 禅道任务报告中心</div>')
    parts.append('</div>')

    # 嵌入数据
    parts.append('<script>')
    parts.append('window.ALL_TASKS = ' + all_tasks_js + ';')
    parts.append('window.ALL_EXECS = ' + all_excs_js + ';')
    parts.append('window.PROJECT_TASKS = ' + project_tasks_js + ';')
    parts.append('window.PROJECT_NAMES = ' + project_names_js + ';')
    parts.append('</script>')

    # JS 逻辑
    parts.append('<script>')
    parts.append(JS_LOGIC.replace('__TODAY__', today))
    parts.append('</script>')

    parts.append('</body></html>')
    return '\n'.join(parts)

# ── JS 逻辑 ───────────────────────────────────────────────────────────────
JS_LOGIC = r"""
var CATS=["产品","后端开发","前端开发","移动端开发","测试"];
var ICONS={"产品":"📋","后端开发":"⚙️","前端开发":"🌸","移动端开发":"📱","测试":"🔬"};
var COLORS={"产品":"#a78bfa","后端开发":"#34d399","前端开发":"#f093fb","移动端开发":"#ffa726","测试":"#22d3ee"};
var TODAY="__TODAY__";
var curF="all";

function getTasks(){
    return curF==="all"?window.ALL_TASKS:(window.PROJECT_TASKS[curF]||[]);
}
function getExecs(){
    if(curF==="all") return window.ALL_EXECS;
    return window.ALL_EXECS.filter(function(e){return String(e.project_id)===curF});
}
function doClassify(ts){
    var c={}; CATS.forEach(function(k){c[k]=[];});
    ts.forEach(function(t){
        var tp=(t.type||"").toLowerCase();
        if(tp.indexOf("ab")===0) c["产品"].push(t);
        else if(tp.indexOf("a_dev")===0 && tp.indexOf("front")===-1) c["后端开发"].push(t);
        else if(tp.indexOf("front")!==-1 || tp.indexOf("a_dev2_front")===0) c["前端开发"].push(t);
        else if(["ios","android","mobile","app"].some(function(k){return tp.indexOf(k)!==-1})) c["移动端开发"].push(t);
        else if(tp.indexOf("ae")===0 || tp.indexOf("test")!==-1) c["测试"].push(t);
        else{
            var n=(t.name||"").toLowerCase();
            if(["test","用例","冒烟"].some(function(k){return n.indexOf(k)!==-1})) c["测试"].push(t);
            else if(["前端","front","h5","vue","react"].some(function(k){return n.indexOf(k)!==-1})) c["前端开发"].push(t);
            else if(["需求","调研","设计"].some(function(k){return n.indexOf(k)!==-1})) c["产品"].push(t);
            else c["后端开发"].push(t);
        }
    });
    return c;
}
function calcStats(ts){
    var w=ts.filter(function(t){return t._st==="wait"}).length,
        d=ts.filter(function(t){return t._st==="doing"}).length,
        m=new Set();
    ts.forEach(function(t){if(t._rn)m.add(t._rn);});
    return {total:ts.length, wait:w, doing:d, members:m.size};
}
function renderCards(){
    var ts=getTasks(), cats=doClassify(ts), grid=document.getElementById("cg");
    grid.innerHTML="";
    CATS.forEach(function(cat){
        var s=calcStats(cats[cat]);
        var d=document.createElement("a");
        d.className="cd";
        d.href=TODAY+"/未完成"+cat+"任务_详细任务.html"+(curF!=="all"?"?project="+curF:"");
        d.innerHTML='<div class="ci">'+ICONS[cat]+'</div>'
            +'<div class="cn">'+cat+'任务</div>'
            +'<div class="cnu" style="color:'+COLORS[cat]+'">'+s.total+'</div>'
            +'<div class="cdsc">待<span class="cw">'+s.wait+'</span>/做<span class="cdg">'+s.doing+'</span> · <span class="cm">'+s.members+'</span>人</div>';
        grid.appendChild(d);
    });
    renderInsight(ts);
    renderOverview();
}
function renderInsight(tasks){
    var od=tasks.filter(function(t){
        return t._dl && t._dl<TODAY && ["wait","doing"].indexOf(t._st)!==-1;
    });
    var om=new Set(); od.forEach(function(t){if(t._rn)om.add(t._rn)});
    document.getElementById("odInfo").textContent=od.length+" 个延期 / "+om.size+" 人 · 全平台超期追踪";
    var wlUrl=TODAY+"/未完成员工负载_详细任务.html"+(curF!=="all"?"?project="+curF:"");
    document.getElementById("odLink").href=wlUrl.replace("员工负载","延期任务");
    document.getElementById("wlLink").href=wlUrl;
    var ps=new Set(tasks.map(function(t){return t._rn}).filter(function(x){return x}));
    document.getElementById("wlInfo").textContent=ps.size+" 人参与 · 按角色分工时分析";
}
/* ===== 渲染迭代总览 ===== */
function renderOverview(){
    var excs = getExecs();
    var active = excs.filter(function(e){return e.status==="doing"||e.status==="undone"});
    var body = document.getElementById("ovBody");

    /* 汇总统计 */
    var totalTasks=0, totalStories=0, totalBugs=0;
    active.forEach(function(e){
        var s=e._stats||{};
        totalTasks   += s.task_count||0;
        totalStories += s.story_count||0;
        totalBugs    += s.bug_count||0;
    });
    var html='';
    html+='<div class="ov-sum">';
    html+='<div class="ov-sm"><div class="ov-sn" style="color:#7c5cfc">'+active.length+'</div><div class="ov-sl">进行中迭代</div></div>';
    html+='<div class="ov-sm"><div class="ov-sn" style="color:#34d399">'+totalTasks+'</div><div class="ov-sl">总任务数</div></div>';
    html+='<div class="ov-sm"><div class="ov-sn" style="color:#a78bfa">'+totalStories+'</div><div class="ov-sl">总需求数</div></div>';
    html+='<div class="ov-sm"><div class="ov-sn" style="color:#ffa726">'+totalBugs+'</div><div class="ov-sl">总Bug数</div></div>';
    html+='</div>';

    /* 按项目分组 */
    var byProj={};
    active.forEach(function(e){
        var pn=e.project_name||"未知";
        if(!byProj[pn]) byProj[pn]=[];
        byProj[pn].push(e);
    });
    Object.keys(byProj).forEach(function(pn){
        var items=byProj[pn];
        html+='<div class="ov-ptl">'+pn+'（'+items.length+'个迭代）</div>';
        html+='<table class="ov-tbl"><thead><tr>';
        html+='<th>迭代ID</th><th>迭代名称</th><th>时间范围</th>';
        html+='<th>任务|需求|Bug</th><th>完成率</th><th>操作</th>';
        html+='</tr></thead><tbody>';
        items.forEach(function(e){
            var s=e._stats||{};
            var begin=e.begin||"", end=e.end||"";
            var trange=(begin&&end)?begin+" ~ "+end:"-";
            var pct=s.completion_pct||0;
            /* 进度条颜色 */
            var gColor="linear-gradient(90deg,#7c5cfc,#44e5ff)";
            if(pct>=80) gColor="linear-gradient(90deg,#34d399,#6ee7b7)";
            else if(pct>=50) gColor="linear-gradient(90deg,#fbbf24,#fcd34d)";
            else if(pct>=30) gColor="linear-gradient(90deg,#f97316,#fbbf24)";
            html+='<tr>';
            html+='<td><a class="ov-eid" href="#">#'+e.id+'</a></td>';
            html+='<td style="max-width:260px">'+esc(e.name||"")+'</td>';
            html+='<td style="font-size:12px;color:#64748b">'+trange+'</td>';
            html+='<td style="font-size:12px;color:#94a3b8">'+(s.task_count||0)+' | '+(s.story_count||0)+' | '+(s.bug_count||0)+'</td>';
            html+='<td><div class="ov-prg"><div class="ov-prgf" style="width:'+pct+'%;background:'+gColor+'"></div></div>';
            html+='<span class="ov-pct">'+pct+'%</span></td>';
            html+='<td><a class="ov-vl" href="'+TODAY+'/未完成测试任务_详细任务.html?project='+e.project_id+'" target="_blank">查看报告</a></td>';
            html+='</tr>';
        });
        html+='</tbody></table>';
    });
    body.innerHTML=html;
}
function esc(s){
    var d=document.createElement("div"); d.textContent=s; return d.innerHTML;
}
function setFilter(f){
    curF=f;
    document.querySelectorAll(".fn").forEach(function(b){
        b.classList.toggle("active",b.dataset.f===f);
    });
    renderCards();
    location.hash=f;
}
(function(){
    var h=location.hash.replace("#","");
    if(h&&(h==="all"||window.PROJECT_TASKS[h])) curF=h;
    document.querySelectorAll(".fn").forEach(function(b){
        b.classList.toggle("active",b.dataset.f===curF);
    });
    renderCards();
})();
"""

# ── main ───────────────────────────────────────────────────────────────────
def main():
    print('=' * 50)
    print('生成 index.html v8（优化配色）')
    print('=' * 50)

    client = ZentaoClient(CONFIG_FILE)
    print('已连接禅道 API')

    print('获取任务和迭代数据（含 stats）...')
    all_tasks, all_excs = fetch_rich_executions(client)
    print('  任务: %d 条' % len(all_tasks))
    print('  迭代: %d 个' % len(all_excs))

    today = datetime.now().strftime('%Y-%m-%d')
    html = make_html(all_tasks, all_excs, today)

    out = OUTPUT_DIR / 'index.html'
    out.write_text(html, encoding='utf-8')
    print('已写入 %s  (%d KB)' % (out, len(html) // 1024))
    print('完成！')

if __name__ == '__main__':
    main()
