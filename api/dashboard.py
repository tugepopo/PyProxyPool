"""
PyProxyPool — 更新 Dashboard 前端 API 调用路径到 /api/v1/
"""

# Dashboard HTML 页面
# 更新 API 调用路径：所有 /stats, /proxy, /export 等路径前缀 /api/v1/
# WebSocket 路径 /ws 保持不变

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PyProxyPool 仪表盘</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        header { display: flex; justify-content: space-between; align-items: center; padding: 20px 0; border-bottom: 1px solid #1e293b; margin-bottom: 20px; }
        header h1 { font-size: 1.5rem; color: #38bdf8; }
        header .badge { background: #1e293b; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; color: #94a3b8; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .stat-card { background: #1e293b; border-radius: 8px; padding: 16px; text-align: center; }
        .stat-card .value { font-size: 1.75rem; font-weight: 700; color: #38bdf8; }
        .stat-card .label { font-size: 0.75rem; color: #64748b; margin-top: 4px; }
        .grade-a { color: #22c55e !important; } .grade-b { color: #3b82f6 !important; }
        .grade-c { color: #f59e0b !important; } .grade-d { color: #ef4444 !important; }
        .section { background: #1e293b; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
        .section h2 { font-size: 1rem; margin-bottom: 12px; color: #94a3b8; }
        table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
        th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #334155; }
        th { color: #64748b; font-weight: 600; }
        tr:hover { background: #334155; }
        .btn { background: #38bdf8; color: #0f172a; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 0.8rem; }
        .btn:hover { background: #7dd3fc; }
        .btn-danger { background: #ef4444; color: white; }
        .btn-success { background: #22c55e; color: #0f172a; }
        .controls { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
        .controls input, .controls select { background: #0f172a; color: #e2e8f0; border: 1px solid #334155; padding: 6px 12px; border-radius: 4px; font-size: 0.8rem; }
        .badge-grade { padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }
        .grade-A { background: #22c55e; color: white; }
        .grade-B { background: #3b82f6; color: white; }
        .grade-C { background: #f59e0b; color: white; }
        .grade-D { background: #ef4444; color: white; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
        .dot-green { background: #22c55e; } .dot-yellow { background: #f59e0b; } .dot-red { background: #ef4444; }
        .chart-bar { display: flex; align-items: end; height: 80px; gap: 4px; margin-top: 8px; }
        .chart-bar .bar { background: #38bdf8; border-radius: 2px 2px 0 0; flex: 1; min-width: 20px; position: relative; }
        .chart-bar .bar .label { position: absolute; bottom: -18px; left: 50%; transform: translateX(-50%); font-size: 0.6rem; color: #64748b; white-space: nowrap; }
        .chart-bar .bar .val { position: absolute; top: -16px; left: 50%; transform: translateX(-50%); font-size: 0.6rem; color: #94a3b8; }
        #log-area { background: #0f172a; border-radius: 4px; padding: 12px; font-family: 'Fira Code', monospace; font-size: 0.75rem; height: 200px; overflow-y: auto; color: #94a3b8; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 1000; justify-content: center; align-items: center; }
        .modal.active { display: flex; }
        .modal-content { background: #1e293b; border-radius: 8px; padding: 24px; max-width: 500px; width: 90%; }
        .modal-content h3 { margin-bottom: 16px; }
        .modal-content textarea { width: 100%; height: 150px; background: #0f172a; color: #e2e8f0; border: 1px solid #334155; border-radius: 4px; padding: 8px; font-family: monospace; font-size: 0.8rem; resize: vertical; }
        .modal-content .btn-row { display: flex; gap: 8px; margin-top: 12px; }
        .toast { position: fixed; bottom: 20px; right: 20px; background: #22c55e; color: white; padding: 8px 16px; border-radius: 4px; font-size: 0.8rem; opacity: 0; transition: opacity 0.3s; }
        .toast.show { opacity: 1; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>&#128270; PyProxyPool 仪表盘</h1>
            <div style="display: flex; gap: 8px; align-items: center;">
                <span id="status-indicator"><span class="status-dot dot-green"></span>运行中</span>
                <span class="badge" id="uptime">运行时间: --</span>
                <button class="btn" onclick="refreshAll()">&#8635; 刷新</button>
                <button class="btn btn-success" onclick="triggerCrawl()">&#9654; 采集</button>
                <button class="btn" onclick="showImportModal()">&#128193; 导入</button>
            </div>
        </header>

        <!-- 统计卡片 -->
        <div class="stats-grid" id="stats-cards">
            <div class="stat-card"><div class="value" id="stat-total">0</div><div class="label">代理总数</div></div>
            <div class="stat-card"><div class="value grade-a" id="stat-grade-a">0</div><div class="label">A 级</div></div>
            <div class="stat-card"><div class="value grade-b" id="stat-grade-b">0</div><div class="label">B 级</div></div>
            <div class="stat-card"><div class="value grade-c" id="stat-grade-c">0</div><div class="label">C 级</div></div>
            <div class="stat-card"><div class="value grade-d" id="stat-grade-d">0</div><div class="label">D 级</div></div>
            <div class="stat-card"><div class="value" id="stat-http">0</div><div class="label">HTTP</div></div>
            <div class="stat-card"><div class="value" id="stat-https">0</div><div class="label">HTTPS</div></div>
            <div class="stat-card"><div class="value" id="stat-socks5">0</div><div class="label">SOCKS5</div></div>
            <div class="stat-card"><div class="value" id="stat-avg-score">0</div><div class="label">平均评分</div></div>
        </div>

        <!-- GeoIP 数据库状态 -->
        <div class="section">
            <h2>&#128269; GeoIP 数据库状态</h2>
            <div class="controls">
                <span id="geoip-source">加载中...</span>
                <span id="geoip-path">-</span>
                <span id="geoip-size">-</span>
                <span id="geoip-mtime">-</span>
                <span id="geoip-available">-</span>
                <button class="btn btn-success" onclick="refreshGeoip()">&#8635; 手动更新</button>
            </div>
        </div>

        <!-- 采集任务进度 -->
        <div class="section">
            <h2>&#128220; 采集任务</h2>
            <div class="controls">
                <span id="crawl-task-id">无活跃任务</span>
                <span id="crawl-progress-bar">--</span>
                <span id="crawl-next" style="margin-left:auto; color:#94a3b8;">--</span>
            </div>
            <!-- 进度条 -->
            <div style="background:#0f172a; border-radius:4px; height:24px; margin:8px 0; overflow:hidden;">
                <div id="crawl-progress-fill" style="height:100%; background:linear-gradient(90deg,#38bdf8,#22c55e); width:0%; transition:width 0.3s; display:flex; align-items:center; justify-content:center; color:#0f172a; font-size:0.75rem; font-weight:600;">0%</div>
            </div>
            <!-- 最近任务列表 -->
            <table>
                <thead><tr><th>任务</th><th>状态</th><th>进度</th><th>有效</th><th>无效</th><th>创建时间</th></tr></thead>
                <tbody id="recent-tasks-tbody"></tbody>
            </table>
        </div>

        <!-- 筛选控制 -->
        <div class="section">
            <h2>&#128269; 代理浏览</h2>
            <div class="controls">
                <input type="text" id="search-ip" placeholder="搜索 IP..." style="width: 200px;">
                <select id="filter-grade"><option value="all">全部等级</option><option value="A">A</option><option value="B">B</option><option value="C">C</option><option value="D">D</option></select>
                <select id="filter-protocol"><option value="all">全部协议</option><option value="http">HTTP</option><option value="https">HTTPS</option><option value="socks5">SOCKS5</option></select>
                <select id="filter-country"><option value="all">全部国家</option></select>
                <input type="number" id="page-size" value="20" min="1" max="100" style="width: 60px;">
                <button class="btn" onclick="loadProxies()">搜索</button>
                <button class="btn btn-success" onclick="exportProxies()">&#128229; 导出</button>
                <span style="margin-left: auto; color: #64748b;" id="pagination-info">第 1 页</span>
            </div>
        </div>

        <!-- 代理列表 -->
        <div class="section">
            <table>
                <thead>
                    <tr>
                        <th>IP</th><th>端口</th><th>协议</th><th>等级</th><th>评分</th>
                        <th>速度</th><th>国家</th><th>ISP</th><th>来源</th><th>操作</th>
                    </tr>
                </thead>
                <tbody id="proxies-tbody"></tbody>
            </table>
        </div>

        <!-- 分布图表 -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
            <div class="section">
                <h2>&#128202; 速度分布</h2>
                <div class="chart-bar" id="speed-chart"></div>
            </div>
            <div class="section">
                <h2>&#128202; 评分分布</h2>
                <div class="chart-bar" id="score-chart"></div>
            </div>
        </div>

        <!-- 来源排行 -->
        <div class="section">
            <h2>&#128220; 来源排行</h2>
            <table>
                <thead><tr><th>来源</th><th>数量</th><th>平均评分</th><th>平均速度</th><th>状态</th></tr></thead>
                <tbody id="sources-tbody"></tbody>
            </table>
        </div>

        <!-- 国家排行 -->
        <div class="section">
            <h2>&#127757; 国家排行</h2>
            <table>
                <thead><tr><th>国家</th><th>数量</th><th>平均评分</th></tr></thead>
                <tbody id="countries-tbody"></tbody>
            </table>
        </div>

        <!-- 日志 -->
        <div class="section">
            <h2>&#128221; 日志</h2>
            <div id="log-area">加载中...</div>
        </div>
    </div>

    <!-- 导入弹窗 -->
    <div class="modal" id="import-modal">
        <div class="modal-content">
            <h3>&#128193; 导入代理</h3>
            <p style="font-size: 0.75rem; color: #64748b; margin-bottom: 8px;">每行一个代理 (ip:port, protocol://ip:port 等)</p>
            <textarea id="import-text" placeholder="1.2.3.4:8080&#10;http://5.6.7.8:3128&#10;socks5://9.10.11.12:1080"></textarea>
            <div class="btn-row">
                <button class="btn btn-success" onclick="importProxies()">导入</button>
                <button class="btn" onclick="closeImportModal()">取消</button>
            </div>
        </div>
    </div>

    <!-- Toast -->
    <div class="toast" id="toast"></div>

    <script>
        const API_BASE = '/api/v1';
        let currentPage = 1;
        let currentFilters = {};
        let ws = null;

        async function api(path, method = 'GET', body = null) {
            const opts = { method, headers: { 'Content-Type': 'application/json' } };
            if (body) opts.body = JSON.stringify(body);
            const resp = await fetch(`${API_BASE}${path}`, opts);
            return resp.json();
        }

        async function loadCrawlProgress() {
            try {
                const data = await api('/stats/crawl-progress');
                
                // 超时检测辅助函数：running 超过 30 分钟未更新 = 标记为已失效
                function isStale(task) {
                    if (task.status !== 'running') return false;
                    const updated = new Date(task.updated_at);
                    const now = new Date();
                    const STALE_SECONDS = 30 * 60; // 30 分钟
                    return (now - updated) / 1000 > STALE_SECONDS;
                }
                
                // 更新当前任务
                if (data.current_task) {
                    const ct = data.current_task;
                    const stale = isStale(ct);
                    document.getElementById('crawl-task-id').textContent = stale ? '任务: ' + ct.task_id + ' (已失效)' : '任务: ' + ct.task_id;
                    const pct = ct.progress_pct || 0;
                    const bar = document.getElementById('crawl-progress-bar');
                    bar.textContent = ct.processed + '/' + ct.total + (stale ? ' ⚠️' : '');
                    const fill = document.getElementById('crawl-progress-fill');
                    fill.style.width = pct + '%';
                    fill.textContent = pct + '%';
                    if (stale) fill.style.background = 'linear-gradient(90deg,#ef4444,#f87171)';
                    else if (pct < 100) fill.style.background = 'linear-gradient(90deg,#38bdf8,#7dd3fc)';
                    else fill.style.background = 'linear-gradient(90deg,#22c55e,#86efac)';
                } else {
                    document.getElementById('crawl-task-id').textContent = '无活跃任务';
                    document.getElementById('crawl-progress-bar').textContent = '--';
                    document.getElementById('crawl-progress-fill').style.width = '0%';
                    document.getElementById('crawl-progress-fill').textContent = '0%';
                }

                // 下次调度
                if (data.next_scheduled && data.next_scheduled.periodic_crawl) {
                    const next = new Date(data.next_scheduled.periodic_crawl);
                    const now = new Date();
                    const diff = Math.round((next - now) / 1000);
                    const h = Math.floor(diff / 3600);
                    const m = Math.floor((diff % 3600) / 60);
                    const s = diff % 60;
                    document.getElementById('crawl-next').textContent =
                        '下次自动采集: ' + next.toLocaleString() + ' (' + (h>0?h+'h':'') + (m>0?m+'m':'') + s+'s后)';
                }

                // 最近任务列表
                const tbody = document.getElementById('recent-tasks-tbody');
                tbody.innerHTML = (data.recent_tasks || []).map(t => {
                    const stale = isStale(t);
                    const statusColor = t.status === 'completed' ? '#22c55e' :
                                       (t.status === 'running' && !stale) ? '#38bdf8' :
                                       t.status === 'running' && stale ? '#ef4444' :
                                       t.status === 'failed' ? '#ef4444' : '#94a3b8';
                    const statusText = stale ? 'running ⚠️' : t.status;
                    const progress = t.total > 0 ? Math.round(t.processed/t.total*100) + '%' : '-';
                    return `<tr>
                        <td>${t.task_id}</td>
                        <td><span style="color:${statusColor}">${statusText}</span></td>
                        <td>${progress}</td>
                        <td>${t.valid||0}</td>
                        <td>${t.invalid||0}</td>
                        <td>${new Date(t.created_at).toLocaleString()}</td>
                    </tr>`;
                }).join('');
            } catch (e) {
                // 静默失败
            }
        }

        async function refreshAll() {
            await Promise.all([loadStats(), loadProxies(), loadSources(), loadCountries(), loadCharts(), loadLogs(), loadGeoipStatus(), loadCrawlProgress()]);
        }

        async function loadStats() {
            const data = await api('/stats');
            document.getElementById('stat-total').textContent = data.total || 0;
            document.getElementById('stat-grade-a').textContent = data.grade_a || 0;
            document.getElementById('stat-grade-b').textContent = data.grade_b || 0;
            document.getElementById('stat-grade-c').textContent = data.grade_c || 0;
            document.getElementById('stat-grade-d').textContent = data.grade_d || 0;
            document.getElementById('stat-http').textContent = data.http || 0;
            document.getElementById('stat-https').textContent = data.https || 0;
            document.getElementById('stat-socks5').textContent = data.socks5 || 0;
            document.getElementById('stat-avg-score').textContent = (data.avg_score || 0).toFixed(1);
            if (data.uptime_human) document.getElementById('uptime').textContent = 'Uptime: ' + data.uptime_human;
        }

        async function loadProxies() {
            const grade = document.getElementById('filter-grade').value;
            const protocol = document.getElementById('filter-protocol').value;
            const pageSize = parseInt(document.getElementById('page-size').value);
            const ip = document.getElementById('search-ip').value;

            let url = `/proxies?page=${currentPage}&page_size=${pageSize}`;
            if (grade !== 'all') url += `&grade=${grade}`;
            if (protocol !== 'all') url += `&protocol=${protocol}`;
            if (ip) url += `&country=${ip}`;

            const data = await api(url);
            const tbody = document.getElementById('proxies-tbody');
            tbody.innerHTML = data.items ? data.items.map(p => `
                <tr>
                    <td>${p.ip}</td><td>${p.port}</td><td>${p.protocol}</td>
                    <td><span class="badge-grade grade-${p.grade || 'D'}">${p.grade || '-'}</span></td>
                    <td>${p.scan_score || p.score}</td>
                    <td>${p.speed ? p.speed + 'ms' : '-'}</td>
                    <td>${p.country || '-'}</td>
                    <td>${p.isp || '-'}</td>
                    <td>${p.source || '-'}</td>
                    <td><button class=\"btn btn-danger\" style=\"padding:2px 8px;font-size:0.7rem;\" onclick=\"deleteProxy('${p.ip}', ${p.port})\">删除</button></td>
                </tr>
            `).join('') : '';

            document.getElementById('pagination-info').textContent = `第 ${data.page} 页，共 ${data.pages} 页`;

            // Update country filter
            const countries = new Set();
            if (data.items) data.items.forEach(p => { if (p.country) countries.add(p.country); });
            const sel = document.getElementById('filter-country');
            sel.innerHTML = '<option value="all">全部国家</option>' + Array.from(countries).sort().map(c => `<option value="${c}">${c}</option>`).join('');
        }

        async function loadSources() {
            const data = await api('/stats/sources');
            const tbody = document.getElementById('sources-tbody');
            tbody.innerHTML = (data || []).slice(0, 10).map(s => `
                <tr><td>${s.source}</td><td>${s.count}</td><td>${s.avg_score}</td><td>${s.avg_speed}ms</td>
                <td>${s.status === 'degraded' ? '<span style="color:#ef4444">降级</span>' : '<span style="color:#22c55e">正常</span>'}</td></tr>
            `).join('');
        }

        async function loadCountries() {
            const data = await api('/stats/countries');
            const tbody = document.getElementById('countries-tbody');
            tbody.innerHTML = (data || []).slice(0, 10).map(c => `
                <tr><td>${c.country}</td><td>${c.count}</td><td>${c.avg_score}</td></tr>
            `).join('');
        }

        async function loadCharts() {
            const speed = await api('/stats/speed-distribution');
            const score = await api('/stats/score-distribution');

            const maxSpeed = Math.max(...Object.values(speed), 1);
            const maxScore = Math.max(...Object.values(score), 1);

            document.getElementById('speed-chart').innerHTML = Object.entries(speed).map(([k, v]) => {
                const h = (v / maxSpeed) * 100;
                return `<div class="bar" style="height:${h}%" title="${k}: ${v}"><div class="val">${v}</div><div class="label">${k}</div></div>`;
            }).join('');

            document.getElementById('score-chart').innerHTML = Object.entries(score).map(([k, v]) => {
                const h = (v / maxScore) * 100;
                return `<div class="bar" style="height:${h}%" title="${k}: ${v}"><div class="val">${v}</div><div class="label">${k}</div></div>`;
            }).join('');
        }

        async function loadLogs() {
            try {
                const resp = await fetch('/logs');
                const text = await resp.text();
                document.getElementById('log-area').textContent = text || '无日志';
            } catch (e) {
                document.getElementById('log-area').textContent = '加载日志失败';
            }
        }

        async function loadGeoipStatus() {
            try {
                const resp = await fetch('/api/admin/geoip/status');
                const data = await resp.json();
                document.getElementById('geoip-source').textContent = '数据源: ' + (data.source || 'geolite2');
                document.getElementById('geoip-path').textContent = '路径: ' + (data.path || '-');
                document.getElementById('geoip-size').textContent = '大小: ' + (data.size_mb || 0).toFixed(1) + ' MB';
                document.getElementById('geoip-mtime').textContent = '更新: ' + (data.mtime_iso || '-');
                document.getElementById('geoip-available').textContent = data.available ? '✅ 可用' : '❌ 不可用';
            } catch (e) {
                document.getElementById('geoip-available').textContent = '❌ 加载失败';
            }
        }

        async function refreshGeoip() {
            if (!confirm('确定要更新 GeoIP 数据库吗？这将下载约 60MB 文件。')) return;
            try {
                const resp = await fetch('/api/admin/geoip/refresh', {method: 'POST'});
                const data = await resp.json();
                showToast(data.message);
                loadGeoipStatus();
            } catch (e) {
                showToast('更新失败');
            }
        }

        async function triggerCrawl() {
            const data = await api('/crawl', 'POST', { batch_size: 500 });
            showToast('采集已触发: ' + data.task_id);
        }

        async function deleteProxy(ip, port) {
            if (!confirm(`确认删除 ${ip}:${port}?`)) return;
            await api(`/proxies/${ip}/${port}`, 'DELETE');
            showToast('已删除');
            loadProxies();
        }

        async function exportProxies() {
            const grade = document.getElementById('filter-grade').value;
            const protocol = document.getElementById('filter-protocol').value;
            const params = new URLSearchParams({ grade: grade !== 'all' ? grade : 'all', protocol: protocol !== 'all' ? protocol : 'all', format: 'json' });
            window.open(`${API_BASE}/export?${params}`);
        }

        function showImportModal() { document.getElementById('import-modal').classList.add('active'); }
        function closeImportModal() { document.getElementById('import-modal').classList.remove('active'); }

        async function importProxies() {
            const text = document.getElementById('import-text').value.trim();
            if (!text) return;
            const lines = text.split('\\n').filter(l => l.trim());
            const result = await api('/proxies', 'POST', lines);
            showToast(result.message || '导入成功');
            closeImportModal();
            refreshAll();
        }

        function showToast(msg) {
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 3000);
        }

        // WebSocket connection for real-time updates
        function connectWS() {
            const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
            ws = new WebSocket(`${protocol}://${location.host}/ws`);
            ws.onopen = () => {
                document.getElementById('status-indicator').innerHTML = '<span class="status-dot dot-green"></span>已连接';
            };
            ws.onclose = () => {
                document.getElementById('status-indicator').innerHTML = '<span class="status-dot dot-yellow"></span>已断开';
                setTimeout(connectWS, 5000);
            };
            ws.onerror = () => {
                document.getElementById('status-indicator').innerHTML = '<span class="status-dot dot-red"></span>错误';
            };
        }

        // Auto-refresh
        setInterval(refreshAll, 30000);

        // Init
        document.addEventListener('DOMContentLoaded', () => {
            refreshAll();
            connectWS();
        });
    </script>
</body>
</html>"""