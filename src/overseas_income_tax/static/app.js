const state = { documents: [], lastPayload: null, lastResult: null, nextEvent: 1 };
const $ = (selector) => document.querySelector(selector);
const checked = (selector) => $(selector).checked;

function makeInput(label, name, type = "text", value = "") {
  const wrapper = document.createElement("label");
  wrapper.textContent = label;
  const input = document.createElement("input");
  input.name = name;
  input.type = type;
  input.value = value;
  wrapper.append(input);
  return wrapper;
}

function addEvent(defaults = {}) {
  const id = defaults.id || `event-${state.nextEvent++}`;
  const card = document.createElement("article");
  card.className = "event-card";
  card.dataset.id = id;
  card.dataset.revision = "0";
  card.dataset.rejected = "false";
  card.innerHTML = `
    <div class="event-top"><strong>${id}</strong><button type="button" class="secondary remove-event">删除</button></div>
    <div class="event-grid">
      <label>所得类别<select name="category"><option value="interest">利息</option><option value="dividend">普通现金股息</option><option value="capital_gain">资本利得（只整理）</option><option value="complex_product">复杂理财（只整理）</option><option value="other">其他（只整理）</option></select></label>
      <label>来源国家或地区<input name="country" placeholder="例如：美国"></label>
      <label>收入日期<input name="date" type="date"></label>
      <label>币种<input name="currency" value="USD" maxlength="3"></label>
      <label>税前收入<input name="gross" type="number" step="0.01" min="0"></label>
      <label>报表显示扣税<input name="reported-tax" type="number" step="0.01" min="0" value="0"></label>
      <label>符合条件的已缴税<input name="eligible-tax" type="number" step="0.01" min="0" value="0"></label>
      <label>税款币种<input name="tax-currency" value="USD" maxlength="3"></label>
      <label>证据页码<input name="page" type="number" min="1" value="1"></label>
      <label class="wide-field">证据文件<select name="document"><option value="manual">手工录入（需后续补证据）</option></select></label>
      <label class="wide-field">证据位置/原文摘要<input name="locator" placeholder="例如：第2页 Box 2；不要填写完整账号"></label>
      <label class="wide-field">确认或修改原因<input name="reason" value="已与原始材料逐项核对"></label>
    </div>
    <div class="confirmation">
      <label class="check"><input name="confirmed" type="checkbox" checked> 事实已确认</label>
      <label class="check"><input name="source-confirmed" type="checkbox" checked> 来源地已确认</label>
      <label class="check"><input name="nature-confirmed" type="checkbox" checked> 所得性质已确认</label>
      <label class="check"><input name="tax-confirmed" type="checkbox" checked> 境外已缴税已确认</label>
    </div>`;
  card.querySelector('[name="category"]').value = defaults.category || "interest";
  card.querySelector('[name="country"]').value = defaults.country || "";
  card.querySelector('[name="date"]').value = defaults.date || "";
  card.querySelector('.remove-event').addEventListener('click', () => {
    if (card.dataset.rejected === 'true') {
      card.dataset.rejected = 'false';
      card.classList.remove('rejected');
      card.querySelectorAll('input, select').forEach(control => control.disabled = false);
      card.querySelector('.remove-event').textContent = '删除';
    } else {
      const reason = window.prompt('请填写删除原因（会保留在审计记录中）：');
      if (!reason || !reason.trim()) return;
      card.querySelector('[name="reason"]').value = reason.trim();
      card.dataset.rejected = 'true';
      card.classList.add('rejected');
      card.querySelectorAll('input, select').forEach(control => control.disabled = true);
      card.querySelector('.remove-event').disabled = false;
      card.querySelector('.remove-event').textContent = '恢复';
    }
    card.dataset.revision = String(Number(card.dataset.revision) + 1);
    markStale();
  });
  card.addEventListener('change', () => {
    card.dataset.revision = String(Number(card.dataset.revision) + 1);
    markStale();
  });
  $('#events').append(card);
  refreshDocumentOptions();
  markStale();
}

function addRate(currency = "USD") {
  const row = document.createElement("div");
  row.className = "rate-row";
  row.innerHTML = `
    <label>币种<input name="rate-currency" maxlength="3" value="${currency}"></label>
    <label>1 原币 = CNY<input name="rate-value" type="number" step="0.000001" min="0"></label>
    <label>汇率日期<input name="rate-date" type="date"></label>
    <label>官方来源<input name="rate-source" placeholder="人民银行或中国外汇交易中心链接"></label>
    <button type="button" class="secondary remove-rate">删除</button>`;
  row.querySelector('.remove-rate').addEventListener('click', () => { row.remove(); markStale(); });
  row.addEventListener('change', markStale);
  $('#rates').append(row);
}

