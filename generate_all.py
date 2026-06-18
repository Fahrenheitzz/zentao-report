#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 index.html + 各分类任务明细页
配色方案 v8
"""
import json, hashlib, urllib.request, ssl
from datetime import datetime
from pathlib import Path

CONFIG_FILE   = r'C:\Users\A80369\.zentao\config.json'
OUTPUT_DIR    = Path(r'D:\workbuddy\PM work\zentao-report')
PROJECT_IDS   = [1013, 4047]
PROJECT_NAMES  = {1013: '商城3.0', 4047: '格力官网'}
CATEGORIES   = ['产品', '后端开发', '前端开发', '移动端开发', '测试']
ICONS         = {'产品': '📋', '后端开发': '⚙️', '前端开发': '🌸',
                 '移动端开发': '📱', '测试': '🔬'}

# ── 禅道客户端 ─────────────────────────────────────────────────────
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

# ── 获取数据 ───────────────────────────────────────────────────────
def fetch_all_data(client):
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
                e['project_id']  = pid
                e['project_name'] = pname
                e['_stats'] = {'task_count': 0, 'done_count': 0,
                                'story_count': 0, 'bug_count': 0, 'completion_pct': 0}
                all_excs.append(e)
            if len(es) < 100:
                break
            page += 1

    print('  共 %d 个迭代，开始获取任务...' % len(all_excs))
    seen = set()
    for e in all_excs:
        eid = e['id']
        t_cnt = d_cnt = 0
        page = 1
        while True:
            res = client.get('/executions/%d/tasks' % eid, {'page': page, 'limit': 100})
            ts  = res.get('tasks', [])
            if not ts:
                break
            for t in ts:
                tid = t.get('id')
                if tid and tid not in seen:
                    seen.add(tid)
                    t['_pid']  = e['project_id']
                    t['_pname'] = e['project_name']
                    t['_st']   = t.get('status', 'wait')
                    t['_rn']   = t.get('realname', '') or t.get('assignedTo', '')
                    t['_dl']   = t.get('deadline', '') or ''
                    all_tasks.append(t)
                if t.get('status') in ('done', 'closed'):
                    d_cnt += 1
                t_cnt += 1
            if len(ts) < 100:
                break
            page += 1
        stories = client.get('/executions/%d/stories' % eid).get('stories', [])
        bugs    = client.get('/executions/%d/bugs'    % eid).get('bugs',    [])
        pct = int(d_cnt / t_cnt * 100) if t_cnt > 0 else 0
        e['_stats'] = {
            'task_count':     t_cnt,
            'done_count':     d_cnt,
            'story_count':    len(stories),
            'bug_count':      len(bugs),
            'completion_pct': pct,
        }
    return all_tasks, all_excs

# ── 分类函数 ────────────────────────────────────────────────────────
def classify_task(t):
    tp = (t.get('type') or '').lower()
    nm = (t.get('name') or '').lower()
    if tp.startswith('ab'):          return '产品'
    if tp.startswith('a_dev') and 'front' not in tp: return '后端开发'
    if 'front' in tp or tp.startswith('a_dev2_front'): return '前端开发'
    if any(k in tp for k in ['ios','android','mobile','app']): return '移动端开发'
    if tp.startswith('ae') or 'test' in tp: return '测试'
    if any(k in nm for k in ['test','用例','冒烟']): return '测试'
    if any(k in nm for k in ['前端','front','h5','vue','react']): return '前端开发'
    if any(k in nm for k in ['需求','调研','设计']): return '产品'
    return '后端开发'

# ═══════════════════════════════════════════════════════════
#  明细页模板（Python 字符串，JS 用 /*__PLACEHOLDER__*/ 占位）
# ═══════════════════════════════════════════════════════════

DETAIL_PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>/*__TITLE__*/</title>
<style>
/*__CSS__*/
</style>
</head>
<body>
<div class="ct">
  <a class="bk" href="../index.html">&larr; 返回首页</a>
  <h1 class="pt">/*__ICON__*/ /*__PAGE_TITLE__*/</h1>
  <div class="fb">
    <button class="fn active" data-f="all"  onclick="setFilter('all')">全部项目</button>
    <button class="fn"        data-f="1013" onclick="setFilter('1013')">商城3.0</button>
    <button class="fn"        data-f="4047" onclick="setFilter('4047')">格力官网</button>
  </div>
  <div id="sr" class="sr"></div>
  <div class="cr">
    <div class="cb"><div class="cti">负责人 Top 任务分布</div><canvas id="ac"></canvas></div>
    <div class="cb"><div class="cti">状态分布</div><canvas id="sc"></canvas></div>
    <div class="cb"><div class="cti">优先级分布</div><canvas id="pc"></canvas></div>
  </div>
  <div id="asecs"></div>
</div>

<script>
var CAT = /*__CAT__*/;
var IS_SP = /*__IS_SP__*/;
var TODAY = "/*__TODAY__*/";
window.ALL_TASKS = /*__ALL_TASKS__*/;
window.PROJECT_TASKS = /*__PROJECT_TASKS__*/;
window.PROJECT_NAMES = /*__PROJECT_NAMES__*/;
</script>

<script>
/*__DETAIL_JS__*/
</script>
</body>
</html>
"""

