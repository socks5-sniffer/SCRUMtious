/* SCRUMtious frontend logic.
 *
 * Loaded with `defer` after the vendored marked + DOMPurify bundles, so the
 * DOM is parsed and both libraries are available when this runs. All handlers
 * are attached here (no inline onclick) so the CSP can exclude
 * 'unsafe-inline' from script-src.
 */

// Configure marked
marked.setOptions({ breaks: true, gfm: true });

const AGENT_ORDER = ['business_analyst', 'product_owner', 'lead_developer', 'security_auditor', 'scrum_master'];
let agentOutputs = {};  // raw markdown strings keyed by agent id
let currentIdea = '';
let currentSessionId = null;

function renderMarkdown(markdownText) {
    return DOMPurify.sanitize(marked.parse(markdownText || ''));
}

function toggleOutput(agentId) {
    const el = document.getElementById(`output-${agentId}`);
    el.classList.toggle('visible');
}

function setAgentState(agentId, state) {
    const card = document.getElementById(`card-${agentId}`);
    const pipe = document.getElementById(`pipe-${agentId}`);
    const status = document.getElementById(`status-${agentId}`);

    card.className = `agent-card ${state}`;
    pipe.className = `pipeline-step ${state}`;

    if (state === 'active') {
        status.innerHTML = '<span class="spinner"></span> Working';
        document.getElementById(`output-${agentId}`).classList.add('visible');
        const content = document.getElementById(`output-content-${agentId}`);
        if (!content.dataset.hasOutput) {
            content.innerHTML = '<span style="color:var(--text-dim)">Agent is processing…</span>';
        }
    } else if (state === 'done') {
        status.textContent = 'Complete ✓';
        // Keep output visible — don't auto-collapse
    } else if (state === 'error') {
        status.textContent = 'Error';
    }
}

function updateProgress() {
    const doneCount = AGENT_ORDER.filter(id =>
        document.getElementById(`card-${id}`).classList.contains('done')).length;
    const activeCount = AGENT_ORDER.filter(id =>
        document.getElementById(`card-${id}`).classList.contains('active')).length;
    const pct = ((doneCount + activeCount * 0.5) / AGENT_ORDER.length) * 100;
    document.getElementById('progress-fill').style.width = `${pct}%`;
}

async function startRun() {
    const idea = document.getElementById('idea-input').value.trim();
    if (!idea) return;
    currentIdea = idea;

    const techStack = document.getElementById('tech-stack').value;
    const securityFramework = document.getElementById('security-framework').value;

    const btn = document.getElementById('btn-run');
    btn.disabled = true;

    document.getElementById('error-banner').classList.remove('visible');

    // Reset all agents
    AGENT_ORDER.forEach(id => {
        setAgentState(id, 'waiting');
        const content = document.getElementById(`output-content-${id}`);
        content.innerHTML = 'Waiting for agent output…';
        delete content.dataset.hasOutput;
        document.getElementById(`output-${id}`).classList.remove('visible');
    });
    agentOutputs = {};
    document.getElementById('progress-fill').style.width = '0%';
    document.getElementById('workflow-section').classList.add('visible');
    document.getElementById('retro-section').classList.remove('visible');
    document.getElementById('btn-download-all').classList.remove('visible');
    document.getElementById('btn-download-pdf').classList.remove('visible');

    // Reset HITL panels
    AGENT_ORDER.forEach(id => {
        const hitl = document.getElementById(`hitl-${id}`);
        if (hitl) {
            hitl.classList.remove('visible');
            const approveBtn = document.getElementById(`hitl-btn-${id}`);
            if (approveBtn) { approveBtn.disabled = false; approveBtn.textContent = 'Approve & Continue →'; }
            const edit = document.getElementById(`hitl-edit-${id}`);
            if (edit) edit.value = '';
        }
    });

    try {
        const res = await fetch('/api/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ idea, tech_stack: techStack, security_framework: securityFramework }),
        });

        const data = await res.json();
        if (!res.ok || data.error) {
            showError(data.error || 'Failed to start the sprint.');
            btn.disabled = false;
            return;
        }

        currentSessionId = data.session_id;
        listenToEvents(data.session_id);
    } catch (err) {
        showError('Failed to start the sprint. Check that the server is running.');
        btn.disabled = false;
    }
}

function listenToEvents(sessionId) {
    const evtSource = new EventSource(`/api/stream/${sessionId}`);

    evtSource.onmessage = (event) => {
        const data = JSON.parse(event.data);

        switch (data.type) {
            case 'agent_start':
                setAgentState(data.agent, 'active');
                updateProgress();
                // Hide any open HITL panel for the PREVIOUS agent
                const PREV_IDX = AGENT_ORDER.indexOf(data.agent) - 1;
                if (PREV_IDX >= 0) {
                    const prevHitl = document.getElementById(`hitl-${AGENT_ORDER[PREV_IDX]}`);
                    if (prevHitl) prevHitl.classList.remove('visible');
                }
                document.getElementById(`card-${data.agent}`).scrollIntoView({
                    behavior: 'smooth', block: 'center'
                });
                break;

            case 'agent_complete':
                setAgentState(data.agent, 'done');
                if (data.output) {
                    agentOutputs[data.agent] = data.output;
                    const content = document.getElementById(`output-content-${data.agent}`);
                    content.innerHTML = renderMarkdown(data.output);
                    content.dataset.hasOutput = '1';
                    // Pre-fill HITL edit textarea with agent output
                    const editArea = document.getElementById(`hitl-edit-${data.agent}`);
                    if (editArea) editArea.value = data.output;
                }
                updateProgress();
                // Show approval panel if this agent expects approval
                if (data.needs_approval) {
                    const hitl = document.getElementById(`hitl-${data.agent}`);
                    if (hitl) hitl.classList.add('visible');
                }
                break;

            case 'agent_edited':
                // User submitted an edit — update the rendered output
                if (data.output) {
                    agentOutputs[data.agent] = data.output;
                    const c = document.getElementById(`output-content-${data.agent}`);
                    if (c) c.innerHTML = renderMarkdown(data.output);
                }
                break;

            case 'complete':
                document.getElementById('progress-fill').style.width = '100%';
                showRetro(data.result, data.verdict);
                document.getElementById('btn-run').disabled = false;
                evtSource.close();
                break;

            case 'error':
                // Mark the currently-active agent as errored
                AGENT_ORDER.forEach(id => {
                    if (document.getElementById(`card-${id}`).classList.contains('active')) {
                        setAgentState(id, 'error');
                    }
                });
                showError(data.message || 'An error occurred during the sprint.');
                document.getElementById('btn-run').disabled = false;
                evtSource.close();
                break;
        }
    };

    evtSource.onerror = () => {
        evtSource.close();
        document.getElementById('btn-run').disabled = false;
    };
}

