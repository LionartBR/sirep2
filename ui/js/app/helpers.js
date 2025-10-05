export function registerHelperModule(context) {
  const {
    statusText,
    currencyFormatter,
    runningPlanNumberEl,
    runningPlanDocumentEl,
    runningPlanCompanyEl,
    runningPlanStatusEl,
    runningPlanStageEl,
    lblLastUpdate,
    lblLastDuration,
  } = context;

  context.setStatus = (text) => {
    if (!statusText) {
      return;
    }
    const value = text && String(text).trim() ? String(text).trim() : '—';
    statusText.textContent = value;
  };

  const formatStatusLabel = (value) => {
    if (!value) {
      return '—';
    }
    const text = String(value).trim();
    if (!text) {
      return '—';
    }
    return text.replace(/_/g, ' ');
  };

  const formatDaysValue = (value) => {
    if (value === null || value === undefined) {
      return '—';
    }
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return '—';
    }
    return String(Math.max(0, Math.trunc(number)));
  };

  const formatCurrencyValue = (value) => {
    if (value === null || value === undefined) {
      return '—';
    }
    const number = typeof value === 'number' ? value : Number(value);
    if (!Number.isFinite(number)) {
      return '—';
    }
    try {
      return currencyFormatter.format(number);
    } catch (error) {
      console.warn('Falha ao formatar valor monetário.', error);
      return number.toFixed(2);
    }
  };

  const formatDateLabel = (value) => {
    if (!value) {
      return '—';
    }
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
      return value.toLocaleDateString('pt-BR');
    }
    const text = String(value).trim();
    if (!text) {
      return '—';
    }
    const isoMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (isoMatch) {
      const [, year, month, day] = isoMatch;
      return `${day}/${month}/${year}`;
    }
    const parsed = new Date(text);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed.toLocaleDateString('pt-BR');
    }
    return text;
  };

  const formatDurationLabel = (value) => {
    if (value === null || value === undefined) {
      return null;
    }
    const text = String(value).trim();
    if (!text) {
      return null;
    }
    const parts = text.split(':');
    if (parts.length !== 3) {
      return text;
    }
    const [hoursPart, minutesPart, secondsPart] = parts;
    const normalizeHoursMinutes = (segment) => {
      const trimmed = segment.trim();
      if (!trimmed) {
        return '00';
      }
      const numeric = Number.parseInt(trimmed, 10);
      if (Number.isNaN(numeric)) {
        return trimmed.padStart(2, '0');
      }
      const normalized = String(Math.max(0, numeric));
      return normalized.length < 2 ? normalized.padStart(2, '0') : normalized;
    };
    const normalizeSeconds = (segment) => {
      const trimmed = segment.trim();
      if (!trimmed) {
        return '00';
      }
      const digits = trimmed.replace(/\D/g, '');
      if (digits.length >= 2) {
        return digits.slice(0, 2);
      }
      if (digits.length === 1) {
        return digits.padStart(2, '0');
      }
      const numeric = Number.parseInt(trimmed, 10);
      if (Number.isNaN(numeric)) {
        return trimmed.padStart(2, '0');
      }
      const normalized = String(Math.max(0, numeric));
      return normalized.length < 2 ? normalized.padStart(2, '0') : normalized;
    };
    const hours = normalizeHoursMinutes(hoursPart);
    const minutes = normalizeHoursMinutes(minutesPart);
    const seconds = normalizeSeconds(secondsPart);
    return `${hours}:${minutes}:${seconds}`;
  };

  const formatDateTimeLabel = (value) => {
    if (!value) {
      return '—';
    }
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) {
      return '—';
    }
    return date.toLocaleString('pt-BR', {
      dateStyle: 'short',
      timeStyle: 'short',
    });
  };

  const formatDateTime = (value) => {
    if (!value) {
      return '—';
    }
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) {
      return '—';
    }
    try {
      return new Intl.DateTimeFormat('pt-BR', {
        dateStyle: 'short',
        timeStyle: 'medium',
        timeZone: 'America/Sao_Paulo',
      }).format(date);
    } catch (error) {
      return date.toLocaleString('pt-BR');
    }
  };

  const stripDigits = (value) => {
    if (value === null || value === undefined) {
      return '';
    }
    return String(value).replace(/\D+/g, '');
  };

  const setElementText = (element, value) => {
    if (!element) {
      return;
    }

    if (value === null || value === undefined) {
      element.textContent = '—';
      return;
    }

    const text = String(value).trim();
    element.textContent = text || '—';
  };

  const resolveRunningPlanFromState = (state) => {
    if (!state || typeof state !== 'object') {
      return null;
    }

    const candidate =
      state.current_plan ??
      state.currentPlan ??
      state.plan_in_execution ??
      state.planInExecution ??
      state.running_plan ??
      state.runningPlan ??
      state.plan ??
      null;

    if (!candidate || typeof candidate !== 'object') {
      return null;
    }

    return candidate;
  };

  const updateRunningPlanInfo = (plan) => {
    const resolvedPlan = plan && typeof plan === 'object' ? plan : null;

    const planNumber =
      resolvedPlan?.number ??
      resolvedPlan?.plan_number ??
      resolvedPlan?.planNumber ??
      resolvedPlan?.numero ??
      resolvedPlan?.numero_plano ??
      null;
    setElementText(runningPlanNumberEl, planNumber);

    const rawDocument =
      resolvedPlan?.document ??
      resolvedPlan?.documento ??
      resolvedPlan?.document_number ??
      resolvedPlan?.documentNumber ??
      resolvedPlan?.numero_inscricao ??
      null;
    const formattedDocument = rawDocument ? context.formatDocument(rawDocument) : null;
    setElementText(runningPlanDocumentEl, formattedDocument);

    const companyName =
      resolvedPlan?.company_name ??
      resolvedPlan?.razao_social ??
      resolvedPlan?.companyName ??
      resolvedPlan?.razaoSocial ??
      null;
    setElementText(runningPlanCompanyEl, companyName);

    const statusValue =
      resolvedPlan?.status ??
      resolvedPlan?.status_label ??
      resolvedPlan?.situacao ??
      null;
    setElementText(runningPlanStatusEl, formatStatusLabel(statusValue));

    const stageValue =
      resolvedPlan?.stage ??
      resolvedPlan?.stage_label ??
      resolvedPlan?.stageLabel ??
      resolvedPlan?.etapa ??
      null;
    setElementText(runningPlanStageEl, stageValue);
  };

  const pad2 = (n) => String(Math.trunc(Math.max(0, n))).padStart(2, '0');

  const formatDurationText = (ms) => {
    if (!Number.isFinite(ms) || ms < 0) {
      return '—';
    }
    const totalSeconds = Math.trunc(ms / 1000);
    const hours = Math.trunc(totalSeconds / 3600);
    const minutes = Math.trunc((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return `${hours}h ${pad2(minutes)}m ${pad2(seconds)}s`;
  };

  const setText = (el, prefix, value) => {
    if (!el) return;
    const text = value ? value : '—';
    if (prefix && String(prefix).trim()) {
      el.textContent = `${prefix} ${text}`;
    } else {
      el.textContent = text;
    }
  };

  context.formatStatusLabel = formatStatusLabel;
  context.formatDaysValue = formatDaysValue;
  context.formatCurrencyValue = formatCurrencyValue;
  context.formatDateLabel = formatDateLabel;
  context.formatDurationLabel = formatDurationLabel;
  context.formatDateTimeLabel = formatDateTimeLabel;
  context.formatDateTime = formatDateTime;
  context.setElementText = setElementText;
  context.resolveRunningPlanFromState = resolveRunningPlanFromState;
  context.updateRunningPlanInfo = updateRunningPlanInfo;
  context.pad2 = pad2;
  context.formatDurationText = formatDurationText;
  context.setText = setText;
  context.stripDigits = stripDigits;
}