DETAIL_CSS = (
    "*{margin:0;padding:0;box-sizing:border-box}"
    "body{"
        "font-family:-apple-system,'Microsoft YaHei','PingFang SC',sans-serif;"
        "background:linear-gradient(160deg,#0a0e27 0%,#131736 40%,#0d1117 100%);"
        "min-height:100vh;padding:20px 16px 60px;color:#e2e8f0;"
        "background-attachment:fixed"
    "}"
    ".ct{max-width:1200px;margin:0 auto}"
    ".bk{display:inline-block;color:#7c5cfc;font-size:13px;text-decoration:none;margin-bottom:12px;transition:color .2s}"
    ".bk:hover{color:#44e5ff;text-decoration:underline}"
    ".pt{font-size:22px;font-weight:700;"
        "background:linear-gradient(120deg,#7c5cfc,#44e5ff);"
        "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
        "background-clip:text;margin-bottom:14px}"
    ".fb{display:flex;justify-content:center;gap:8px;margin:14px 0 18px;flex-wrap:wrap}"
    ".fn{padding:6px 18px;border-radius:20px;font-size:12px;font-weight:600;"
        "border:1px solid rgba(255,255,255,0.1);background:rgba(22,27,51,0.6);"
        "color:#64748b;cursor:pointer;transition:all .25s}"
    ".fn:hover{background:rgba(124,92,252,0.1);border-color:rgba(124,92,252,0.3);color:#a78bfa}"
    ".fn.active{background:linear-gradient(135deg,rgba(124,92,252,0.25),rgba(68,229,255,0.15));"
        "border-color:rgba(124,92,252,0.5);color:#fff;"
        "box-shadow:0 0 12px rgba(124,92,252,0.2)}"
    ".sr{display:flex;flex-wrap:wrap;gap:12px;justify-content:center;margin-bottom:20px}"
    ".si{background:rgba(22,27,51,0.6);border-radius:12px;padding:14px 22px;"
        "text-align:center;border:1px solid rgba(255,255,255,0.06);min-width:110px;transition:all .3s}"
    ".si:hover{border-color:rgba(124,92,252,0.2)}"
    ".sn{font-size:26px;font-weight:800;text-shadow:0 2px 6px rgba(0,0,0,0.3)}"
    ".sl{font-size:11px;color:#64748b;margin-top:2px}"
    ".cr{display:flex;flex-wrap:wrap;gap:16px;margin-bottom:24px}"
    ".cb{flex:1;min-width:260px;background:rgba(22,27,51,0.6);"
        "border-radius:14px;padding:18px;border:1px solid rgba(255,255,255,0.06)}"
    ".cti{font-size:14px;font-weight:600;color:#94a3b8;margin-bottom:14px}"
    "canvas{max-height:220px;width:100% !important}"
    ".as{margin-bottom:16px}"
    ".ash{display:flex;align-items:center;gap:10px;cursor:pointer;"
        "background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);"
        "border-radius:10px;padding:12px 16px;transition:all .2s;user-select:none}"
    ".ash:hover{background:rgba(255,255,255,0.06)}"
    ".asm{font-size:14px;font-weight:700}"
    ".asc{font-size:12px;color:#64748b}"
    ".ast{margin-left:auto;font-size:12px;color:#555;transition:transform .2s}"
    ".aok .ast{transform:rotate(90deg)}"
    ".abd{display:none}.aok .abd{display:block}"
    ".tw{padding:8px 0}"
    "table{width:100%;border-collapse:separate;border-spacing:0 2px;font-size:12px}"
    "th{background:rgba(124,92,252,0.1);color:#94a3b8;padding:8px 12px;"
        "text-align:left;font-weight:600;white-space:nowrap;font-size:11px}"
    "td{padding:8px 12px;border-bottom:1px solid rgba(255,255,255,0.03);white-space:nowrap}"
    "tr:hover td{background:rgba(124,92,252,0.05)}"
    ".sw{color:#f97066;font-weight:700}"
    ".sd{color:#34d399;font-weight:700}"
    ".ss{color:#ef4444;font-weight:700}"
    ".p1{color:#ef4444}.p2{color:#fbbf24}.p3{color:#e2e8f0}.p4{color:#64748b}"
    ".ot{color:#ef4444;font-weight:700;font-size:11px}"
    ".tn{color:#7c5cfc;font-weight:600;font-size:12px}"
)