function showRetro(result, verdict) {
    const section = document.getElementById('retro-section');
    const badge = document.getElementById('verdict-badge');
    const content = document.getElementById('retro-content');

    const retroText = agentOutputs['scrum_master'] || result || 'No retrospective output available.';

    verdict = (verdict || 'UNKNOWN').toUpperCase();
    badge.textContent = verdict;
    badge.className = 'verdict-badge ' + verdict.toLowerCase();

    content.innerHTML = renderMarkdown(retroText);

    section.classList.add('visible');
    document.getElementById('btn-download-all').classList.add('visible');
    document.getElementById('btn-download-pdf').classList.add('visible');
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function approveStep(agentId) {
    const btn = document.getElementById(`hitl-btn-${agentId}`);
    const editArea = document.getElementById(`hitl-edit-${agentId}`);
    if (!currentSessionId || !btn) return;

    // Only send an edit payload if the user actually changed the text
    const originalText = agentOutputs[agentId] || '';
    const editedText = editArea ? editArea.value : '';
    const body = {};
    if (editedText && editedText !== originalText) {
        body.edit = editedText;
    }

    btn.disabled = true;
    btn.textContent = 'Continuing…';

    try {
        const res = await fetch(`/api/approve/${currentSessionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const d = await res.json();
            showError(d.error || 'Could not approve step.');
            btn.disabled = false;
            btn.textContent = 'Approve & Continue →';
        }
        // Panel hides itself when 'agent_start' event arrives for the next agent
    } catch (err) {
        showError('Failed to communicate with server.');
        btn.disabled = false;
        btn.textContent = 'Approve & Continue →';
    }
}

function copyOutput(agentId) {
    const raw = agentOutputs[agentId];
    if (!raw) return;
    navigator.clipboard.writeText(raw).then(() => {
        const btn = document.getElementById(`copy-${agentId}`);
        const orig = btn.innerHTML;
        btn.innerHTML = '✓ Copied';
        btn.style.color = 'var(--green)';
        setTimeout(() => { btn.innerHTML = orig; btn.style.color = ''; }, 2000);
    });
}

function downloadPdf() {
    if (!currentSessionId) return;
    window.location.href = `/api/sessions/${currentSessionId}/pdf`;
}

function downloadArtifacts() {
    const agentLabels = {
        business_analyst: '## 📋 Business Analyst – Requirements\n\n',
        product_owner:    '## 🎯 Product Owner – User Story\n\n',
        lead_developer:   '## ⚡ Lead Developer – Implementation\n\n',
        security_auditor: '## 🛡️ Security Auditor – Audit Report\n\n',
        scrum_master:     '## 🔄 Scrum Master – Retrospective\n\n',
    };
    const generatedAtUtc = new Date().toISOString().replace('T', ' ').replace('Z', ' UTC');
    const parts = [`# Scrumtious Sprint Artifacts\n\n**Idea:** ${currentIdea}\n\n**Generated At (UTC):** ${generatedAtUtc}\n\n---\n\n`];
    AGENT_ORDER.forEach(id => {
        if (agentOutputs[id]) {
            parts.push(agentLabels[id] + agentOutputs[id] + '\n\n---\n\n');
        }
    });
    const blob = new Blob([parts.join('')], { type: 'text/markdown' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'scrumtious-artifacts.md';
    a.click();
    URL.revokeObjectURL(a.href);
}

function showError(message) {
    const banner = document.getElementById('error-banner');
    banner.textContent = message;
    banner.classList.add('visible');
}

// ── Event wiring (replaces inline onclick handlers) ─────────────────────────

document.getElementById('btn-run').addEventListener('click', startRun);
document.getElementById('btn-download-all').addEventListener('click', downloadArtifacts);
document.getElementById('btn-download-pdf').addEventListener('click', downloadPdf);

document.querySelectorAll('.agent-card-header[data-agent]').forEach(el => {
    el.addEventListener('click', () => toggleOutput(el.dataset.agent));
});
document.querySelectorAll('.btn-copy[data-agent]').forEach(el => {
    el.addEventListener('click', () => copyOutput(el.dataset.agent));
});
document.querySelectorAll('.btn-approve[data-agent]').forEach(el => {
    el.addEventListener('click', () => approveStep(el.dataset.agent));
});

// Ctrl+Enter to submit
document.getElementById('idea-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        startRun();
    }
});

// Live char counter hint
document.getElementById('idea-input').addEventListener('input', function() {
    const remaining = 2000 - this.value.length;
    if (remaining < 200) {
        this.style.color = remaining < 50 ? 'var(--red)' : 'var(--amber)';
    } else {
        this.style.color = '';
    }
});
