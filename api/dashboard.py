"""
Web 管理页面 - 内嵌HTML，零外部依赖
"""
import json
import time
import logging
from urllib.parse import urlparse, parse_qs
from db import get_db
from config import API_HOST, API_PORT, MIN_SCORE

logger = logging.getLogger('dashboard')

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PyProxyPool 管理面板</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f1117; color: #e0e0e0; min-height: 100vh; }
.header { background: linear-gradient(135deg, #1a1d29 0%, #252836 100%); border-bottom: 1px solid #2d3148; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
.header h1 { font-size: 20px; font-weight: 600; color: #fff; }
.header h1 span { color: #6c63ff; }
.header-right { display: flex; gap: 12px; align-items: center; }
.badge { background: #1e2235; border: 1px solid #2d3148; padding: 4px 12px; border-radius: 20px; font-size: 12px; color: #8b8fa3; }
.badge.online { border-color: #22c55e; color: #22c55e; }
.badge.online::before { content: ""; display: inline-block; width: 6px; height: 6px; background: #22c55e; border-radius: 50%; margin-right: 6px; animation: pulse 2s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
.container { max-width: 1400px; margin: 0 auto; padding: 20px 24px; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 20px; }
.stat-card { background: #1a1d29; border: 1px solid #2d3148; border-radius: 12px; padding: 20px; position: relative; overflow: hidden; }
.stat-card::after { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px; }
.stat-card:nth-child(1)::after { background: #6c63ff; }
.stat-card:nth-child(2)::after { background: #3b82f6; }
.stat-card:nth-child(3)::after { background: #f59e0b; }
.stat-card:nth-child(4)::after { background: #22c55e; }
.stat-card:nth-child(5)::after { background: #ef4444; }
.stat-label { font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
.stat-value { font-size: 32px; font-weight: 700; color: #fff; }
.stat-sub { font-size: 12px; color: #6b7280; margin-top: 4px; }
.toolbar { background: #1a1d29; border: 1px solid #2d3148; border-radius: 12px; padding: 16px 20px; margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.toolbar input, .toolbar select { background: #0f1117; border: 1px solid #2d3148; color: #e0e0e0; padding: 8px 12px; border-radius: 8px; font-size: 13px; outline: none; transition: border-color .2s; }
.toolbar input:focus, .toolbar select:focus { border-color: #6c63ff; }
.toolbar input { width: 220px; }
.btn { padding: 8px 16px; border: none; border-radius: 8px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all .2s; display: inline-flex; align-items: center; gap: 6px; }
.btn-primary { background: #6c63ff; color: #fff; }
.btn-primary:hover { background: #5b54e0; }
.btn-danger { background: #ef4444; color: #fff; }
.btn-danger:hover { background: #dc2626; }
.btn-outline { background: transparent; border: 1px solid #2d3148; color: #8b8fa3; }
.btn-outline:hover { border-color: #6c63ff; color: #6c63ff; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.spacer { flex: 1; }
.table-wrap { background: #1a1d29; border: 1px solid #2d3148; border-radius: 12px; overflow: hidden; }
table { width: 100%; border-collapse: collapse; }
thead th { background: #14161f; padding: 12px 16px; text-align: left; font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #2d3148; cursor: pointer; user-select: none; white-space: nowrap; }
thead th:hover { color: #e0e0e0; }
thead th.sorted-asc::after { content: " ▲"; color: #6c63ff; }
thead th.sorted-desc::after { content: " ▼"; color: #6c63ff; }
tbody tr { border-bottom: 1px solid #1e2235; transition: background .15s; }
tbody tr:hover { background: #1e2235; }
tbody td { padding: 10px 16px; font-size: 13px; font-family: "SF Mono", "Fira Code", monospace; }
.score-bar { display: inline-flex; align-items: center; gap: 6px; }
.score-bar-bg { width: 60px; height: 6px; background: #2d3148; border-radius: 3px; overflow: hidden; }
.score-bar-fill { height: 100%; border-radius: 3px; transition: width .3s; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
.tag-http { background: #1e3a5f; color: #60a5fa; }
.tag-https { background: #1a3a2a; color: #4ade80; }
.tag-high { background: #1a3a2a; color: #4ade80; }
.tag-anonymous { background: #3a2a1a; color: #fbbf24; }
.tag-transparent { background: #3a1a1a; color: #f87171; }
.tag-unknown { background: #2d2d3d; color: #6b7280; }
.speed { color: #6b7280; }
.speed.fast { color: #4ade80; }
.speed.medium { color: #fbbf24; }
.speed.slow { color: #f87171; }
.empty { text-align: center; padding: 60px 20px; color: #4b5563; }
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.pagination { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-top: 1px solid #2d3148; }
.pagination-info { font-size: 13px; color: #6b7280; }
.pagination-btns { display: flex; gap: 8px; }
.toast { position: fixed; top: 20px; right: 20px; padding: 12px 20px; border-radius: 8px; font-size: 13px; z-index: 999; animation: slideIn .3s; }
.toast-success { background: #065f46; color: #a7f3d0; border: 1px solid #22c55e; }
.toast-error { background: #7f1d1d; color: #fca5a5; border: 1px solid #ef4444; }
@keyframes slideIn { from { transform: translateX(100px); opacity: 0; } to { transform: none; opacity: 1; } }
.checkbox { width: 16px; height: 16px; accent-color: #6c63ff; cursor: pointer; }
.source-tag { font-size: 11px; color: #6b7280; background: #0f1117; padding: 2px 6px; border-radius: 4px; }
.footer { text-align: center; padding: 20px; color: #4b5563; font-size: 12px; }
</style>
</head>
<body>
<div class="header">
  <h1>⚡ <span>Py</span>ProxyPool</h1>
  <div class="header-right">
    <span class="badge online" id="statusBadge">运行中</span>
    <span class="badge" id="refreshBadge">自动刷新: 关</span>
    <button class="btn btn-outline btn-sm" onclick="toggleAutoRefresh()">⟳ 自动刷新</button>
    <button class="btn btn-primary btn-sm" onclick="triggerCrawl()">🔄 立即采集</button>
  </div>
</div>

<div class="container">
  <!-- 统计卡片 -->
  <div class="stats">
    <div class="stat-card">
      <div class="stat-label">代理总数</div>
      <div class="stat-value" id="statTotal">-</div>
      <div class="stat-sub">数据库中所有代理</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">HTTP 代理</div>
      <div class="stat-value" id="statHttp">-</div>
      <div class="stat-sub">协议: http</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">HTTPS 代理</div>
      <div class="stat-value" id="statHttps">-</div>
      <div class="stat-sub">协议: https</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">平均评分</div>
      <div class="stat-value" id="statAvgScore">-</div>
      <div class="stat-sub">越高越可靠</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">已验证</div>
      <div class="stat-value" id="statVerified">-</div>
      <div class="stat-sub">通过可用性检测</div>
    </div>
  </div>

  <!-- 工具栏 -->
  <div class="toolbar">
    <input type="text" id="searchInput" placeholder="🔍 搜索 IP / 端口 / 来源..." oninput="renderTable()">
    <select id="filterProtocol" onchange="renderTable()">
      <option value="">全部协议</option>
      <option value="http">HTTP</option>
      <option value="https">HTTPS</option>
    </select>
    <select id="filterAnonymity" onchange="renderTable()">
      <option value="">全部匿名</option>
      <option value="high">高匿</option>
      <option value="anonymous">匿名</option>
      <option value="transparent">透明</option>
    </select>
    <select id="filterScore" onchange="renderTable()">
      <option value="0">全部评分</option>
      <option value="5">≥ 5 分</option>
      <option value="8">≥ 8 分</option>
      <option value="10">≥ 10 分</option>
    </select>
    <div class="spacer"></div>
    <button class="btn btn-outline btn-sm" onclick="exportCSV()">📥 导出CSV</button>
    <button class="btn btn-danger btn-sm" onclick="deleteSelected()">🗑 删除选中</button>
    <button class="btn btn-outline btn-sm" onclick="cleanupLowScore()">🧹 清理低分</button>
  </div>

  <!-- 代理表格 -->
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th style="width:40px"><input type="checkbox" class="checkbox" id="selectAll" onchange="toggleSelectAll()"></th>
          <th data-sort="ip" onclick="sortBy('ip')">IP 地址</th>
          <th data-sort="port" onclick="sortBy('port')">端口</th>
          <th data-sort="protocol" onclick="sortBy('protocol')">协议</th>
          <th data-sort="anonymity" onclick="sortBy('anonymity')">匿名</th>
          <th data-sort="country" onclick="sortBy('country')">地区</th>
          <th data-sort="speed" onclick="sortBy('speed')">速度</th>
          <th data-sort="score" onclick="sortBy('score')">评分</th>
          <th data-sort="source" onclick="sortBy('source')">来源</th>
          <th data-sort="last_verified" onclick="sortBy('last_verified')">验证时间</th>
          <th style="width:80px">操作</th>
        </tr>
      </thead>
      <tbody id="proxyTableBody"></tbody>
    </table>
    <div class="empty" id="emptyState" style="display:none">
      <div class="empty-icon">📭</div>
      <div>暂无代理数据</div>
      <div style="margin-top:8px;font-size:12px">点击「立即采集」获取代理</div>
    </div>
    <div class="pagination" id="pagination" style="display:none">
      <div class="pagination-info" id="paginationInfo"></div>
      <div class="pagination-btns">
        <button class="btn btn-outline btn-sm" onclick="prevPage()">← 上一页</button>
        <button class="btn btn-outline btn-sm" onclick="nextPage()">下一页 →</button>
      </div>
    </div>
  </div>
</div>

<div class="footer">PyProxyPool — 融合 proxypool + IPProxyPool 优点的代理池系统</div>

<script>
let allProxies = [];
let sortKey = 'score';
let sortDir = 'desc';
let page = 0;
const pageSize = 50;
let autoRefreshTimer = null;

// ==================== 数据加载 ====================
async function loadStatus() {
  try {
    const r = await fetch('/status');
    const d = await r.json();
    document.getElementById('statTotal').textContent = d.total;
    document.getElementById('statHttp').textContent = d.http;
    document.getElementById('statHttps').textContent = d.https;
    document.getElementById('statusBadge').textContent = '运行中';
    document.getElementById('statusBadge').className = 'badge online';
  } catch(e) {
    document.getElementById('statusBadge').textContent = '离线';
    document.getElementById('statusBadge').className = 'badge';
  }
}

async function loadProxies() {
  try {
    const r = await fetch('/proxy/all');
    const d = await r.json();
    allProxies = d.proxies || [];

    // 计算统计
    const scores = allProxies.map(p => p.score);
    const avg = scores.length ? (scores.reduce((a,b)=>a+b,0)/scores.length).toFixed(1) : '-';
    const verified = allProxies.filter(p => p.last_verified > 0).length;

    document.getElementById('statAvgScore').textContent = avg;
    document.getElementById('statVerified').textContent = verified;

    renderTable();
  } catch(e) {
    console.error('Load failed:', e);
  }
}

function renderTable() {
  const search = document.getElementById('searchInput').value.toLowerCase();
  const proto = document.getElementById('filterProtocol').value;
  const anon = document.getElementById('filterAnonymity').value;
  const minScore = parseInt(document.getElementById('filterScore').value) || 0;

  let filtered = allProxies.filter(p => {
    if (search && !p.ip.includes(search) && !String(p.port).includes(search) && !(p.source||'').toLowerCase().includes(search) && !(p.country||'').toLowerCase().includes(search)) return false;
    if (proto && p.protocol !== proto) return false;
    if (anon && p.anonymity !== anon) return false;
    if (p.score < minScore) return false;
    return true;
  });

  // 排序
  filtered.sort((a, b) => {
    let va = a[sortKey], vb = b[sortKey];
    if (typeof va === 'string') { va = va.toLowerCase(); vb = vb.toLowerCase(); }
    if (va < vb) return sortDir === 'asc' ? -1 : 1;
    if (va > vb) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  // 分页
  const totalPages = Math.ceil(filtered.length / pageSize);
  if (page >= totalPages) page = Math.max(0, totalPages - 1);
  const start = page * pageSize;
  const paged = filtered.slice(start, start + pageSize);

  // 渲染
  const tbody = document.getElementById('proxyTableBody');
  const empty = document.getElementById('emptyState');
  const pag = document.getElementById('pagination');

  if (paged.length === 0) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    pag.style.display = 'none';
    return;
  }
  empty.style.display = 'none';
  pag.style.display = 'flex';

  tbody.innerHTML = paged.map(p => {
    const speedClass = p.speed === 0 ? '' : p.speed < 500 ? 'fast' : p.speed < 2000 ? 'medium' : 'slow';
    const speedText = p.speed === 0 ? '-' : p.speed.toFixed(0) + 'ms';
    const scoreColor = p.score >= 8 ? '#4ade80' : p.score >= 5 ? '#fbbf24' : '#f87171';
    const scorePct = Math.min(p.score * 10, 100);
    const verifiedText = p.last_verified > 0 ? new Date(p.last_verified * 1000).toLocaleString('zh-CN', {hour12:false}) : '-';
    const key = p.ip + ':' + p.port;
    return `<tr>
      <td><input type="checkbox" class="checkbox sel-cb" data-key="${key}"></td>
      <td>${p.ip}</td>
      <td>${p.port}</td>
      <td><span class="tag tag-${p.protocol}">${p.protocol.toUpperCase()}</span></td>
      <td><span class="tag tag-${p.anonymity}">${anonLabel(p.anonymity)}</span></td>
      <td style="font-size:11px;color:#8b8fa3;white-space:nowrap" title="${p.area||''}">${p.country||'-'}</td>
      <td><span class="speed ${speedClass}">${speedText}</span></td>
      <td><div class="score-bar"><span style="color:${scoreColor}">${p.score}</span><div class="score-bar-bg"><div class="score-bar-fill" style="width:${scorePct}%;background:${scoreColor}"></div></div></div></td>
      <td><span class="source-tag">${p.source||'-'}</span></td>
      <td style="font-size:11px;color:#6b7280">${verifiedText}</td>
      <td><button class="btn btn-danger btn-sm" onclick="deleteProxy('${p.ip}',${p.port})">删除</button></td>
    </tr>`;
  }).join('');

  // 更新排序指示
  document.querySelectorAll('thead th[data-sort]').forEach(th => {
    th.classList.remove('sorted-asc', 'sorted-desc');
    if (th.dataset.sort === sortKey) th.classList.add('sorted-' + sortDir);
  });

  // 分页信息
  document.getElementById('paginationInfo').textContent =
    `显示 ${start+1}-${Math.min(start+pageSize, filtered.length)} / 共 ${filtered.length} 条 (筛选自 ${allProxies.length} 条)`;
}

function anonLabel(v) {
  return {high:'高匿', anonymous:'匿名', transparent:'透明', unknown:'未知'}[v] || v;
}

// ==================== 排序 ====================
function sortBy(key) {
  if (sortKey === key) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
  else { sortKey = key; sortDir = 'desc'; }
  page = 0;
  renderTable();
}

// ==================== 分页 ====================
function prevPage() { if (page > 0) { page--; renderTable(); } }
function nextPage() { page++; renderTable(); }

// ==================== 选择 ====================
function toggleSelectAll() {
  const checked = document.getElementById('selectAll').checked;
  document.querySelectorAll('.sel-cb').forEach(cb => cb.checked = checked);
}

function getSelectedKeys() {
  const keys = [];
  document.querySelectorAll('.sel-cb:checked').forEach(cb => keys.push(cb.dataset.key));
  return keys;
}

// ==================== 操作 ====================
async function deleteProxy(ip, port) {
  if (!confirm(`确认删除 ${ip}:${port} ?`)) return;
  try {
    const r = await fetch(`/delete?ip=${ip}&port=${port}`);
    const d = await r.json();
    toast(`已删除 ${d.deleted} 条代理`, 'success');
    loadStatus(); loadProxies();
  } catch(e) { toast('删除失败: ' + e, 'error'); }
}

async function deleteSelected() {
  const keys = getSelectedKeys();
  if (!keys.length) { toast('请先勾选要删除的代理', 'error'); return; }
  if (!confirm(`确认删除选中的 ${keys.length} 条代理?`)) return;
  let deleted = 0;
  for (const key of keys) {
    const [ip, port] = key.split(':');
    try {
      const r = await fetch(`/delete?ip=${ip}&port=${port}`);
      const d = await r.json();
      deleted += d.deleted;
    } catch(e) {}
  }
  toast(`已删除 ${deleted} 条代理`, 'success');
  loadStatus(); loadProxies();
}

async function cleanupLowScore() {
  if (!confirm('确认清理评分低于 2 的代理?')) return;
  try {
    const r = await fetch('/cleanup?min_score=2');
    const d = await r.json();
    toast(`已清理 ${d.deleted} 条低分代理`, 'success');
    loadStatus(); loadProxies();
  } catch(e) { toast('清理失败', 'error'); }
}

async function triggerCrawl() {
  toast('正在触发采集...', 'success');
  try {
    const r = await fetch('/crawl', {method:'POST'});
    const d = await r.json();
    toast(d.message || '采集已触发', 'success');
    setTimeout(() => { loadStatus(); loadProxies(); }, 5000);
  } catch(e) { toast('触发失败', 'error'); }
}

// ==================== 导出 ====================
function exportCSV() {
  const search = document.getElementById('searchInput').value.toLowerCase();
  const proto = document.getElementById('filterProtocol').value;
  let filtered = allProxies.filter(p => {
    if (search && !p.ip.includes(search)) return false;
    if (proto && p.protocol !== proto) return false;
    return true;
  });
  let csv = 'IP,Port,Protocol,Anonymity,Country,ISP,Speed,Score,Source,Verified\n';
  filtered.forEach(p => {
    csv += `${p.ip},${p.port},${p.protocol},${p.anonymity},"${p.country||''}","${p.area||''}",${p.speed},${p.score},${p.source},${p.last_verified}\n`;
  });
  const blob = new Blob([csv], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `proxypool_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  toast(`已导出 ${filtered.length} 条`, 'success');
}

// ==================== 自动刷新 ====================
function toggleAutoRefresh() {
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
    document.getElementById('refreshBadge').textContent = '自动刷新: 关';
  } else {
    autoRefreshTimer = setInterval(() => { loadStatus(); loadProxies(); }, 10000);
    document.getElementById('refreshBadge').textContent = '自动刷新: 10s';
  }
}

// ==================== Toast ====================
function toast(msg, type) {
  const el = document.createElement('div');
  el.className = 'toast toast-' + type;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// ==================== 初始化 ====================
loadStatus();
loadProxies();
</script>
</body>
</html>"""