# JS 逻辑（明细页共用，占位符在 generate 时替换）
DETAIL_JS = r"""
function classifyTask(t){
    var tp=(t.type||"").toLowerCase();
    var nm=(t.name||"").toLowerCase();
    if(tp.indexOf("ab")===0) return "产品";
    if(tp.indexOf("a_dev")===0 && tp.indexOf("front")===-1) return "后端开发";
    if(tp.indexOf("front")!==-1 || tp.indexOf("a_dev2_front")===0) return "前端开发";
    if(["ios","android","mobile","app"].some(function(k){return tp.indexOf(k)!==-1})) return "移动端开发";
    if(tp.indexOf("ae")===0 || tp.indexOf("test")!==-1) return "测试";
    if(["test","用例","冒烟"].some(function(k){return nm.indexOf(k)!==-1})) return "测试";
    if(["前端","front","h5","vue","react"].some(function(k){return nm.indexOf(k)!==-1})) return "前端开发";
    if(["需求","调研","设计"].some(function(k){return nm.indexOf(k)!==-1})) return "产品";
    return "后端开发";
}
function getTasks(){
    return curF==="all"?window.ALL_TASKS:(window.PROJECT_TASKS[curF]||[]);
}
function setFilter(f){
    curF=f;
    document.querySelectorAll(".fn").forEach(function(b){
        b.classList.toggle("active",b.dataset.f===f);
    });
    renderAll();
    location.hash=f;
}
function gStatus(s){
    if(s==="wait")  return "待处理";
    if(s==="doing") return "进行中";
    if(s==="done")  return "已完成";
    if(s==="pause") return "暂停";
    if(s==="cancel") return "已取消";
    return s||"-";
}
function gPri(p){
    var m={"1":"紧急","2":"高","3":"中","4":"低"};
    return m[p]||p||"-";
}
function escHtml(s){
    var d=document.createElement("div"); d.textContent=s||""; return d.innerHTML;
}

/* 汇总卡片 */
function renderSummary(ts){
    var tot=ts.length,
        w=ts.filter(function(t){return t._st==="wait"}).length,
        d=ts.filter(function(t){return t._st==="doing"}).length,
        m=new Set(ts.map(function(t){return t._rn}).filter(Boolean)).size,
        eh=Math.round(ts.reduce(function(s,t){return s+(parseFloat(t.est_h)||0)},0)*10)/10,
        ch=Math.round(ts.reduce(function(s,t){return s+(parseFloat(t.con_h)||0)},0)*10)/10;
    document.getElementById("sr").innerHTML=
        '<div class="si"><div class="sn" style="color:#7c5cfc">'+tot+'</div><div class="sl">任务总数</div></div>'
      + '<div class="si"><div class="sn" style="color:#f97066">'+w+'</div><div class="sl">待处理</div></div>'
      + '<div class="si"><div class="sn" style="color:#34d399">'+d+'</div><div class="sl">进行中</div></div>'
      + '<div class="si"><div class="sn" style="color:#e2e8f0">'+m+'</div><div class="sl">参与人数</div></div>'
      + '<div class="si"><div class="sn" style="color:#64748b">'+eh+'</div><div class="sl">预估(h)</div></div>'
      + '<div class="si"><div class="sn" style="color:#44e5ff">'+ch+'</div><div class="sl">消耗(h)</div></div>';
}

/* 柱状图：负责人Top任务 */
function drawBar(cid, labels, values){
    var cv=document.getElementById(cid); if(!cv) return;
    var ctx=cv.getContext("2d");
    cv.width=cv.parentElement.clientWidth-36; cv.height=200;
    var W=cv.width, H=cv.height,
        pad={top:10,right:10,bottom:40,left:45},
        cw=W-pad.left-pad.right,
        ch=H-pad.top-pad.bottom,
        mx=Math.max.apply(null,values.concat([1])),
        bw=cw/values.length*0.65,
        gap=(cw/values.length)*(0.35/2);
    ctx.clearRect(0,0,W,H);
    values.forEach(function(v,i){
        var x=pad.left+i*(cw/values.length)+gap,
            ratio=v/mx,
            barH=Math.max(ratio*(ch-4),2),
            y=pad.top+ch-barH;
        ctx.fillStyle="rgba(124,92,252,0.75)";
        ctx.beginPath();
        if(ctx.roundRect) ctx.roundRect(x,y,bw,barH,4); else ctx.rect(x,y,bw,barH);
        ctx.fill();
        ctx.fillStyle="#8892b0"; ctx.font="11px sans-serif"; ctx.textAlign="center";
        ctx.fillText(labels[i]||"?",x+bw/2,H-8);
        ctx.fillStyle="#e2e8f0"; ctx.font="bold 11px sans-serif";
        ctx.fillText(v,x+bw/2,y-4);
    });
}

/* 饼图 */
function drawPie(cid, items, colors){
    var cv=document.getElementById(cid); if(!cv) return;
    var ctx=cv.getContext("2d");
    cv.width=cv.parentElement.clientWidth-36; cv.height=180;
    var cx=cv.width/2, cy=cv.height/2,
        r=Math.min(cx,cy)-30,
        tot=items.reduce(function(s,i){return s+i.v},0)||1,
        start=-Math.PI/2;
    ctx.clearRect(0,0,cv.width,cv.height);
    items.forEach(function(item,i){
        var sweep=(item.v/tot)*Math.PI*2;
        ctx.beginPath(); ctx.moveTo(cx,cy);
        ctx.arc(cx,cy,r,start,start+sweep);
        ctx.closePath();
        ctx.fillStyle=colors[i%colors.length];
        ctx.fill();
        start+=sweep;
    });
    var lx=cx-Math.max(items.length*20,40), ly=cy+r+16;
    items.forEach(function(item,i){
        ctx.fillStyle=colors[i%colors.length];
        ctx.fillRect(lx+70*i,ly,10,10);
        ctx.fillStyle="#94a3b8"; ctx.font="11px sans-serif"; ctx.textAlign="left";
        ctx.fillText(item.l+"("+item.v+")",lx+70*i+14,ly+9);
    });
}

/* 渲染图表 */
function renderCharts(ts){
    var byPerson={};
    ts.forEach(function(t){var nm=t._rn||"未指派"; byPerson[nm]=(byPerson[nm]||0)+1;});
    var sorted=Object.entries(byPerson).sort(function(a,b){return b[1]-a[1]}).slice(0,12);
    drawBar("ac", sorted.map(function(e){return e[0]}), sorted.map(function(e){return e[1]}));

    var sm={};
    ts.forEach(function(t){var s=gStatus(t._st); sm[s]=(sm[s]||0)+1});
    var si=Object.entries(sm).map(function(kv){return {l:kv[0],v:kv[1]}});
    drawPie("sc", si, ["#f97066","#34d399","#ef4444","#64748b","#7c5cfc"]);

    var pm={};
    ts.forEach(function(t){var p=t.pri||"3"; pm[p]=(pm[p]||0)+1});
    var pi=Object.entries(pm).sort(function(a,b){return parseInt(a[0])-parseInt(b[0])})
        .map(function(kv){return {l:gPri(kv[0]),v:kv[1]}});
    drawPie("pc", pi, ["#ef4444","#fbbf24","#e2e8f0","#64748b"]);
}

/* 渲染任务列表（按负责人分组）*/
function renderTaskList(ts){
    var byPerson={};
    ts.forEach(function(t){var nm=t._rn||"未指派"; if(!byPerson[nm]) byPerson[nm]=[]; byPerson[nm].push(t);});
    var sorted=Object.entries(byPerson).sort(function(a,b){return b[1].length-a[1].length});
    var con=document.getElementById("asecs");
    con.innerHTML="";
    sorted.forEach(function(pair){
        var nm=pair[0], tasks=pair[1];
        var dc=tasks.filter(function(t){return t._st==="doing"}).length,
            wc=tasks.filter(function(t){return t._st==="wait"}).length;
        var sec=document.createElement("div");
        sec.className="as";
        var rows=tasks.map(function(t){
            var cls=t._st==="wait"?"sw":t._st==="doing"?"sd":"ss";
            var pcl="p"+(t.pri||"3");
            var dl=t._dl||"-";
            var dlCell="<td>"+dl+"</td>";
            if(dl && dl<TODAY && ["wait","doing"].indexOf(t._st)!==-1)
                dlCell='<td><span class="ot">'+dl+'</span></td>';
            return "<tr>"
                +'<td class="tn">'+t.id+'</td>'
                +'<td style="text-align:left;max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'+(escHtml(t.name))+'">'
                    +escHtml((t._pname||"")+" "+t.name)+'</td>'
                +'<td class="'+cls+'">'+gStatus(t._st)+'</td>'
                +'<td class="'+pcl+'">'+gPri(t.pri)+'</td>'
                + dlCell
                +"<td>"+(t.est_h||0)+"</td>"
                +"<td>"+(t.con_h||0)+"</td>"
                +"<td>"+(t.lft_h||0)+"</td>"
                +"</tr>";
        }).join("");
        sec.innerHTML=
            '<div class="ash" onclick="this.parentElement.classList.toggle(\'aok\')">'
          + '<div class="asm">'+escHtml(nm)+'</div>'
          + '<div class="asc">'+tasks.length+'个任务 (做'+dc+'/待'+wc+')</div>'
          + '<div class="ast">&#9654;</div>'
          + '</div>'
          + '<div class="abd"><div class="tw">'
          + '<table><thead><tr>'
          + '<th>ID</th><th>任务名称</th><th>状态</th><th>优先级</th>'
          + '<th>截止日期</th><th>预估h</th><th>消耗h</th><th>剩余h</th>'
          + '</tr></thead><tbody>'
          + rows
          + '</tbody></table>'
          + '</div></div>';
        con.appendChild(sec);
    });
}

/* 主渲染 */
function renderAll(){
    var allTs=getTasks();
    var targetTs;
    if(IS_SP){
        targetTs=allTs.filter(function(t){
            return t._dl && t._dl<TODAY && ["wait","doing"].indexOf(t._st)!==-1;
        });
    }else if(CAT){
        targetTs=allTs.filter(function(t){return classifyTask(t)===CAT});
    }else{
        targetTs=allTs;
    }
    renderSummary(targetTs);
    renderCharts(targetTs);
    renderTaskList(targetTs);
}

(function(){
    var h=location.hash.replace("#","");
    if(h && (h==="all" || window.PROJECT_TASKS[h])) curF=h;
    document.querySelectorAll(".fn").forEach(function(b){
        b.classList.toggle("active",b.dataset.f===curF);
    });
    renderAll();
})();
"""

