const state = { documents: [], auditReviews: {}, lastPayload: null, lastResult: null, nextEvent: 1 };
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
  if (defaults.candidate) card.classList.add("candidate");
  card.dataset.id = id;
  card.dataset.revision = String(defaults.revision || 0);
  card.dataset.rejected = "false";
  card.dataset.excerpt = defaults.excerpt || "";
  card.dataset.amendmentKey = defaults.amendmentKey || "";
  card._extractedFields = defaults.extractedFields || {};
  card.innerHTML = `
    <div class="event-top"><strong>${id}${defaults.candidate ? '<span class="candidate-badge">待确认候选值</span>' : ''}</strong><button type="button" class="secondary remove-event">删除</button></div>
    <div class="event-grid">
      <label>所得类别<select name="category"><option value="interest">利息</option><option value="dividend">普通现金股息</option><option value="capital_gain">资本利得（只整理）</option><option value="complex_product">复杂理财（只整理）</option><option value="other">其他（只整理）</option></select></label>
      <label>来源国家或地区<input name="country" placeholder="例如：美国"></label>
      <label>收入日期<input name="date" type="date"></label>
      <label>币种<input name="currency" value="USD" maxlength="3"></label>
      <label>税前收入<input name="gross" type="number" step="0.01" min="0"></label>
      <label>报表显示扣税<input name="reported-tax" type="number" step="0.01" min="0"></label>
      <label>符合条件的已缴税<input name="eligible-tax" type="number" step="0.01" min="0"></label>
      <label>税款币种<input name="tax-currency" value="USD" maxlength="3"></label>
      <label>证据页码<input name="page" type="number" min="1" value="1"></label>
      <label class="wide-field">证据文件<select name="document"><option value="manual">手工录入（需后续补证据）</option></select></label>
      <label class="wide-field">证据位置/原文摘要<input name="locator" placeholder="例如：第2页 Box 2；不要填写完整账号"></label>
      <label class="wide-field">确认或修改原因<input name="reason" value="${defaults.candidate ? '规则自动预填，待人工核对' : ''}"></label>
    </div>
    <div class="confirmation">
      <label class="check"><input name="confirmed" type="checkbox"> 事实已确认</label>
      <label class="check"><input name="source-confirmed" type="checkbox"> 来源地已确认</label>
      <label class="check"><input name="nature-confirmed" type="checkbox"> 所得性质已确认</label>
      <label class="check"><input name="tax-confirmed" type="checkbox"> 可抵免境外税款已确认</label>
      <label class="check"><input name="summary-row" type="checkbox"> 汇总凭证，不重复计税</label>
    </div>`;
  card.querySelector('[name="category"]').value = defaults.category || "interest";
  card.querySelector('[name="country"]').value = defaults.country || "";
  card.querySelector('[name="date"]').value = defaults.date || "";
  const fallbackCurrency = defaults.candidate ? "" : "USD";
  card.querySelector('[name="currency"]').value = defaults.currency ?? fallbackCurrency;
  card.querySelector('[name="tax-currency"]').value = defaults.taxCurrency ?? defaults.currency ?? fallbackCurrency;
  card.querySelector('[name="gross"]').value = defaults.gross ?? "";
  card.querySelector('[name="reported-tax"]').value = defaults.reportedTax ?? "";
  card.querySelector('[name="eligible-tax"]').value = defaults.eligibleTax ?? "";
  card.querySelector('[name="page"]').value = defaults.page || 1;
  card.querySelector('[name="locator"]').value = defaults.locator || "";
  card.querySelector('[name="reason"]').value = defaults.reason || (defaults.candidate ? "规则自动预填，待人工核对" : "");
  card.querySelector('[name="summary-row"]').checked = Boolean(defaults.summaryRow);
  if (defaults.summaryRecommended) {
    const summaryLabel = card.querySelector('[name="summary-row"]').closest('label');
    summaryLabel.classList.add('needs-review');
    summaryLabel.title = '检测到汇总表。若已上传覆盖同一收入的逐笔明细，请勾选以避免重复计税。';
  }
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
    delete state.auditReviews[id];
    card.dataset.revision = String(Number(card.dataset.revision) + 1);
    markStale();
  });
  card.addEventListener('change', () => {
    delete state.auditReviews[id];
    card.dataset.revision = String(Number(card.dataset.revision) + 1);
    if (card.classList.contains('candidate')) {
      const reason = card.querySelector('[name="reason"]');
      if (!reason.value || reason.value === '规则自动预填，待人工核对') reason.value = '已人工核对或修改自动预填值';
      updateCandidateState(card);
    }
    markStale();
  });
  $('#events').append(card);
  refreshDocumentOptions();
  if (defaults.document) card.querySelector('[name="document"]').value = defaults.document;
  applyFieldMetadata(card, defaults.fieldMeta || {});
  markStale();
}

