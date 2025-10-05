export function registerTreatmentModule(context) {
  const state = context;
  const {
    treatmentTableBody,
    treatmentColumnCount,
    treatmentPagerPrevBtn,
    treatmentPagerNextBtn,
    treatmentPagerLabel,
    treatmentPagerRange,
    kpiQueueEl,
    kpiRescindedEl,
    kpiFailuresEl,
    TREATMENT_ENDPOINT,
    TREATMENT_GRID,
    DEFAULT_PLAN_PAGE_SIZE,
    filtersState,
    btnCloseTreatment,
  } = context;

  const treatmentPager = context.treatmentPager;

  const formatIntCount = (value) => {
    const n = Number(value);
    if (!Number.isFinite(n) || n < 0) return '0';
    if (n >= 1000) return n.toLocaleString('pt-BR');
    return String(Math.trunc(n));
  };

  const updateTreatmentKpis = () => {
    if (kpiQueueEl) {
      kpiQueueEl.textContent = formatIntCount(state.treatmentTotals.pending ?? 0);
    }
    if (kpiRescindedEl) {
      kpiRescindedEl.textContent = formatIntCount(state.treatmentTotals.processed ?? 0);
    }
    if (kpiFailuresEl) {
      kpiFailuresEl.textContent = formatIntCount(state.treatmentTotals.skipped ?? 0);
    }
  };

  const renderTreatmentPlaceholder = (
    message = 'nenhum lote aberto. clique em "Migrar planos".',
    modifier = 'empty',
  ) => {
    if (!treatmentTableBody) {
      return;
    }
    treatmentTableBody.innerHTML = '';
    const row = document.createElement('tr');
    row.className = 'table__row table__row--empty';
    if (modifier) {
      row.classList.add(`table__row--${modifier}`);
    }
    const cell = document.createElement('td');
    cell.className = 'table__cell table__cell--empty';
    cell.colSpan = treatmentColumnCount;
    cell.textContent = message;
    row.appendChild(cell);
    treatmentTableBody.appendChild(row);
  };

  const renderTreatmentRows = (items) => {
    if (!treatmentTableBody) {
      return;
    }
    treatmentTableBody.innerHTML = '';
    const plans = Array.isArray(items) ? items : [];
    if (!plans.length) {
      renderTreatmentPlaceholder('nenhum item pendente neste lote.');
      return;
    }
    plans.forEach((item) => {
      const row = document.createElement('tr');
      row.className = 'table__row';
      if (item?.plano_id) {
        row.dataset.planId = String(item.plano_id);
      }

      const planCell = document.createElement('td');
      planCell.className = 'table__cell';
      planCell.textContent = item?.number ?? '';
      row.appendChild(planCell);

      const documentCell = document.createElement('td');
      documentCell.className = 'table__cell';
      documentCell.textContent = item?.document ?? '';
      row.appendChild(documentCell);

      const companyCell = document.createElement('td');
      companyCell.className = 'table__cell';
      companyCell.textContent = item?.company_name ?? '';
      row.appendChild(companyCell);

      const balanceCell = document.createElement('td');
      balanceCell.className = 'table__cell';
      balanceCell.textContent = context.formatCurrencyValue(item?.balance);
      row.appendChild(balanceCell);

      const statusDateCell = document.createElement('td');
      statusDateCell.className = 'table__cell';
      statusDateCell.textContent = context.formatDateLabel(item?.status_date);
      row.appendChild(statusDateCell);

      const actionsCell = document.createElement('td');
      actionsCell.className = 'table__cell table__cell--actions';
      const actionsWrapper = document.createElement('div');
      actionsWrapper.className = 'table-actions';

      const rescindButton = document.createElement('button');
      rescindButton.type = 'button';
      rescindButton.className = 'btn btn--ghost';
      rescindButton.textContent = 'Rescindir';
      rescindButton.addEventListener('click', () => {
        void handleRescind(item, rescindButton);
      });
      actionsWrapper.appendChild(rescindButton);

      const skipButton = document.createElement('button');
      skipButton.type = 'button';
      skipButton.className = 'btn btn--ghost';
      skipButton.textContent = 'Pular';
      skipButton.addEventListener('click', () => {
        void handleSkip(item, skipButton);
      });
      actionsWrapper.appendChild(skipButton);

      actionsCell.appendChild(actionsWrapper);
      row.appendChild(actionsCell);

      treatmentTableBody.appendChild(row);
    });
  };

  const resetTreatmentPagination = () => {
    treatmentPager.page = 1;
    treatmentPager.nextCursor = null;
    treatmentPager.prevCursor = null;
    treatmentPager.hasMoreNext = false;
    treatmentPager.hasMorePrev = false;
    treatmentPager.lastCount = 0;
    treatmentPager.currentCursor = null;
    treatmentPager.currentDirection = 'next';
  };

  const setTreatmentTotals = (totals) => {
    const pending = Number(totals?.pending) || 0;
    const processed = Number(totals?.processed) || 0;
    const skipped = Number(totals?.skipped) || 0;
    state.treatmentTotals = {
      pending: pending < 0 ? 0 : pending,
      processed: processed < 0 ? 0 : processed,
      skipped: skipped < 0 ? 0 : skipped,
    };
    updateTreatmentKpis();
  };

  const getTreatmentTotalForStatus = (status) => {
    const normalized = typeof status === 'string' ? status.trim().toLowerCase() : 'pending';
    if (normalized === 'processed') {
      return Math.max(0, Number(state.treatmentTotals.processed) || 0);
    }
    if (normalized === 'skipped') {
      return Math.max(0, Number(state.treatmentTotals.skipped) || 0);
    }
    return Math.max(0, Number(state.treatmentTotals.pending) || 0);
  };

  const buildTreatmentFilters = () => {
    const filters = {};
    if (Array.isArray(filtersState.situacao) && filtersState.situacao.length) {
      filters.situacao = filtersState.situacao;
    }
    if (typeof filtersState.diasMin === 'number' && Number.isFinite(filtersState.diasMin)) {
      filters.dias_min = filtersState.diasMin;
    }
    if (typeof filtersState.saldoMin === 'number' && Number.isFinite(filtersState.saldoMin)) {
      filters.saldo_min = filtersState.saldoMin;
    }
    if (filtersState.dtRange) {
      filters.dt_sit_range = filtersState.dtRange;
    }
    return Object.keys(filters).length ? filters : null;
  };

  const updateTreatmentPagerUI = () => {
    const pageSize = Number(treatmentPager.pageSize) || DEFAULT_PLAN_PAGE_SIZE;
    const totalForStatus = getTreatmentTotalForStatus(state.treatmentStatusFilter);
    const totalValue = Number.isFinite(totalForStatus) ? totalForStatus : 0;
    const totalPages = totalValue > 0 ? Math.ceil(totalValue / pageSize) : 1;
    let currentPage = Math.max(1, Number(treatmentPager.page) || 1);
    if (currentPage > totalPages) {
      currentPage = totalPages;
      treatmentPager.page = currentPage;
    }

    if (treatmentPagerLabel) {
      treatmentPagerLabel.textContent = `pág. ${currentPage} de ${totalPages}`;
    }

    if (treatmentPagerRange) {
      const rowsOnPage = Math.max(0, Number(treatmentPager.lastCount) || 0);
      const showingFrom = rowsOnPage ? (currentPage - 1) * pageSize + 1 : 0;
      const showingTo = rowsOnPage
        ? Math.min(totalValue, showingFrom + rowsOnPage - 1)
        : 0;
      const totalLabel = totalValue.toLocaleString('pt-BR');
      treatmentPagerRange.textContent = `exibindo ${showingFrom}–${showingTo} de ${totalLabel} planos para rescisão`;
    }

    if (treatmentPagerPrevBtn) {
      const canGoPrev = currentPage > 1 && Boolean(treatmentPager.prevCursor);
      treatmentPagerPrevBtn.disabled = !canGoPrev;
      treatmentPagerPrevBtn.setAttribute('aria-disabled', String(!canGoPrev));
    }

    if (treatmentPagerNextBtn) {
      const canGoNext =
        currentPage < totalPages && Boolean(treatmentPager.hasMoreNext && treatmentPager.nextCursor);
      treatmentPagerNextBtn.disabled = !canGoNext;
      treatmentPagerNextBtn.setAttribute('aria-disabled', String(!canGoNext));
    }
  };

  const fetchTreatmentState = async ({ refreshItems = true } = {}) => {
    if (state.isFetchingTreatmentState) {
      return null;
    }
    state.isFetchingTreatmentState = true;
    const baseUrl =
      window.location.origin && window.location.origin !== 'null'
        ? window.location.origin
        : window.location.href;
    const url = new URL(`${TREATMENT_ENDPOINT}/state`, baseUrl);
    url.searchParams.set('grid', TREATMENT_GRID);
    const headers = new Headers({ Accept: 'application/json' });
    const matricula = state.currentUser?.username?.trim();
    if (matricula) {
      headers.set('X-User-Registration', matricula);
    }

    try {
      const response = await fetch(url.toString(), { headers });
      if (!response.ok) {
        throw new Error('Falha ao obter estado do tratamento.');
      }
      const payload = await response.json();
      const hasOpen = Boolean(payload?.has_open);
      const loteIdRaw = hasOpen ? payload?.lote_id ?? null : null;
      const loteId = loteIdRaw ? String(loteIdRaw) : null;
      setTreatmentTotals(payload?.totals ?? {});

      if (btnCloseTreatment) {
        const disable = !hasOpen || !loteId;
        btnCloseTreatment.disabled = disable;
        btnCloseTreatment.setAttribute('aria-disabled', String(disable));
      }

      if (!hasOpen || !loteId) {
        state.treatmentBatchId = null;
        resetTreatmentPagination();
        updateTreatmentPagerUI();
        renderTreatmentPlaceholder();
        state.treatmentLoaded = true;
        return payload;
      }

      const batchChanged = state.treatmentBatchId !== loteId;
      state.treatmentBatchId = loteId;
      if (batchChanged) {
        resetTreatmentPagination();
      }
      if (refreshItems || batchChanged) {
        await refreshTreatment({ reset: batchChanged, showLoading: !state.treatmentLoaded });
      } else {
        updateTreatmentPagerUI();
      }
      return payload;
    } catch (error) {
      console.error('Erro ao carregar o estado do tratamento.', error);
      state.treatmentBatchId = null;
      setTreatmentTotals({ pending: 0, processed: 0, skipped: 0 });
      resetTreatmentPagination();
      updateTreatmentPagerUI();
      renderTreatmentPlaceholder('Não foi possível carregar os planos.', 'error');
      return null;
    } finally {
      state.isFetchingTreatmentState = false;
    }
  };

  const refreshTreatment = async ({ cursor, direction, reset = false, showLoading } = {}) => {
    if (!treatmentTableBody || state.isFetchingTreatment) {
      return;
    }
    if (!state.treatmentBatchId) {
      resetTreatmentPagination();
      updateTreatmentPagerUI();
      renderTreatmentPlaceholder();
      return;
    }

    const hasCursorParam = cursor !== undefined;
    let normalizedDirection;
    if (hasCursorParam || typeof direction === 'string') {
      normalizedDirection = direction === 'prev' ? 'prev' : 'next';
    } else {
      normalizedDirection = treatmentPager.currentDirection || 'next';
    }

    if (reset) {
      resetTreatmentPagination();
      treatmentPager.currentDirection = normalizedDirection;
    }

    let requestCursor;
    if (hasCursorParam) {
      requestCursor = cursor;
    } else if (reset) {
      requestCursor = null;
    } else {
      requestCursor = treatmentPager.currentCursor;
    }

    const shouldShowLoading = showLoading ?? !state.treatmentLoaded;
    if (shouldShowLoading) {
      renderTreatmentPlaceholder('carregando planos...', 'loading');
    }

    state.isFetchingTreatment = true;
    try {
      const baseUrl =
        window.location.origin && window.location.origin !== 'null'
          ? window.location.origin
          : window.location.href;
      const url = new URL(`${TREATMENT_ENDPOINT}/items`, baseUrl);
      url.searchParams.set('lote_id', String(state.treatmentBatchId));
      url.searchParams.set('status', state.treatmentStatusFilter);
      url.searchParams.set('page_size', String(treatmentPager.pageSize || DEFAULT_PLAN_PAGE_SIZE));
      url.searchParams.set('direction', normalizedDirection);
      if (requestCursor) {
        url.searchParams.set('cursor', requestCursor);
      }

      const headers = new Headers({ Accept: 'application/json' });
      const matricula = state.currentUser?.username?.trim();
      if (matricula) {
        headers.set('X-User-Registration', matricula);
      }

      const response = await fetch(url.toString(), { headers });
      if (!response.ok) {
        throw new Error('Não foi possível carregar os itens do tratamento.');
      }

      const payload = await response.json();
      const items = Array.isArray(payload?.items) ? payload.items : [];
      renderTreatmentRows(items);

      const paging = payload?.paging || {};
      const pageSizeValue = Number(paging.page_size);
      if (Number.isFinite(pageSizeValue) && pageSizeValue > 0) {
        treatmentPager.pageSize = pageSizeValue;
      }
      treatmentPager.nextCursor = paging?.next_cursor || null;
      treatmentPager.prevCursor = paging?.prev_cursor || null;
      treatmentPager.lastCount = items.length;

      const hasResults = items.length > 0;

      if (reset) {
        treatmentPager.page = 1;
      } else if (hasCursorParam && requestCursor && hasResults) {
        if (normalizedDirection === 'next') {
          treatmentPager.page += 1;
        } else if (normalizedDirection === 'prev') {
          treatmentPager.page = Math.max(1, treatmentPager.page - 1);
        }
      } else if (!hasCursorParam) {
        treatmentPager.page = Math.max(1, treatmentPager.page);
      }

      if (reset) {
        treatmentPager.currentCursor = requestCursor ?? null;
        treatmentPager.currentDirection = normalizedDirection;
      } else if (hasCursorParam) {
        if (hasResults) {
          treatmentPager.currentCursor = requestCursor ?? null;
          treatmentPager.currentDirection = normalizedDirection;
        }
      } else {
        if (requestCursor !== undefined) {
          treatmentPager.currentCursor = requestCursor ?? null;
        }
        treatmentPager.currentDirection = normalizedDirection;
      }

      const totalForStatus = getTreatmentTotalForStatus(state.treatmentStatusFilter);
      const totalPages = totalForStatus > 0 ? Math.ceil(totalForStatus / treatmentPager.pageSize) : 1;
      if (treatmentPager.page > totalPages) {
        treatmentPager.page = totalPages;
      }
      treatmentPager.page = Math.max(1, treatmentPager.page);

      const hasMorePrev =
        (normalizedDirection === 'prev' && hasCursorParam)
          ? Boolean(paging?.has_more)
          : treatmentPager.page > 1;
      const hasMoreNext =
        (normalizedDirection === 'next' && hasCursorParam)
          ? Boolean(paging?.has_more)
          : treatmentPager.page < totalPages;

      treatmentPager.hasMorePrev = hasMorePrev && Boolean(treatmentPager.prevCursor);
      treatmentPager.hasMoreNext = hasMoreNext && Boolean(treatmentPager.nextCursor);

      if (treatmentPager.page <= 1) {
        treatmentPager.hasMorePrev = false;
      }

      updateTreatmentPagerUI();
      state.treatmentLoaded = true;
    } catch (error) {
      console.error('Erro ao carregar planos de tratamento.', error);
      if (!state.treatmentLoaded) {
        renderTreatmentPlaceholder('Não foi possível carregar os planos.', 'error');
      }
    } finally {
      state.isFetchingTreatment = false;
    }
  };

  async function handleRescind(item, button) {
    if (!state.treatmentBatchId || !item?.plano_id) {
      return;
    }
    const targetButton = button ?? null;
    if (targetButton) {
      targetButton.disabled = true;
      targetButton.setAttribute('aria-disabled', 'true');
    }
    try {
      const baseUrl =
        window.location.origin && window.location.origin !== 'null'
          ? window.location.origin
          : window.location.href;
      const url = new URL(`${TREATMENT_ENDPOINT}/rescind`, baseUrl);
      const headers = new Headers({ Accept: 'application/json', 'Content-Type': 'application/json' });
      const matricula = state.currentUser?.username?.trim();
      if (matricula) {
        headers.set('X-User-Registration', matricula);
      }
      const payload = {
        lote_id: state.treatmentBatchId,
        plano_id: item.plano_id,
        data_rescisao: new Date().toISOString(),
      };
      const response = await fetch(url.toString(), {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error('Falha ao rescindir o plano.');
      }
      await fetchTreatmentState({ refreshItems: true });
    } catch (error) {
      console.error('Erro ao rescindir plano.', error);
    } finally {
      if (targetButton) {
        targetButton.disabled = false;
        targetButton.setAttribute('aria-disabled', 'false');
      }
    }
  }

  async function handleSkip(item, button) {
    if (!state.treatmentBatchId || !item?.plano_id) {
      return;
    }
    const targetButton = button ?? null;
    if (targetButton) {
      targetButton.disabled = true;
      targetButton.setAttribute('aria-disabled', 'true');
    }
    try {
      const baseUrl =
        window.location.origin && window.location.origin !== 'null'
          ? window.location.origin
          : window.location.href;
      const url = new URL(`${TREATMENT_ENDPOINT}/skip`, baseUrl);
      const headers = new Headers({ Accept: 'application/json', 'Content-Type': 'application/json' });
      const matricula = state.currentUser?.username?.trim();
      if (matricula) {
        headers.set('X-User-Registration', matricula);
      }
      const payload = {
        lote_id: state.treatmentBatchId,
        plano_id: item.plano_id,
      };
      const response = await fetch(url.toString(), {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error('Falha ao ignorar o item.');
      }
      await fetchTreatmentState({ refreshItems: true });
    } catch (error) {
      console.error('Erro ao ignorar item de tratamento.', error);
    } finally {
      if (targetButton) {
        targetButton.disabled = false;
        targetButton.setAttribute('aria-disabled', 'false');
      }
    }
  }

  if (treatmentPagerPrevBtn) {
    treatmentPagerPrevBtn.addEventListener('click', () => {
      if (treatmentPager.page <= 1 || !treatmentPager.prevCursor) {
        return;
      }
      void refreshTreatment({ direction: 'prev', cursor: treatmentPager.prevCursor });
    });
  }

  if (treatmentPagerNextBtn) {
    treatmentPagerNextBtn.addEventListener('click', () => {
      if (!treatmentPager.hasMoreNext || !treatmentPager.nextCursor) {
        return;
      }
      void refreshTreatment({ direction: 'next', cursor: treatmentPager.nextCursor });
    });
  }

  const btnMigratePlans = document.getElementById('btnMigratePlans');
  if (btnMigratePlans) {
    btnMigratePlans.addEventListener('click', async () => {
      try {
        const baseUrl =
          window.location.origin && window.location.origin !== 'null'
            ? window.location.origin
            : window.location.href;
        const url = new URL(`${TREATMENT_ENDPOINT}/migrate`, baseUrl);
        const headers = new Headers({ 'Accept': 'application/json', 'Content-Type': 'application/json' });
        const matricula = state.currentUser?.username?.trim();
        if (matricula) {
          headers.set('X-User-Registration', matricula);
        }
        const payload = { grid: TREATMENT_GRID };
        const filtersPayload = buildTreatmentFilters();
        if (filtersPayload) {
          payload.filters = filtersPayload;
        }
        const response = await fetch(url.toString(), {
          method: 'POST',
          headers,
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          throw new Error('Falha ao migrar planos.');
        }
        await response.json().catch(() => null);
        await fetchTreatmentState({ refreshItems: true });
      } catch (error) {
        console.error('Erro ao migrar planos para tratamento.', error);
      }
    });
  }

  if (btnCloseTreatment) {
    btnCloseTreatment.addEventListener('click', async () => {
      if (!state.treatmentBatchId) {
        return;
      }
      btnCloseTreatment.disabled = true;
      btnCloseTreatment.setAttribute('aria-disabled', 'true');

      try {
        const baseUrl =
          window.location.origin && window.location.origin !== 'null'
            ? window.location.origin
            : window.location.href;
        const url = new URL(`${TREATMENT_ENDPOINT}/close`, baseUrl);
        const headers = new Headers({ 'Accept': 'application/json', 'Content-Type': 'application/json' });
        const matricula = state.currentUser?.username?.trim();
        if (matricula) {
          headers.set('X-User-Registration', matricula);
        }
        const payload = { lote_id: state.treatmentBatchId };
        const response = await fetch(url.toString(), {
          method: 'POST',
          headers,
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          throw new Error('Falha ao encerrar o lote.');
        }
        await response.json().catch(() => null);
        await fetchTreatmentState({ refreshItems: true });
      } catch (error) {
        console.error('Erro ao encerrar lote de tratamento.', error);
        if (state.treatmentBatchId) {
          btnCloseTreatment.disabled = false;
          btnCloseTreatment.setAttribute('aria-disabled', 'false');
        }
      }
    });
  }

  context.updateTreatmentKpis = updateTreatmentKpis;
  context.renderTreatmentPlaceholder = renderTreatmentPlaceholder;
  context.renderTreatmentRows = renderTreatmentRows;
  context.resetTreatmentPagination = resetTreatmentPagination;
  context.setTreatmentTotals = setTreatmentTotals;
  context.buildTreatmentFilters = buildTreatmentFilters;
  context.updateTreatmentPagerUI = updateTreatmentPagerUI;
  context.fetchTreatmentState = fetchTreatmentState;
  context.refreshTreatment = refreshTreatment;
}