function refreshDocumentOptions() {
  document.querySelectorAll('[name="document"]').forEach(select => {
    const current = select.value;
    select.replaceChildren(new Option("手工录入（需后续补证据）", "manual"));
    state.documents.forEach(doc => select.add(new Option(doc.file_name, doc.sha256)));
    select.value = [...select.options].some(option => option.value === current) ? current : "manual";
  });
}

async function extractPdf() {
  const file = $('#pdf-file').files[0];
  if (!file) return showError('请选择 PDF 文件。');
  const data = new FormData();
  data.append('file', file);
  $('#extract-button').disabled = true;
  try {
    const response = await fetch('/api/extract', { method: 'POST', body: data });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || '提取失败');
    if (!state.documents.some(doc => doc.sha256 === body.sha256)) state.documents.push(body);
    renderDocuments();
    refreshDocumentOptions();
  } catch (error) { showError(error.message); }
  finally { $('#extract-button').disabled = false; }
}

function renderDocuments() {
  const container = $('#documents');
  container.replaceChildren();
  state.documents.forEach(doc => {
    const box = document.createElement('details');
    box.className = 'document';
    const summary = document.createElement('summary');
    summary.textContent = `${doc.file_name} · ${doc.pages.length} 页`;
    box.append(summary);
    const code = document.createElement('code');
    code.textContent = `SHA-256 ${doc.sha256}`;
    box.append(code);
    doc.pages.forEach(page => {
      const details = document.createElement('details');
      const pageSummary = document.createElement('summary');
      pageSummary.textContent = `第 ${page.page} 页文本`;
      const pre = document.createElement('pre');
      pre.textContent = page.text;
      details.append(pageSummary, pre);
      box.append(details);
    });
    container.append(box);
  });
}

function buildPayload() {
  const observations = [];
  const events = [];
  document.querySelectorAll('.event-card').forEach((card, index) => {
    const id = card.dataset.id;
    const documentId = card.querySelector('[name="document"]').value;
    const doc = state.documents.find(item => item.sha256 === documentId);
    const observationId = `observation-${id}`;
    observations.push({
      id: observationId,
      evidence: {
        document_sha256: doc ? doc.sha256 : `manual-${id}`,
        file_name: doc ? doc.file_name : '手工录入',
        page: Number(card.querySelector('[name="page"]').value || 1),
        locator: card.querySelector('[name="locator"]').value || '待补充证据定位',
        excerpt: '',
      },
      fields: { source: doc ? 'pdf' : 'manual' },
      is_summary_row: false,
    });
    events.push({
      id,
      category: card.querySelector('[name="category"]').value,
      country_or_region: card.querySelector('[name="country"]').value,
      currency: card.querySelector('[name="currency"]').value.toUpperCase(),
      foreign_tax_currency: card.querySelector('[name="tax-currency"]').value.toUpperCase(),
      gross_amount: card.querySelector('[name="gross"]').value,
      foreign_tax_reported: card.querySelector('[name="reported-tax"]').value,
      foreign_tax_eligible: card.querySelector('[name="eligible-tax"]').value,
      occurred_on: card.querySelector('[name="date"]').value,
      evidence_ids: [observationId],
      review_status: card.dataset.rejected === 'true' ? 'rejected' : (card.querySelector('[name="confirmed"]').checked ? 'confirmed' : 'candidate'),
      review_reason: card.querySelector('[name="reason"]').value,
      source_confirmed: card.querySelector('[name="source-confirmed"]').checked,
      nature_confirmed: card.querySelector('[name="nature-confirmed"]').checked,
      foreign_tax_confirmed: card.querySelector('[name="tax-confirmed"]').checked,
      revision: Number(card.dataset.revision),
    });
  });
  const rates = [...document.querySelectorAll('.rate-row')]
    .filter(row => row.querySelector('[name="rate-value"]').value.trim() !== '')
    .map(row => ({
    currency: row.querySelector('[name="rate-currency"]').value.toUpperCase(),
    cny_per_unit: row.querySelector('[name="rate-value"]').value,
    rate_date: row.querySelector('[name="rate-date"]').value,
    quote_unit: 1,
    source: row.querySelector('[name="rate-source"]').value,
    rule_code: 'PIT-REG-32-ANNUAL-BALANCE',
    }));
  return {
    questionnaire: {
      tax_year: Number($('#tax-year').value),
      residency_status: $('#residency').value,
      filing_scenario: $('#filing-scenario').value,
      same_country_other_income_reviewed: checked('#country-reviewed'),
      prior_credit_balance_reviewed: checked('#prior-reviewed'),
      refund_or_correction_reviewed: checked('#refund-reviewed'),
      has_prior_credit_balance: checked('#has-prior'),
      has_refund_or_correction: checked('#has-refund'),
    },
    observations,
    events,
    exchange_rates: rates,
  };
}