function applyFieldMetadata(card, metadata) {
  const mapping = {
    category: 'category', country_or_region: 'country', currency: 'currency',
    foreign_tax_currency: 'tax-currency', gross_amount: 'gross',
    foreign_tax_reported: 'reported-tax', foreign_tax_eligible: 'eligible-tax',
    occurred_on: 'date',
  };
  Object.entries(mapping).forEach(([field, name]) => {
    const meta = metadata[field];
    const input = card.querySelector(`[name="${name}"]`);
    if (!meta || !input) return;
    const label = input.closest('label');
    if (meta.confidence !== 'high' || meta.value === null || meta.value === '') label.classList.add('needs-review');
    const note = document.createElement('span');
    note.className = 'field-reason';
    note.textContent = `${meta.confidence === 'high' ? '高' : meta.confidence === 'medium' ? '中' : '低'}置信度 · ${meta.reason}`;
    label.append(note);
  });
}

function updateCandidateState(card) {
  const confirmed = ['confirmed', 'source-confirmed', 'nature-confirmed', 'tax-confirmed']
    .every(name => card.querySelector(`[name="${name}"]`).checked);
  if (confirmed) {
    card.classList.remove('candidate');
    const badge = card.querySelector('.candidate-badge');
    if (badge) badge.textContent = '已人工确认';
  }
}

function confirmReadyCandidates() {
  document.querySelectorAll('.event-card:not(.rejected)').forEach(card => {
    const required = ['country', 'currency', 'gross', 'reported-tax', 'eligible-tax', 'tax-currency'];
    if (!required.every(name => card.querySelector(`[name="${name}"]`).value.trim() !== '')) return;
    ['confirmed', 'source-confirmed', 'nature-confirmed', 'tax-confirmed'].forEach(name => {
      card.querySelector(`[name="${name}"]`).checked = true;
    });
    card.querySelector('[name="reason"]').value = '批量核对材料后确认自动预填值';
    updateCandidateState(card);
  });
  markStale();
}

function adoptReportedTax() {
  const accepted = window.confirm('仅当你已核对这些扣税确为实际缴纳的所得税，且不属于错征、可退或税收协定下不应征收的税款时继续。是否将已匹配的报表扣税批量填入“符合条件的已缴税”？');
  if (!accepted) return;
  document.querySelectorAll('.event-card:not(.rejected)').forEach(card => {
    const category = card.querySelector('[name="category"]').value;
    const reported = card.querySelector('[name="reported-tax"]').value;
    const eligible = card.querySelector('[name="eligible-tax"]');
    if (!['interest', 'dividend'].includes(category) || reported === '' || eligible.value !== '') return;
    eligible.value = reported;
    card.querySelector('[name="tax-confirmed"]').checked = true;
    card.querySelector('[name="reason"]').value = '用户批量确认采用已匹配的报表扣税';
    updateCandidateState(card);
  });
  markStale();
}

function markFormSummaries() {
  const accepted = window.confirm('仅当逐笔明细已经完整覆盖同一收入时继续。标记后，1042-S 只用于勾稽，不会与逐笔明细重复计税。');
  if (!accepted) return;
  document.querySelectorAll('.event-card:not(.rejected)').forEach(card => {
    if (card._extractedFields?.aggregation_level !== 'form_summary') return;
    card.querySelector('[name="summary-row"]').checked = true;
    card.querySelector('[name="reason"]').value = '用户确认该表单只作汇总勾稽凭证';
  });
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
  row.addEventListener('change', () => {
    delete row.dataset.referenceManaged;
    markStale();
  });
  $('#rates').append(row);
  return row;
}

