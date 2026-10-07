// Study Guard v2 SPA Frontend Logic

let categories = [];
let selectedCategoryId = null;
let currentMode = 'block';
let sseSource = null;
let categoryChart = null;
let dailyChart = null;
let pollTimer = null;

// Initialize on DOM Ready
document.addEventListener('DOMContentLoaded', () => {
  setupTabs();
  setupModeToggle();
  setupPomodoroToggle();
  setupCategoryModal();
  setupSettingsHandlers();
  
  loadCategories();
  loadStatus();
  loadAnalytics();
  initSSE();

  pollTimer = setInterval(loadStatus, 2000);
});

// -------------------------------------------------------------
// Tabs Navigation
// -------------------------------------------------------------
function setupTabs() {
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      
      btn.classList.add('active');
      const tabId = btn.getAttribute('data-tab');
      document.getElementById(`tab-${tabId}`).classList.add('active');

      if (tabId === 'analytics') {
        loadAnalytics();
      } else if (tabId === 'categories') {
        renderCategoriesTable();
      } else if (tabId === 'settings') {
        loadSettings();
      }
    });
  });
}

// -------------------------------------------------------------
// Category Management & Chips
// -------------------------------------------------------------
async function loadCategories() {
  try {
    const res = await fetch('/api/categories');
    categories = await res.json();
    renderCategoryChips();
    renderCategoriesTable();
  } catch (err) {
    console.error('Failed to load categories:', err);
  }
}