# ═══════════════════════════════════════════════════════════
#  生成明细页
# ═══════════════════════════════════════════════════════════

def make_detail_page(category, icon, is_special, all_tasks, project_tasks, today, out_path):
    """生成一个分类明细页（或延期任务页）"""
    all_tasks_js   = json.dumps(all_tasks, ensure_ascii=False)
    project_tasks_js = json.dumps(project_tasks, ensure_ascii=False)
    project_names_js = json.dumps(PROJECT_NAMES, ensure_ascii=False)
    cat_js   = json.dumps(category) if not is_special else "null"
    is_sp_js = "true" if is_special else "false"

    if is_special:
        title       = "%s - 禅道报告" % category
        page_title  = category
    else:
        title       = "%s任务 - 禅道报告" % category
        page_title  = "%s任务" % category

    html = DETAIL_PAGE_TEMPLATE
    # 替换占位符（全部用 string.replace，避免 % 格式化冲突）
    html = html.replace("/*__TITLE__*/",        title)
    html = html.replace("/*__ICON__*/",         icon)
    html = html.replace("/*__PAGE_TITLE__*/",  page_title)
    html = html.replace("/*__CAT__*/",         cat_js)
    html = html.replace("/*__IS_SP__*/",       is_sp_js)
    html = html.replace("/*__TODAY__*/",       today)
    html = html.replace("/*__ALL_TASKS__*/",   all_tasks_js)
    html = html.replace("/*__PROJECT_TASKS__*/", project_tasks_js)
    html = html.replace("/*__PROJECT_NAMES__*/", project_names_js)
    html = html.replace("/*__CSS__*/",         DETAIL_CSS)
    html = html.replace("/*__DETAIL_JS__*/",  DETAIL_JS)

    out_path.write_text(html, encoding='utf-8')
    return len(html)