async function loadReferenceRates() {
  const taxYear = Number($('#tax-year').value);
  document.querySelectorAll('.rate-row[data-reference-managed="true"]').forEach(row => {
    row.querySelector('[name="rate-value"]').value = '';
    row.querySelector('[name="rate-date"]').value = '';
    row.querySelector('[name="rate-source"]').value = '';
    delete row.dataset.referenceManaged;
  });
  try {
    const response = await fetch(`/api/v1/reference-rates/${taxYear}`);
    if (!response.ok) return;
    const body = await response.json();
    body.rates.forEach(rate => {
      let row = [...document.querySelectorAll('.rate-row')]
        .find(candidate => candidate.querySelector('[name="rate-currency"]').value.toUpperCase() === rate.currency);
      if (!row) row = addRate(rate.currency);
      if (row.querySelector('[name="rate-value"]').value.trim()) return;
      row.querySelector('[name="rate-value"]').value = rate.cny_per_unit;
      row.querySelector('[name="rate-date"]').value = rate.rate_date;
      row.querySelector('[name="rate-source"]').value = rate.source;
      row.dataset.referenceManaged = 'true';
    });
  } catch (_) {
    // Offline use remains available; unresolved rates stay visibly blank.
  }
}

function refreshDocumentOptions() {
  document.querySelectorAll('[name="document"]').forEach(select => {
    const current = select.value;
    select.replaceChildren(new Option("手工录入（需后续补证据）", "manual"));
    const seen = new Set();
    state.documents.filter(doc => doc.sha256 && !seen.has(doc.sha256) && seen.add(doc.sha256))
      .forEach(doc => select.add(new Option(doc.file_name, doc.sha256)));
    select.value = [...select.options].some(option => option.value === current) ? current : "manual";
  });
}

async function extractPdfs() {
  const files = [...$('#pdf-file').files];
  if (!files.length) return showError('请选择至少一个 PDF 文件。');
  const existingHashes = new Set(state.documents.filter(item => item.sha256).map(item => item.sha256));
  const placeholders = files.map((file, index) => ({
    localId: `${Date.now()}-${index}`,
    file_name: file.name,
    status: 'processing',
    pages: [],
    warnings: [],
  }));
  state.documents.push(...placeholders);
  renderDocuments();
  $('#upload-status').textContent = `正在识别 ${files.length} 个文件…`;
  $('#extract-button').disabled = true;

  await Promise.all(files.map(async (file, index) => {
    const entry = placeholders[index];
    const data = new FormData();
    data.append('file', file);
    try {
      const response = await fetch('/api/v1/extract', { method: 'POST', body: data });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || '识别失败');
      Object.assign(entry, body, {
        status: body.recognition.status,
        warnings: body.recognition.warnings || [],
      });
      if (existingHashes.has(body.sha256)) {
        entry.status = 'duplicate';
        entry.warnings = ['检测到内容完全相同的文件，本次未重复生成候选事项。'];
        return;
      }
      existingHashes.add(body.sha256);
      if (body.recognition.tax_year?.value) $('#tax-year').value = body.recognition.tax_year.value;
      body.recognition.events.forEach(candidate => addCandidateEvent(candidate, body));
    } catch (error) {
      entry.status = 'failed';
      entry.error = error.message;
    } finally {
      renderDocuments();
      refreshDocumentOptions();
    }
  }));

  const recognized = placeholders.filter(item => item.status === 'recognized').length;
  const review = placeholders.filter(item => ['needs_manual_review', 'duplicate'].includes(item.status)).length;
  const failed = placeholders.filter(item => item.status === 'failed').length;
  $('#upload-status').textContent = `处理完成：${recognized} 个已生成候选值，${review} 个需人工核对，${failed} 个失败。`;
  $('#extract-button').disabled = false;
  $('#pdf-file').value = '';
  await loadReferenceRates();
}

function addCandidateEvent(candidate, documentInfo) {
  const value = name => candidate[name]?.value ?? '';
  const aggregationLevel = candidate.extracted_fields?.aggregation_level || '';
  addEvent({
    id: candidate.id,
    candidate: true,
    category: value('category'),
    country: value('country_or_region'),
    currency: value('currency'),
    taxCurrency: value('foreign_tax_currency'),
    gross: value('gross_amount'),
    reportedTax: value('foreign_tax_reported'),
    eligibleTax: value('foreign_tax_eligible'),
    date: value('occurred_on'),
    document: documentInfo.sha256,
    page: candidate.evidence.page,
    locator: candidate.evidence.locator,
    excerpt: candidate.evidence.excerpt,
    amendmentKey: candidate.amendment_key,
    revision: candidate.revision,
    extractedFields: candidate.extracted_fields,
    summaryRecommended: aggregationLevel === 'form_summary',
    fieldMeta: candidate,
  });
}

