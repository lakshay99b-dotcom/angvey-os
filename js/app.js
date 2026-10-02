/* Angvey Agent OS — Demo Frontend */

// Nav scroll effect
const nav = document.getElementById('nav');
window.addEventListener('scroll', () => {
  nav.classList.toggle('scrolled', window.scrollY > 20);
});

// —— Inline demo (landing page) ——
const DEMO_STEPS = [
  { label: 'Understanding intent & assembling context', status: 'Understanding' },
  { label: 'Planning: Goal → Subgoals → Steps', status: 'Planning' },
  { label: 'Checking permissions (READ / WRITE)', status: 'Permissions' },
  { label: 'Calling skill: Research Topic', status: 'Researching' },
  { label: 'Tool: web_search → collecting sources', status: 'Researching' },
  { label: 'Tool: extract_content → evaluating quality', status: 'Researching' },
  { label: 'Cross-checking & synthesizing findings', status: 'Analyzing' },
  { label: 'Creating report document', status: 'Creating' },
  { label: 'Verifying output (structure + sources)', status: 'Verifying' },
  { label: 'Storing task learning in memory', status: 'Learning' },
];

function setDemo(text) {
  document.getElementById('demo-input').value = text;
}

function runDemo() {
  const input = document.getElementById('demo-input');
  const goal = (input.value || '').trim() || 'Research AI agent architectures and create a report';
  document.getElementById('demo-intro').classList.add('hidden');
  document.getElementById('demo-run').classList.remove('hidden');
  document.getElementById('demo-result').classList.add('hidden');
  document.getElementById('demo-goal').textContent = goal;
  document.getElementById('demo-status').textContent = 'Planning…';
  const stepsEl = document.getElementById('demo-steps');
  stepsEl.innerHTML = '';

  let i = 0;
  function next() {
    if (i >= DEMO_STEPS.length) {
      document.getElementById('demo-status').textContent = 'Completed';
      document.getElementById('demo-status').style.color = 'var(--success)';
      const result = document.getElementById('demo-result');
      result.classList.remove('hidden');
      document.getElementById('demo-result-body').innerHTML =
        `Report generated successfully.<br><br>` +
        `<strong>AI Agent Architectures — Summary</strong><br>` +
        `• Layered Agent OS (Orchestrator → Planner → Executor → Observer → Reflector)<br>` +
        `• Model-agnostic provider interface<br>` +
        `• Tool registry + composable skills<br>` +
        `• Memory tiers + failure learning<br>` +
        `• Permission boundaries & secret isolation<br><br>` +
        `File: <code>AI_Agent_Architectures_Report.md</code> · Learning stored for future runs.`;
      return;
    }
    const step = DEMO_STEPS[i];
    document.getElementById('demo-status').textContent = step.status + '…';
    document.getElementById('demo-status').style.color = '';
    const el = document.createElement('div');
    el.className = 'step-item active';
    el.style.animationDelay = '0s';
    el.innerHTML = `<span class="step-icon">⏳</span><span>${step.label}</span>`;
    stepsEl.appendChild(el);
    // mark previous done
    const items = stepsEl.querySelectorAll('.step-item');
    if (items.length > 1) {
      const prev = items[items.length - 2];
      prev.classList.remove('active');
      prev.classList.add('done');
      prev.querySelector('.step-icon').textContent = '✓';
    }
    i++;
    setTimeout(next, 700 + Math.random() * 400);
  }
  next();
}

// —— Full App ——
function openApp() {
  document.getElementById('app-overlay').classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}
function closeApp() {
  document.getElementById('app-overlay').classList.add('hidden');
  document.body.style.overflow = '';
}

// Sidebar navigation
document.querySelectorAll('.app-nav-item').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.app-nav-item').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const view = btn.dataset.view;
    document.querySelectorAll('.app-view').forEach(v => v.classList.remove('active'));
    document.getElementById('view-' + view).classList.add('active');
  });
});

function quickTask(text) {
  document.getElementById('app-input').value = text;
}

const APP_STEPS = [
  { label: 'Intent parsed · Context assembled', phase: 'Understanding' },
  { label: 'Plan created: 6 steps (sequential + parallel research)', phase: 'Planning' },
  { label: 'Permissions checked — READ allowed, WRITE requires confirmation', phase: 'Permissions' },
  { label: 'Skill “Research Topic” invoked', phase: 'Executing' },
  { label: 'web_search(“AI agent architectures 2025–2026”)', phase: 'Tool' },
  { label: 'fetch_webpage + extract_content on top 5 sources', phase: 'Tool' },
  { label: 'Sources ranked · duplicates removed · conflicts flagged', phase: 'Observation' },
  { label: 'Synthesis complete · Draft report structure ready', phase: 'Reflection' },
  { label: 'file_write → AI_Agent_Architectures_Report.md', phase: 'Delivery' },
  { label: 'Verification: file exists, sections present, citations valid', phase: 'Verify' },
  { label: 'Learning stored: preferred report length & source criteria', phase: 'Memory' },
];

function runAppTask() {
  const input = document.getElementById('app-input');
  const goal = (input.value || '').trim() || 'Research AI agent architectures and create a report';
  const live = document.getElementById('app-live');
  live.classList.remove('hidden');
  document.getElementById('app-output').classList.add('hidden');
  document.getElementById('app-task-goal').textContent = goal;
  const statusEl = document.getElementById('app-task-status');
  statusEl.textContent = 'Planning';
  statusEl.style.background = 'var(--accent-soft)';
  statusEl.style.color = 'var(--accent)';
  const timeline = document.getElementById('app-timeline');
  timeline.innerHTML = '';

  let i = 0;
  function next() {
    if (i >= APP_STEPS.length) {
      statusEl.textContent = 'Completed';
      statusEl.style.background = 'rgba(61,214,140,0.15)';
      statusEl.style.color = 'var(--success)';
      // mark last step done
      const items = timeline.querySelectorAll('.step-item');
      if (items.length) {
        const last = items[items.length - 1];
        last.classList.remove('active');
        last.classList.add('done');
        last.querySelector('.step-icon').textContent = '✓';
      }
      const out = document.getElementById('app-output');
      out.classList.remove('hidden');
      document.getElementById('app-output-body').textContent =
        `✓ Report delivered\n\n` +
        `File: AI_Agent_Architectures_Report.md\n` +
        `Sources: 5 evaluated, 4 cited\n` +
        `Verification: structure OK · citations OK\n` +
        `Learning: stored for “Do the same research next week”\n\n` +
        `You can now schedule this as an automation from the Automations tab.`;
      // Add to tasks list
      const list = document.getElementById('tasks-list');
      if (list.querySelector('.empty-state')) list.innerHTML = '';
      const card = document.createElement('div');
      card.className = 'list-card';
      card.innerHTML = `<div class="list-card-title">${goal.slice(0, 60)}${goal.length > 60 ? '…' : ''}</div>
        <div class="list-card-meta">Completed · just now · Model: current provider</div>`;
      list.prepend(card);
      return;
    }
    const step = APP_STEPS[i];
    statusEl.textContent = step.phase;
    const el = document.createElement('div');
    el.className = 'step-item active';
    el.innerHTML = `<span class="step-icon">⏳</span><span>${step.label}</span>`;
    timeline.appendChild(el);
    const items = timeline.querySelectorAll('.step-item');
    if (items.length > 1) {
      const prev = items[items.length - 2];
      prev.classList.remove('active');
      prev.classList.add('done');
      prev.querySelector('.step-icon').textContent = '✓';
    }
    i++;
    setTimeout(next, 650 + Math.random() * 350);
  }
  next();
}

// Escape to close app
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeApp();
});
