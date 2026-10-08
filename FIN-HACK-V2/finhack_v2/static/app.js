const msg = document.getElementById('msg');
let streamTimer = null;

function show(text) {
  msg.textContent = text;
  msg.style.display = 'block';
  setTimeout(() => msg.style.display = 'none', 2200);
}

async function postReview(button) {
  const r = await fetch('/review', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({transaction_id: button.dataset.id, status: button.dataset.status})
  });
  const j = await r.json();
  if (j.ok) {
    const row = button.closest('tr');
    row.querySelector('.status').textContent = j.status;
    show(`${j.transaction_id}: ${j.status}`);
  } else show(j.error || 'Review failed');
}

document.querySelectorAll('.review,.false,.escalate').forEach(b => b.addEventListener('click', () => postReview(b)));

document.getElementById('uploadForm').addEventListener('submit', async e => {
  e.preventDefault();
  const f = e.currentTarget.querySelector('input').files[0];
  if (!f) return;
  const fd = new FormData(); fd.append('file', f);
  const r = await fetch('/upload', {method:'POST', body:fd});
  const j = await r.json();
  if (j.ok) location.reload(); else show(j.error || 'Upload failed');
});

document.getElementById('loadDemo').addEventListener('click', async () => {
  const r = await fetch('/load-demo', {method:'POST'});
  const j = await r.json();
  if (j.ok) location.reload(); else show(j.error || 'Could not load demo dataset');
});

const search = document.getElementById('search');
const riskFilter = document.getElementById('riskFilter');
function filterRows() {
  const q = search.value.toLowerCase();
  const risk = riskFilter.value;
  document.querySelectorAll('#txnTable tbody tr').forEach(row => {
    const matchText = row.dataset.search.toLowerCase().includes(q);
    const matchRisk = risk === 'ALL' || row.dataset.risk === risk;
    row.style.display = matchText && matchRisk ? '' : 'none';
  });
}
search.addEventListener('input', filterRows); riskFilter.addEventListener('change', filterRows);

const modal = document.getElementById('modal');
const modalContent = document.getElementById('modalContent');
document.getElementById('closeModal').addEventListener('click', () => modal.classList.add('hidden'));
modal.addEventListener('click', e => { if (e.target === modal) modal.classList.add('hidden'); });

document.querySelectorAll('.details').forEach(btn => btn.addEventListener('click', async () => {
  const r = await fetch(`/api/transaction/${encodeURIComponent(btn.dataset.id)}`);
  const j = await r.json();
  if (!j.ok) return show(j.error || 'Transaction not found');
  const t = j.transaction;
  modalContent.innerHTML = `
    <div class="eyebrow">TRANSACTION INVESTIGATION</div>
    <h2>${t.transaction_id}</h2>
    <div class="riskbox ${String(t.risk_level).toLowerCase()}"><b>Risk Score: ${t.risk_score}/100 · ${t.risk_level}</b><div>${t.context_note}</div></div>
    <div class="detail-grid">
      <div class="detail-item"><span>Account</span><b>${t.account_id}</b></div>
      <div class="detail-item"><span>Amount</span><b>₹${Number(t.amount).toLocaleString('en-IN')}</b></div>
      <div class="detail-item"><span>Date / Time</span><b>${t.date} · ${t.time || String(t.hour).padStart(2,'0') + ':00'}</b></div>
      <div class="detail-item"><span>Category</span><b>${t.merchant_category}</b></div>
      <div class="detail-item"><span>Location</span><b>${t.location}</b></div>
      <div class="detail-item"><span>Daily Frequency</span><b>${t.daily_frequency}</b></div>
    </div>
    <h3>Why FIN-HACK flagged it</h3><ul>${t.reasons.map(x => `<li>${x}</li>`).join('')}</ul>
    <p><b>Current review:</b> ${t.review.status}</p>
    <small>AI assists. Accountant decides.</small>`;
  modal.classList.remove('hidden');
}));

const streamButton = document.getElementById('streamToggle');
const streamStatus = document.getElementById('streamStatus');
async function streamOnce() {
  try {
    const r = await fetch('/api/stream/next');
    const j = await r.json();
    if (!j.ok) return;
    const t = j.transaction;
    show(`SIMULATED: ${t.transaction_id} → ${t.risk_level} (${t.risk_score}/100)`);
  } catch (_) { show('Simulated stream unavailable'); }
}
streamButton.addEventListener('click', () => {
  if (streamTimer) {
    clearInterval(streamTimer); streamTimer = null;
    streamButton.textContent = '▶ Start Simulated Demo Stream'; streamStatus.textContent = 'Stopped';
  } else {
    streamOnce(); streamTimer = setInterval(streamOnce, 2500);
    streamButton.textContent = '■ Stop Simulated Demo Stream'; streamStatus.textContent = 'Running · synthetic only';
  }
});