function recognitionLabel(status) {
  return {
    processing: ['识别中', 'processing'],
    recognized: ['已生成候选值', 'recognized'],
    needs_manual_review: ['需人工核对', 'review'],
    duplicate: ['重复文件', 'review'],
    failed: ['识别失败', 'failed'],
  }[status] || ['待处理', 'processing'];
}

function renderDocuments() {
  const container = $('#documents');
  container.replaceChildren();
  state.documents.forEach(doc => {
    const box = document.createElement('details');
    box.className = 'document';
    const summary = document.createElement('summary');
    const [statusText, statusClass] = recognitionLabel(doc.status);
    const head = document.createElement('span');
    head.className = 'document-head';
    const name = document.createElement('strong');
    name.textContent = `${doc.file_name}${doc.pages?.length ? ` · ${doc.pages.length} 页` : ''}`;
    const status = document.createElement('span');
    status.className = `document-status ${statusClass}`;
    status.textContent = statusText;
    head.append(name, status);
    summary.append(head);
    box.append(summary);
    if (doc.sha256) {
      const code = document.createElement('code');
      code.textContent = `SHA-256 ${doc.sha256}`;
      box.append(code);
    }
    if (doc.recognition) {
      const type = document.createElement('p');
      type.className = 'muted';
      type.textContent = `材料类型：${doc.recognition.document_type.value} · 税年：${doc.recognition.tax_year.value || '未识别'}`;
      box.append(type);
    }
    (doc.warnings || []).forEach(message => {
      const warning = document.createElement('p');
      warning.className = 'document-warning';
      warning.textContent = message;
      box.append(warning);
    });
    if (doc.error) {
      const error = document.createElement('p');
      error.className = 'error';
      error.textContent = doc.error;
      box.append(error);
    }
    (doc.pages || []).forEach(page => {
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
        excerpt: card.dataset.excerpt || '',
      },
      fields: { source: doc ? 'pdf_rule_candidate' : 'manual', ...card._extractedFields },
      is_summary_row: card.querySelector('[name="summary-row"]').checked,
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
      amendment_key: card.dataset.amendmentKey || null,
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
    audit_reviews: Object.values(state.auditReviews),
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
    const response = await fetch('/api/v1/calculate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
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
  appendDerivations(box, result);
  appendRandomAudit(box, result);
  box.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function appendDerivations(box, result) {
  const section = document.createElement('section');
  section.className = 'derivations';
  const heading = document.createElement('h3');
  heading.textContent = '数字出处与计算推导';
  section.append(heading);
  result.event_derivations.forEach(item => {
    const details = document.createElement('details');
    details.className = 'derivation';
    const summary = document.createElement('summary');
    summary.textContent = `${item.event_id} · ${cny(item.gross_cny)}`;
    const list = document.createElement('dl');
    [
      ['来源', `${item.file_name} · 第 ${item.page} 页 · ${item.locator}`],
      ['原文', item.excerpt || '未保存原文片段'],
      ['换算', item.formula],
      ['汇率', `${item.rate_date} · ${item.rate_source}`],
      ['报表扣税', `${item.foreign_tax_reported} ${item.foreign_tax_currency} → ${cny(item.foreign_tax_reported_cny)}`],
      ['确认可抵免', `${item.foreign_tax_eligible} ${item.foreign_tax_currency} → ${cny(item.foreign_tax_eligible_cny)}`],
    ].forEach(([term, description]) => {
      const dt = document.createElement('dt'); dt.textContent = term;
      const dd = document.createElement('dd'); dd.textContent = description;
      list.append(dt, dd);
    });
    details.append(summary, list);
    section.append(details);
  });
  result.country_credit_accounts.forEach(account => {
    const details = document.createElement('details');
    details.className = 'derivation';
    const summary = document.createElement('summary');
    summary.textContent = `${account.country_or_region} · 分国抵免 ${cny(account.credit_used_cny)}`;
    const paragraph = document.createElement('p');
    paragraph.textContent = `min(符合条件已缴税 ${cny(account.eligible_foreign_tax_cny)}, 抵免限额 ${cny(account.credit_limit_cny)}) = ${cny(account.credit_used_cny)}`;
    details.append(summary, paragraph); section.append(details);
  });
  result.summary_derivations.forEach(item => {
    const details = document.createElement('details');
    details.className = 'derivation';
    const summary = document.createElement('summary');
    summary.textContent = `${item.label} · ${cny(item.result_cny)}`;
    const paragraph = document.createElement('p'); paragraph.textContent = item.formula;
    details.append(summary, paragraph); section.append(details);
  });
  box.append(section);
}

function randomSample(items, limit) {
  const copy = [...items];
  for (let index = copy.length - 1; index > 0; index -= 1) {
    const random = new Uint32Array(1);
    crypto.getRandomValues(random);
    const target = random[0] % (index + 1);
    [copy[index], copy[target]] = [copy[target], copy[index]];
  }
  return copy.slice(0, Math.min(limit, copy.length));
}

function appendRandomAudit(box, result) {
  if (!result.event_derivations.length) return;
  const audit = document.createElement('section');
  audit.className = 'audit-box';
  const heading = document.createElement('h3'); heading.textContent = '随机抽检原件';
  const intro = document.createElement('p');
  intro.textContent = '请随机核对以下事项。标记不一致后，该事项会退回待确认并使当前结果失效。';
  audit.append(heading, intro);
  randomSample(result.event_derivations, 3).forEach(item => {
    const row = document.createElement('div'); row.className = 'audit-item';
    const description = document.createElement('div');
    description.textContent = `${item.event_id} · ${item.file_name} 第 ${item.page} 页 · ${item.formula}`;
    const actions = document.createElement('div'); actions.className = 'audit-actions';
    const consistent = document.createElement('button'); consistent.type = 'button'; consistent.className = 'secondary'; consistent.textContent = '与原件一致';
    const inconsistent = document.createElement('button'); inconsistent.type = 'button'; inconsistent.className = 'secondary'; inconsistent.textContent = '不一致';
    consistent.addEventListener('click', () => {
      state.auditReviews[item.event_id] = { event_id: item.event_id, status: 'consistent', note: '' };
      if (state.lastPayload) state.lastPayload.audit_reviews = Object.values(state.auditReviews);
      description.textContent += ' · 已记录一致';
      consistent.disabled = true; inconsistent.disabled = true;
    });
    inconsistent.addEventListener('click', () => {
      const note = window.prompt('请说明不一致之处：');
      if (!note || !note.trim()) return;
      state.auditReviews[item.event_id] = { event_id: item.event_id, status: 'inconsistent', note: note.trim() };
      const card = [...document.querySelectorAll('.event-card')].find(candidate => candidate.dataset.id === item.event_id);
      if (card) {
        card.querySelector('[name="confirmed"]').checked = false;
        card.querySelector('[name="reason"]').value = `随机抽检不一致：${note.trim()}`;
        card.dataset.revision = String(Number(card.dataset.revision) + 1);
        card.classList.add('candidate');
      }
      markStale();
    });
    actions.append(consistent, inconsistent); row.append(description, actions); audit.append(row);
  });
  box.append(audit);
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
  const response = await fetch('/api/v1/export.xlsx', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(state.lastPayload) });
  if (!response.ok) { const body = await response.json(); return showError(body.error || '导出失败'); }
  const blob = await response.blob();
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `境外收入范围内测算_${$('#tax-year').value}.xlsx`;
  link.click(); URL.revokeObjectURL(link.href);
}

$('#add-event').addEventListener('click', () => addEvent());
$('#confirm-ready').addEventListener('click', confirmReadyCandidates);
$('#adopt-reported-tax').addEventListener('click', adoptReportedTax);
$('#mark-form-summaries').addEventListener('click', markFormSummaries);
$('#add-rate').addEventListener('click', () => addRate(''));
$('#extract-button').addEventListener('click', extractPdfs);
$('#calculate-button').addEventListener('click', calculate);
$('#export-button').addEventListener('click', exportXlsx);
const dropZone = $('#drop-zone');
['dragenter', 'dragover'].forEach(type => dropZone.addEventListener(type, event => {
  event.preventDefault();
  dropZone.classList.add('dragging');
}));
['dragleave', 'drop'].forEach(type => dropZone.addEventListener(type, event => {
  event.preventDefault();
  dropZone.classList.remove('dragging');
}));
dropZone.addEventListener('drop', event => {
  const transfer = new DataTransfer();
  [...event.dataTransfer.files].forEach(file => transfer.items.add(file));
  $('#pdf-file').files = transfer.files;
  extractPdfs();
});
document.querySelectorAll('input, select').forEach(input => input.addEventListener('change', markStale));
addRate('USD');
addRate('HKD');
$('#tax-year').addEventListener('change', loadReferenceRates);
loadReferenceRates();