function renderCategoryChips() {
  const container = document.getElementById('category-chips');
  container.innerHTML = '';
  
  if (categories.length === 0) {
    container.innerHTML = '<span class="text-muted">No categories created yet. Click Categories tab to create one.</span>';
    return;
  }

  categories.forEach((cat, index) => {
    const chip = document.createElement('div');
    chip.className = `cat-chip ${selectedCategoryId === cat.id || (!selectedCategoryId && index === 0) ? 'active' : ''}`;
    if (!selectedCategoryId && index === 0) selectedCategoryId = cat.id;

    chip.innerHTML = `
      <span class="chip-dot" style="background-color: ${cat.color || '#6c63ff'}"></span>
      <span>${cat.name}</span>
    `;

    chip.addEventListener('click', () => {
      document.querySelectorAll('.cat-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      selectedCategoryId = cat.id;
    });

    container.appendChild(chip);
  });
}

function renderCategoriesTable() {
  const tbody = document.getElementById('categories-table-body');
  if (!tbody) return;
  tbody.innerHTML = '';

  if (categories.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No categories defined yet.</td></tr>';
    return;
  }

  categories.forEach(cat => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="chip-dot" style="display:inline-block;background-color:${cat.color}"></span></td>
      <td><b>${escapeHtml(cat.name)}</b></td>
      <td class="text-muted">${escapeHtml(cat.description || 'No criteria')}</td>
      <td><span class="badge ${cat.is_productive ? 'allowed' : 'redirected'}">${cat.is_productive ? 'Productive' : 'Distraction'}</span></td>
      <td>
        <button class="btn btn-secondary btn-sm" onclick="editCategory(${cat.id})">Edit</button>
        <button class="btn btn-danger btn-sm" onclick="deleteCategory(${cat.id})">Delete</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function setupCategoryModal() {
  const modal = document.getElementById('category-modal');
  document.getElementById('btn-open-category-modal').addEventListener('click', () => {
    document.getElementById('modal-cat-id').value = '';
    document.getElementById('modal-cat-name').value = '';
    document.getElementById('modal-cat-desc').value = '';
    document.getElementById('modal-cat-color').value = '#6c63ff';
    document.getElementById('modal-cat-productive').value = '1';
    document.getElementById('modal-cat-title').textContent = 'Create Category';
    modal.classList.remove('hidden');
  });

  const closeFn = () => modal.classList.add('hidden');
  document.getElementById('btn-close-cat-modal').addEventListener('click', closeFn);
  document.getElementById('btn-cancel-cat-modal').addEventListener('click', closeFn);

  document.getElementById('btn-save-cat-modal').addEventListener('click', async () => {
    const id = document.getElementById('modal-cat-id').value;
    const name = document.getElementById('modal-cat-name').value.trim();
    const desc = document.getElementById('modal-cat-desc').value.trim();
    const color = document.getElementById('modal-cat-color').value;
    const isProd = document.getElementById('modal-cat-productive').value === '1';

    if (!name) return alert('Category name is required.');

    const payload = { name, description: desc, color, is_productive: isProd };
    try {
      if (id) {
        await fetch(`/api/categories/${id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      } else {
        await fetch('/api/categories', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      }
      closeFn();
      await loadCategories();
    } catch (e) {
      alert('Error saving category: ' + e);
    }
  });
}

window.editCategory = function(id) {
  const cat = categories.find(c => c.id === id);
  if (!cat) return;
  document.getElementById('modal-cat-id').value = cat.id;
  document.getElementById('modal-cat-name').value = cat.name;
  document.getElementById('modal-cat-desc').value = cat.description;
  document.getElementById('modal-cat-color').value = cat.color;
  document.getElementById('modal-cat-productive').value = cat.is_productive ? '1' : '0';
  document.getElementById('modal-cat-title').textContent = 'Edit Category';
  document.getElementById('category-modal').classList.remove('hidden');
};

window.deleteCategory = async function(id) {
  if (!confirm('Are you sure you want to delete this category?')) return;
  await fetch(`/api/categories/${id}`, { method: 'DELETE' });
  await loadCategories();
};

// -------------------------------------------------------------
// Session Controls & Status Polling
// -------------------------------------------------------------
function setupModeToggle() {
  const blockBtn = document.getElementById('btn-mode-block');
  const obsBtn = document.getElementById('btn-mode-observe');
  const desc = document.getElementById('mode-helper-desc');

  blockBtn.addEventListener('click', () => {
    blockBtn.classList.add('active');
    obsBtn.classList.remove('active');
    currentMode = 'block';
    desc.textContent = 'Redirects distracting browser tabs to motivational quote & minimizes other apps.';
  });

  obsBtn.addEventListener('click', () => {
    obsBtn.classList.add('active');
    blockBtn.classList.remove('active');
    currentMode = 'observe';
    desc.textContent = 'Passively observes and logs all activity to database without minimizing or blocking.';
  });

  document.getElementById('btn-start-session').addEventListener('click', startSession);
  document.getElementById('btn-stop-session').addEventListener('click', stopSession);
}

function setupPomodoroToggle() {
  const check = document.getElementById('pomodoro-enable');
  const inputs = document.getElementById('pomodoro-inputs');
  check.addEventListener('change', () => {
    if (check.checked) inputs.classList.remove('hidden');
    else inputs.classList.add('hidden');
  });
}

async function startSession() {
  const cat = categories.find(c => c.id === selectedCategoryId);
  const catName = cat ? cat.name : 'General';
  const customGoal = document.getElementById('custom-goal').value.trim();
  const duration = parseInt(document.getElementById('session-duration').value) || 30;
  const pomo = document.getElementById('pomodoro-enable').checked;
  const pomoStudy = parseInt(document.getElementById('pomo-study').value) || 25;
  const pomoBreak = parseInt(document.getElementById('pomo-break').value) || 5;

  const payload = {
    category_id: selectedCategoryId,
    category_name: catName,
    goal: customGoal || catName,
    mode: currentMode,
    duration_mins: duration,
    pomodoro: pomo,
    pomo_study: pomoStudy,
    pomo_break: pomoBreak
  };

  try {
    const res = await fetch('/api/session/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json();
      return alert('Failed to start session: ' + (err.error || 'Unknown error'));
    }
    loadStatus();
  } catch (err) {
    alert('Error starting session: ' + err);
  }
}

async function stopSession() {
  try {
    await fetch('/api/session/stop', { method: 'POST' });
    loadStatus();
    loadAnalytics();
  } catch (err) {
    alert('Error stopping session: ' + err);
  }
}

async function loadStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    updateUIWithStatus(data);
  } catch (err) {
    console.error('Status fetch error:', err);
  }
}

function updateUIWithStatus(data) {
  const launcherCard = document.getElementById('launcher-card');
  const activeCard = document.getElementById('active-session-card');
  const statusDot = document.getElementById('status-dot');
  const statusLabel = document.getElementById('status-label');
  const timerPreview = document.getElementById('timer-preview');

  if (data.running && data.session) {
    const s = data.session;
    launcherCard.classList.add('hidden');
    activeCard.classList.remove('hidden');

    const mins = Math.floor(s.remaining_secs / 60);
    const secs = s.remaining_secs % 60;
    const timeStr = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

    document.getElementById('active-timer').textContent = timeStr;
    document.getElementById('active-goal-text').textContent = `Studying: ${s.goal}`;
    document.getElementById('active-category-text').textContent = s.category;
    document.getElementById('active-mode-text').textContent = s.mode.toUpperCase();
    document.getElementById('active-blocks-count').textContent = s.blocks_count;
    document.getElementById('active-jev-count').textContent = s.jev_calls;

    if (s.pomodoro && s.pomodoro.is_break) {
      document.getElementById('active-phase-lbl').textContent = 'BREAK';
      statusDot.className = 'status-indicator break';
      statusLabel.textContent = 'Break';
    } else {
      document.getElementById('active-phase-lbl').textContent = 'FOCUS';
      statusDot.className = 'status-indicator focus';
      statusLabel.textContent = 'Focusing';
    }

    timerPreview.textContent = timeStr;
  } else {
    launcherCard.classList.remove('hidden');
    activeCard.classList.add('hidden');
    statusDot.className = 'status-indicator idle';
    statusLabel.textContent = 'Ready';
    timerPreview.textContent = '00:00';
  }
}

// -------------------------------------------------------------
// Live SSE Event Stream
// -------------------------------------------------------------
function initSSE() {
  if (sseSource) sseSource.close();
  sseSource = new EventSource('/api/live');
  
  sseSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'log') {
        appendLiveLog(data);
      } else if (data.type === 'session_end') {
        loadStatus();
        loadAnalytics();
      }
    } catch (e) {}
  };
}

function appendLiveLog(log) {
  const tbody = document.getElementById('live-feed-body');
  if (tbody.children.length === 1 && tbody.children[0].textContent.includes('Awaiting')) {
    tbody.innerHTML = '';
  }

  const tr = document.createElement('tr');
  const d = new Date(log.timestamp);
  const timeStr = d.toTimeString().split(' ')[0];

  let actionBadge = `<span class="badge ${log.action}">${log.action}</span>`;
  let classBadge = `<span class="badge ${log.classification}">${log.classification}</span>`;

  tr.innerHTML = `
    <td>${timeStr}</td>
    <td title="${escapeHtml(log.title)}"><b>${escapeHtml(log.title.length > 40 ? log.title.substring(0, 37) + '...' : log.title)}</b></td>
    <td><small>${escapeHtml(log.pname || 'App')}</small></td>
    <td>${escapeHtml(log.category)}</td>
    <td>${classBadge}</td>
    <td>${actionBadge}</td>
  `;

  tbody.insertBefore(tr, tbody.firstChild);

  // Keep max 30 entries
  while (tbody.children.length > 30) {
    tbody.removeChild(tbody.lastChild);
  }
}

// -------------------------------------------------------------
// Analytics & Charts
// -------------------------------------------------------------
document.getElementById('analytics-timeframe').addEventListener('change', loadAnalytics);

async function loadAnalytics() {
  const days = document.getElementById('analytics-timeframe').value;
  try {
    const res = await fetch(`/api/analytics/overview?days=${days}`);
    const data = await res.json();

    document.getElementById('stat-total-mins').textContent = `${data.total_study_mins} min`;
    document.getElementById('stat-sessions-count').textContent = data.sessions_count;
    document.getElementById('stat-total-blocks').textContent = data.total_blocks;
    document.getElementById('stat-top-category').textContent = data.most_studied || '—';

    renderCategoryChart(data.categories_breakdown);
    renderDailyChart(data.daily_activity);

    // Load past sessions
    const sRes = await fetch('/api/analytics/sessions?limit=20');
    const sData = await sRes.json();
    renderSessionHistory(sData.sessions);
  } catch (e) {
    console.error('Analytics load failed:', e);
  }
}

function renderCategoryChart(items) {
  const ctx = document.getElementById('categoryDoughnutChart').getContext('2d');
  if (categoryChart) categoryChart.destroy();

  const labels = items.map(i => i.name);
  const values = items.map(i => i.mins);
  const colors = items.map(i => i.color || '#6c63ff');

  categoryChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels.length ? labels : ['No Data'],
      datasets: [{
        data: values.length ? values : [1],
        backgroundColor: colors.length ? colors : ['#334155'],
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: '#94a3b8' } }
      }
    }
  });
}

function renderDailyChart(items) {
  const ctx = document.getElementById('dailyBarChart').getContext('2d');
  if (dailyChart) dailyChart.destroy();

  const labels = items.map(i => i.date);
  const values = items.map(i => i.mins);

  dailyChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Minutes Studied',
        data: values,
        backgroundColor: '#6c63ff',
        borderRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: '#94a3b8' }, grid: { display: false } },
        y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' } }
      },
      plugins: {
        legend: { display: false }
      }
    }
  });
}

function renderSessionHistory(sessions) {
  const tbody = document.getElementById('session-history-body');
  tbody.innerHTML = '';
  if (!sessions || sessions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No sessions completed yet.</td></tr>';
    return;
  }

  sessions.forEach(s => {
    const tr = document.createElement('tr');
    const dt = new Date(s.started_at);
    const dateStr = dt.toLocaleDateString() + ' ' + dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const durationMins = Math.round((s.duration_secs || 0) / 60);

    tr.innerHTML = `
      <td>${dateStr}</td>
      <td><b>${escapeHtml(s.category_name || 'General')}</b></td>
      <td>${escapeHtml(s.goal)}</td>
      <td><span class="badge ${s.mode}">${s.mode.toUpperCase()}</span></td>
      <td>${durationMins} mins</td>
      <td>${s.blocks_count}</td>
    `;
    tbody.appendChild(tr);
  });
}

// -------------------------------------------------------------
// Settings, Integrity & Guardian Reporting
// -------------------------------------------------------------
function setupSettingsHandlers() {
  document.getElementById('btn-verify-integrity').addEventListener('click', verifyIntegrity);
  document.getElementById('btn-save-api-key').addEventListener('click', saveApiKey);
  
  const gToggle = document.getElementById('guardian-enable-toggle');
  const gForm = document.getElementById('guardian-settings-form');
  gToggle.addEventListener('change', () => {
    if (gToggle.checked) gForm.classList.remove('hidden');
    else gForm.classList.add('hidden');
  });

  document.getElementById('btn-save-guardian').addEventListener('click', saveGuardianSettings);
  document.getElementById('btn-send-test-report').addEventListener('click', sendGuardianReport);
}

async function verifyIntegrity() {
  const badge = document.getElementById('integrity-badge');
  const details = document.getElementById('integrity-details');
  badge.textContent = 'Verifying...';
  badge.className = 'badge';

  try {
    const res = await fetch('/api/integrity/verify');
    const data = await res.json();
    if (data.ok) {
      badge.textContent = 'VERIFIED';
      badge.className = 'badge ok';
      details.textContent = `All ${data.events_checked} activity events and ${data.sessions_checked} sessions intact.`;
    } else {
      badge.textContent = 'TAMPERED';
      badge.className = 'badge tampered';
      details.textContent = `Anomaly detected at Session #${data.first_tampered_session || '?'} or Event #${data.first_tampered_event || '?'}.`;
    }
  } catch (err) {
    badge.textContent = 'ERROR';
    badge.className = 'badge tampered';
    details.textContent = 'Integrity check could not complete.';
  }
}

async function loadSettings() {
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    
    if (data.guardian && data.guardian.email) {
      document.getElementById('guardian-enable-toggle').checked = true;
      document.getElementById('guardian-settings-form').classList.remove('hidden');
      document.getElementById('guardian-email').value = data.guardian.email || '';
      document.getElementById('guardian-student-name').value = data.guardian.student_name || '';
      document.getElementById('guardian-smtp-host').value = data.guardian.smtp_host || 'smtp.gmail.com';
      document.getElementById('guardian-smtp-port').value = data.guardian.smtp_port || 587;
      document.getElementById('guardian-smtp-user').value = data.guardian.smtp_user || '';
      if (data.guardian.smtp_pass_set) {
        document.getElementById('guardian-smtp-pass').placeholder = '•••••••• (Saved)';
      }
    }
  } catch (e) {}
}

async function saveApiKey() {
  const key = document.getElementById('setting-api-key').value.trim();
  if (!key) return alert('Please enter a valid key.');
  await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: key })
  });
  alert('OpenRouter API key updated successfully.');
  document.getElementById('setting-api-key').value = '';
}

async function saveGuardianSettings() {
  const guardian = {
    email: document.getElementById('guardian-email').value.trim(),
    student_name: document.getElementById('guardian-student-name').value.trim(),
    smtp_host: document.getElementById('guardian-smtp-host').value.trim(),
    smtp_port: parseInt(document.getElementById('guardian-smtp-port').value) || 587,
    smtp_user: document.getElementById('guardian-smtp-user').value.trim(),
    smtp_pass: document.getElementById('guardian-smtp-pass').value.trim()
  };

  await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ guardian })
  });
  alert('Guardian settings saved successfully.');
}

async function sendGuardianReport() {
  if (!confirm('Send 7-day progress report to guardian now?')) return;
  try {
    const res = await fetch('/api/report/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ period_days: 7 })
    });
    const data = await res.json();
    if (data.ok) alert(data.message || 'Report sent successfully!');
    else alert('Failed to send report: ' + (data.error || 'Check SMTP config.'));
  } catch (e) {
    alert('Error sending report: ' + e);
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}