function validateConsent() {
  if (![checked('#privacy-consent'), checked('#disclaimer-consent'), checked('#financial-consent')].every(Boolean)) {
    throw new Error('请先完成隐私、免责声明和金融账户信息单独同意。');
  }
}

async function calculate() {
  try {
    validateConsent();
    const payload = buildPayload();
    const response = await fetch('/api/calculate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || '测算失败');
    state.lastPayload = payload;
    state.lastResult = body;
    renderResult(body);
    $('#export-button').disabled = false;
  } catch (error) { showError(error.message); }
}

function cny(value) {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(Number(value));
}

function renderResult(result) {
  const box = $('#result');
  box.classList.remove('hidden');
  box.replaceChildren();
  const heading = document.createElement('h2');
  heading.textContent = '测算结果';
  const status = document.createElement('span');
  const map = {
    final_range_result: ['范围内结果可用', ''],
    range_estimate_with_pending: ['范围内测算，仍有待核验项', 'pending'],
    materials_only: ['仅整理材料', 'blocked'],
  };
  status.className = `result-status ${map[result.status][1]}`;
  status.textContent = map[result.status][0];
  const metrics = document.createElement('div');
  metrics.className = 'metrics';
  [['范围内应纳税所得额', result.taxable_income_cny], ['范围内应纳税额', result.tax_before_credit_cny], ['采用抵免额', result.credit_used_cny], ['范围内预计补税', result.range_supplemental_tax_cny]].forEach(([label, value]) => {
    const item = document.createElement('div');
    item.className = 'metric';
    const small = document.createElement('span'); small.textContent = label;
    const strong = document.createElement('strong'); strong.textContent = cny(value);
    item.append(small, strong); metrics.append(item);
  });
  const note = document.createElement('p');
  note.className = 'muted';
  note.textContent = `规则快照 ${result.rule_snapshot_version} · 计算指纹 ${result.fingerprint.slice(0, 12)}…`;
  box.append(heading, status, metrics, note);
  if (result.pending_items.length) {
    const sub = document.createElement('h3'); sub.textContent = '待核验清单';
    const list = document.createElement('ul'); list.className = 'pending-list';
    result.pending_items.forEach(item => { const li = document.createElement('li'); li.textContent = `${item.blocking ? '阻断' : '提示'} · ${item.event_id ? `${item.event_id} · ` : ''}${item.message}`; list.append(li); });
    box.append(sub, list);
  }
  box.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function showError(message) {
  const box = $('#result');
  box.classList.remove('hidden');
  box.replaceChildren();
  const p = document.createElement('p'); p.className = 'error'; p.textContent = message; box.append(p);
}

function markStale() {
  if (!state.lastResult) return;
  $('#export-button').disabled = true;
  const box = $('#result');
  box.classList.remove('hidden');
  box.replaceChildren();
  const p = document.createElement('p'); p.className = 'error'; p.textContent = '事实或汇率已经变化，旧测算已失效，请重新计算。'; box.append(p);
  state.lastPayload = null; state.lastResult = null;
}

async function exportXlsx() {
  if (!state.lastPayload) return;
  const response = await fetch('/api/export.xlsx', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(state.lastPayload) });
  if (!response.ok) { const body = await response.json(); return showError(body.error || '导出失败'); }
  const blob = await response.blob();
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `境外收入范围内测算_${$('#tax-year').value}.xlsx`;
  link.click(); URL.revokeObjectURL(link.href);
}

$('#add-event').addEventListener('click', () => addEvent());
$('#add-rate').addEventListener('click', () => addRate(''));
$('#extract-button').addEventListener('click', extractPdf);
$('#calculate-button').addEventListener('click', calculate);
$('#export-button').addEventListener('click', exportXlsx);
document.querySelectorAll('input, select').forEach(input => input.addEventListener('change', markStale));
addEvent({ country: '美国' });
addRate('USD');
addRate('HKD');