def generate_all_detail_pages(all_tasks, today):
    project_tasks = {}
    for pid in PROJECT_IDS:
        project_tasks[str(pid)] = [t for t in all_tasks if t.get('_pid') == pid]

    detail_dir = OUTPUT_DIR / today
    detail_dir.mkdir(parents=True, exist_ok=True)

    for cat in CATEGORIES:
        fname = '未完成%s任务_详细任务.html' % cat
        nbytes = make_detail_page(
            category   = cat,
            icon       = ICONS.get(cat, '📊'),
            is_special = False,
            all_tasks  = all_tasks,
            project_tasks = project_tasks,
            today      = today,
            out_path   = detail_dir / fname
        )
        print('  ✓ %s (%d KB)' % (fname, nbytes // 1024))

    # 延期任务页
    nbytes = make_detail_page(
        category   = '延期任务',
        icon       = '🚨',
        is_special = True,
        all_tasks  = all_tasks,
        project_tasks = project_tasks,
        today      = today,
        out_path   = detail_dir / '未完成延期任务_详细任务.html'
    )
    print('  ✓ 未完成延期任务_详细任务.html (%d KB)' % (nbytes // 1024))

    # 员工负载页（不过滤分类，显示所有人的任务）
    # 用 IS_SP=false, CAT=null → JS 中 CAT=null 时 targetTs=allTs
    html = DETAIL_PAGE_TEMPLATE
    all_tasks_js   = json.dumps(all_tasks, ensure_ascii=False)
    project_tasks_js = json.dumps(project_tasks, ensure_ascii=False)
    project_names_js = json.dumps(PROJECT_NAMES, ensure_ascii=False)
    html = html.replace("/*__TITLE__*/",       "员工负载 - 禅道报告")
    html = html.replace("/*__ICON__*/",        "💪")
    html = html.replace("/*__PAGE_TITLE__*/", "员工负载")
    html = html.replace("/*__CAT__*/",         "null")
    html = html.replace("/*__IS_SP__*/",       "false")
    html = html.replace("/*__TODAY__*/",       today)
    html = html.replace("/*__ALL_TASKS__*/",   all_tasks_js)
    html = html.replace("/*__PROJECT_TASKS__*/", project_tasks_js)
    html = html.replace("/*__PROJECT_NAMES__*/", project_names_js)
    html = html.replace("/*__CSS__*/",         DETAIL_CSS)
    # 员工负载页：不过滤分类，显示所有任务（按负责人分组）
    # 修改 JS：CAT=null 时 targetTs = allTs
    js_wl = DETAIL_JS.replace(
        'targetTs=allTs.filter(function(t){return classifyTask(t)===CAT});',
        'if(CAT===null){targetTs=allTs;}else{targetTs=allTs.filter(function(t){return classifyTask(t)===CAT});}'
    )
    html = html.replace("/*__DETAIL_JS__*/", js_wl)
    out_wl = detail_dir / '未完成员工负载_详细任务.html'
    out_wl.write_text(html, encoding='utf-8')
    print('  ✓ 未完成员工负载_详细任务.html (%d KB)' % (len(html) // 1024))


# ═══════════════════════════════════════════════════════════
#  生成 index.html（复用 v8 的逻辑，改为模板方式）
# ═══════════════════════════════════════════════════════════

INDEX_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>禅道任务报告中心</title>
<style>
/*__CSS__*/
</style>
</head>
<body>
<div class="ct">
    <div class="hd">
        <span class="logo">📊</span>
        <h1>禅道任务报告中心</h1>
        <p class="sub">Zentao Task Dashboard</p>
    </div>
    <div class="dt"><span>/*__TODAY__*/ 更新</span></div>
    <div class="fb">
        <button class="fn active" data-f="all"  onclick="setFilter('all')">全部项目</button>
        <button class="fn"        data-f="1013" onclick="setFilter('1013')">商城3.0</button>
        <button class="fn"        data-f="4047" onclick="setFilter('4047')">格力官网</button>
    </div>
    <div id="cg" class="gd"></div>
    <div class="stit">— 数据洞察 —</div>
    <div class="ig">
        <a class="icd iov" id="odLink" href="#">
            <div class="ici">🚨</div>
            <div class="icbdy"><div class="ict">延期任务</div>
            <div class="icsu" id="odInfo">-- 个延期 / -- 人</div></div>
        </a>
        <a class="icd iwl" id="wlLink" href="#">
            <div class="ici">💪</div>
            <div class="icbdy"><div class="ict">员工负载</div>
            <div class="icsu" id="wlInfo">按角色分工时分析</div></div>
        </a>
    </div>
    <div class="ov-section">
        <div class="ov-header">
            <div class="ov-title">📊 迭代执行进展总览</div>
        </div>
        <div id="ovBody"></div>
    </div>
    <div class="ft">商城3.0 + 格力官网 · 禅道任务报告中心</div>
</div>
<script>
window.ALL_TASKS = /*__ALL_TASKS__*/;
window.ALL_EXECS = /*__ALL_EXECS__*/;
window.PROJECT_TASKS = /*__PROJECT_TASKS__*/;
window.PROJECT_NAMES = /*__PROJECT_NAMES__*/;
</script>
<script>
/*__INDEX_JS__*/
</script>
</body>
</html>
"""

INDEX_CSS = (
    "*{margin:0;padding:0;box-sizing:border-box}"
    "body{"
        "font-family:-apple-system,BlinkMacSystemFont,'Microsoft YaHei','PingFang SC',sans-serif;"
        "background:linear-gradient(160deg,#0a0e27 0%,#131736 40%,#0d1117 100%);"
        "min-height:100vh;padding:28px 24px 60px;color:#e2e8f0;"
        "background-attachment:fixed"
    "}"
    ".ct{max-width:1280px;margin:0 auto}"
    ".hd{text-align:center;margin-bottom:10px}"
    ".logo{font-size:38px;display:block;margin-bottom:4px;"
        "filter:drop-shadow(0 0 12px rgba(124,92,252,0.4))}"
    ".h1{font-size:28px;font-weight:800;letter-spacing:1px;"
        "background:linear-gradient(135deg,#7c5cfc,#44e5ff,#a78bfa);"
        "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
        "background-clip:text}"
    ".sub{color:#64748b;font-size:13px;letter-spacing:2px;margin-top:4px}"
    ".dt{text-align:center;margin:16px 0 22px;font-size:12px}"
    ".dt span{display:inline-block;padding:5px 18px;border-radius:20px;"
        "background:rgba(124,92,252,0.08);border:1px solid rgba(124,92,252,0.2);"
        "color:#a78bfa;font-size:12px}"
    ".fb{display:flex;justify-content:center;gap:8px;margin-bottom:24px;flex-wrap:wrap}"
    ".fn{padding:7px 22px;border-radius:20px;font-size:13px;font-weight:600;"
        "border:1px solid rgba(255,255,255,0.08);background:rgba(22,27,51,0.6);"
        "color:#64748b;cursor:pointer;transition:all .3s;letter-spacing:0.3px}"
    ".fn:hover{background:rgba(124,92,252,0.1);border-color:rgba(124,92,252,0.3);color:#a78bfa}"
    ".fn.active{background:linear-gradient(135deg,rgba(124,92,252,0.25),rgba(68,229,255,0.15));"
        "border-color:rgba(124,92,252,0.5);color:#fff;"
        "box-shadow:0 0 16px rgba(124,92,252,0.2)}"
    ".stit{font-size:13px;font-weight:700;color:#64748b;margin:28px 0 14px;"
        "text-align:center;letter-spacing:3px}"
    ".gd{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));"
        "gap:14px;margin-bottom:4px}"
    ".cd{position:relative;display:flex;flex-direction:column;align-items:center;"
        "padding:26px 16px 20px;border-radius:18px;"
        "background:rgba(22,27,51,0.7);"
        "border:1px solid rgba(255,255,255,0.06);"
        "cursor:pointer;transition:all .35s;overflow:hidden;"
        "text-decoration:none;color:inherit;backdrop-filter:blur(6px)}"
    ".cd::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;"
        "background:linear-gradient(90deg,transparent,#7c5cfc,transparent);"
        "opacity:0;transition:opacity .35s}"
    ".cd:hover{transform:translateY(-5px);"
        "border-color:rgba(124,92,252,0.25);"
        "box-shadow:0 16px 40px rgba(0,0,0,0.35),0 0 0 1px rgba(124,92,252,0.1);"
        "background:rgba(28,33,62,0.85)}"
    ".cd:hover::before{opacity:1}"
    ".ci{font-size:36px;margin-bottom:10px;"
        "filter:drop-shadow(0 2px 6px rgba(0,0,0,0.3))}"
    ".cn{font-size:13px;font-weight:600;color:#94a3b8;margin-bottom:6px;letter-spacing:0.5px}"
    ".cnu{font-size:32px;font-weight:900;margin-bottom:4px;text-shadow:0 2px 8px rgba(0,0,0,0.3)}"
    ".cdsc{font-size:12px;color:#64748b;text-align:center;line-height:1.6}"
    ".cw{color:#f97066;font-weight:700}"
    ".cdg{color:#34d399;font-weight:700}"
    ".cm{color:#7c5cfc;font-weight:700}"
    ".cpj{margin-top:8px;font-size:11px;color:#475569;line-height:1.5}"
    ".ig{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));"
        "gap:14px;margin-top:20px}"
    ".icd{display:flex;align-items:center;gap:18px;padding:20px 22px;border-radius:18px;"
        "background:rgba(22,27,51,0.7);border:1px solid rgba(255,255,255,0.06);"
        "cursor:pointer;transition:all .35s;color:inherit;text-decoration:none;"
        "backdrop-filter:blur(6px)}"
    ".icd:hover{transform:translateY(-4px);border-color:rgba(255,255,255,0.12);"
        "box-shadow:0 12px 32px rgba(0,0,0,0.3)}"
    ".ici{font-size:38px;min-width:50px;text-align:center;"
        "filter:drop-shadow(0 2px 6px rgba(0,0,0,0.3))}"
    ".icbdy{flex:1}"
    ".ict{font-size:15px;font-weight:700;margin-bottom:5px}"
    ".icsu{font-size:12px;color:#64748b;line-height:1.5}"
    ".iov .ict{color:#f97066}"
    ".iwl .ict{color:#fbbf24}"
    ".ov-section{margin-top:40px;padding-top:8px}"
    ".ov-header{display:flex;align-items:center;justify-content:space-between;"
        "margin-bottom:16px;flex-wrap:wrap;gap:10px}"
    ".ov-title{font-size:20px;font-weight:800;letter-spacing:0.5px;"
        "background:linear-gradient(135deg,#7c5cfc,#44e5ff);"
        "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
        "background-clip:text}"
    ".ov-sum{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:20px}"
    ".ov-sm{background:rgba(22,27,51,0.6);border-radius:14px;padding:14px 24px;"
        "text-align:center;border:1px solid rgba(255,255,255,0.06);"
        "min-width:110px;transition:all .3s}"
    ".ov-sm:hover{border-color:rgba(124,92,252,0.2);"
        "box-shadow:0 4px 16px rgba(0,0,0,0.2)}"
    ".ov-sn{font-size:26px;font-weight:900;text-shadow:0 2px 6px rgba(0,0,0,0.3)}"
    ".ov-sl{font-size:11px;color:#64748b;margin-top:3px;letter-spacing:0.5px}"
    ".ov-ptl{font-size:14px;font-weight:700;color:#94a3b8;"
        "margin:20px 0 10px;border-left:3px solid #7c5cfc;padding-left:12px}"
    ".ov-tbl{width:100%;border-collapse:separate;border-spacing:0 4px;font-size:13px;margin-top:2px}"
    ".ov-tbl thead{position:sticky;top:0}"
    ".ov-tbl th{background:rgba(124,92,252,0.1);color:#94a3b8;padding:10px 14px;"
        "text-align:left;font-weight:700;font-size:11px;letter-spacing:0.5px;"
        "border-bottom:2px solid rgba(124,92,252,0.15)}"
    ".ov-tbl td{padding:11px 14px;border-bottom:1px solid rgba(255,255,255,0.04);transition:background .2s}"
    ".ov-tbl tbody tr{transition:all .25s}"
    ".ov-tbl tbody tr:hover td{background:rgba(124,92,252,0.06);"
        "box-shadow:inset 0 0 0 1px rgba(124,92,252,0.1)}"
    ".ov-eid{color:#7c5cfc;text-decoration:none;font-weight:700;font-size:13px;transition:color .2s}"
    ".ov-eid:hover{color:#44e5ff}"
    ".ov-prg{display:inline-block;width:80px;height:8px;background:rgba(255,255,255,0.06);"
        "border-radius:5px;overflow:hidden;vertical-align:middle;margin-right:8px}"
    ".ov-prgf{height:100%;border-radius:5px;transition:width .6s ease}"
    ".ov-pct{font-size:12px;color:#64748b;font-weight:600}"
    ".ov-vl{color:#7c5cfc;font-size:12px;text-decoration:none;font-weight:600;transition:color .2s}"
    ".ov-vl:hover{color:#44e5ff}"
    ".ft{text-align:center;margin-top:48px;padding-top:20px;"
        "border-top:1px solid rgba(255,255,255,0.04);"
        "color:#4a5568;font-size:11px;letter-spacing:1px}"
)

INDEX_JS = r"""
var CATS = ["产品","后端开发","前端开发","移动端开发","测试"];
var ICONS = {"产品":"📋","后端开发":"⚙️","前端开发":"🌸","移动端开发":"📱","测试":"🔬"};
var COLORS = {"产品":"#a78bfa","后端开发":"#34d399","前端开发":"#f093fb","移动端开发":"#ffa726","测试":"#22d3ee"};
var TODAY = "/*__TODAY__*/";
var curF  = "all";

function getTasks(){
    return curF==="all" ? window.ALL_TASKS : (window.PROJECT_TASKS[curF]||[]);
}
function getExecs(){
    if(curF==="all") return window.ALL_EXECS;
    return window.ALL_EXECS.filter(function(e){ return String(e.project_id)===curF });
}
function classifyTask(t){
    var tp=(t.type||"").toLowerCase();
    var nm=(t.name||"").toLowerCase();
    if(tp.indexOf("ab")===0) return "产品";
    if(tp.indexOf("a_dev")===0 && tp.indexOf("front")===-1) return "后端开发";
    if(tp.indexOf("front")!==-1 || tp.indexOf("a_dev2_front")===0) return "前端开发";
    if(["ios","android","mobile","app"].some(function(k){ return tp.indexOf(k)!==-1 })) return "移动端开发";
    if(tp.indexOf("ae")===0 || tp.indexOf("test")!==-1) return "测试";
    if(["test","用例","冒烟"].some(function(k){ return nm.indexOf(k)!==-1 })) return "测试";
    if(["前端","front","h5","vue","react"].some(function(k){ return nm.indexOf(k)!==-1 })) return "前端开发";
    if(["需求","调研","设计"].some(function(k){ return nm.indexOf(k)!==-1 })) return "产品";
    return "后端开发";
}
function calcStats(ts){
    var w=ts.filter(function(t){ return t._st==="wait" }).length,
        d=ts.filter(function(t){ return t._st==="doing" }).length,
        m=new Set();
    ts.forEach(function(t){ if(t._rn) m.add(t._rn); });
    return {total:ts.length, wait:w, doing:d, members:m.size};
}
function renderCards(){
    var ts=getTasks(), grid=document.getElementById("cg");
    grid.innerHTML="";
    CATS.forEach(function(cat){
        var cats={}; CATS.forEach(function(k){ cats[k]=[]; });
        ts.forEach(function(t){ var c=classifyTask(t); if(cats[c]) cats[c].push(t); });
        var s={total:cats[cat].length,
            wait:cats[cat].filter(function(t){ return t._st==="wait" }).length,
            doing:cats[cat].filter(function(t){ return t._st==="doing" }).length,
            members:new Set(cats[cat].map(function(t){ return t._rn }).filter(Boolean)).size };
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
    var om=new Set(); od.forEach(function(t){ if(t._rn) om.add(t._rn); });
    document.getElementById("odInfo").textContent=od.length+" 个延期 / "+om.size+" 人 · 全平台超期追踪";
    var wlUrl=TODAY+"/未完成员工负载_详细任务.html"+(curF!=="all"?"?project="+curF:"");
    document.getElementById("odLink").href=wlUrl.replace("员工负载","延期任务");
    document.getElementById("wlLink").href=wlUrl;
    var ps=new Set(tasks.map(function(t){ return t._rn }).filter(function(x){ return x }));
    document.getElementById("wlInfo").textContent=ps.size+" 人参与 · 按角色分工时分析";
}
function renderOverview(){
    var excs=getExecs();
    var active=excs.filter(function(e){ return e.status==="doing"||e.status==="undone" });
    var body=document.getElementById("ovBody");
    var totalTasks=0, totalStories=0, totalBugs=0;
    active.forEach(function(e){
        var s=e._stats||{};
        totalTasks    += s.task_count||0;
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
            var s=e._stats||{}, begin=e.begin||"", end=e.end||"";
            var trange=(begin&&end)?begin+" ~ "+end:"-";
            var pct=s.completion_pct||0;
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
    var d=document.createElement("div"); d.textContent=s||""; return d.innerHTML;
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
    if(h && (h==="all" || window.PROJECT_TASKS[h])) curF=h;
    document.querySelectorAll(".fn").forEach(function(b){
        b.classList.toggle("active",b.dataset.f===curF);
    });
    renderCards();
})();
"""


def make_index_html(all_tasks, all_excs, today):
    all_tasks_js  = json.dumps(all_tasks, ensure_ascii=False)
    all_excs_js  = json.dumps(all_excs,  ensure_ascii=False)
    project_tasks = {}
    for pid in PROJECT_IDS:
        project_tasks[str(pid)] = [t for t in all_tasks if t.get('_pid') == pid]
    project_tasks_js  = json.dumps(project_tasks, ensure_ascii=False)
    project_names_js = json.dumps(PROJECT_NAMES, ensure_ascii=False)

    html = INDEX_HTML_TEMPLATE
    html = html.replace("/*__CSS__*/",        INDEX_CSS)
    html = html.replace("/*__TODAY__*/",      today)
    html = html.replace("/*__ALL_TASKS__*/",  all_tasks_js)
    html = html.replace("/*__ALL_EXECS__*/",  all_excs_js)
    html = html.replace("/*__PROJECT_TASKS__*/", project_tasks_js)
    html = html.replace("/*__PROJECT_NAMES__*/", project_names_js)
    # INDEX_JS 里的 TODAY 占位符也要替换
    index_js = INDEX_JS.replace("/*__TODAY__*/", today)
    html = html.replace("/*__INDEX_JS__*/",   index_js)
    return html


# ═══════════════════════════════════════════════════════════
#  main
# ═══════════════════════════════════════════════════════════

def main():
    print('=' * 50)
    print('禅道任务报告生成器 v9')
    print('=' * 50)

    client = ZentaoClient(CONFIG_FILE)
    print('已连接禅道 API')

    print('获取任务和迭代数据...')
    all_tasks, all_excs = fetch_all_data(client)
    print('  任务: %d 条' % len(all_tasks))
    print('  迭代: %d 个' % len(all_excs))

    today = datetime.now().strftime('%Y-%m-%d')

    # 1. 生成首页
    print('生成 index.html ...')
    html_idx = make_index_html(all_tasks, all_excs, today)
    out_idx = OUTPUT_DIR / 'index.html'
    out_idx.write_text(html_idx, encoding='utf-8')
    print('  ✓ index.html (%d KB)' % (len(html_idx) // 1024))

    # 2. 生成各分类明细页
    print('生成任务明细页面...')
    generate_all_detail_pages(all_tasks, today)

    print('=' * 50)
    print('完成！')
    print('  首页: %s' % out_idx)
    print('  明细页目录: %s' % (OUTPUT_DIR / today))
    print('=' * 50)


if __name__ == '__main__':
    main()
