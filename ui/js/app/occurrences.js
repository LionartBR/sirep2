export function registerOccurrencesModule(context) {
  const state = context;
  const {
    occTableBody,
    occColumnCount,
    filtersState,
    occPagerPrevBtn,
    occPagerNextBtn,
    occPagerLabel,
    occPagerRange,
    PLANS_ENDPOINT,
    DEFAULT_PLAN_PAGE_SIZE,
  } = context;

  const occPager = context.occPager;

  const renderOccurrencesPlaceholder = (message, modifier = 'empty') => {
    if (!occTableBody) {
      return;
    }
    occTableBody.innerHTML = '';
    const row = document.createElement('tr');
    row.className = 'table__row table__row--empty';
    if (modifier) {
      row.classList.add(`table__row--${modifier}`);
    }
    const cell = document.createElement('td');
    cell.className = 'table__cell table__cell--empty';
    cell.colSpan = occColumnCount;
    const wrapper = document.createElement('div');
    wrapper.className = 'table-empty';

    const messageEl = document.createElement('p');
    messageEl.className = 'table-empty__message';
    messageEl.textContent = message;
    wrapper.appendChild(messageEl);

    const isEmptyState = modifier === 'empty';
    const hasActiveFilters = typeof context.hasActiveFilters === 'function' && context.hasActiveFilters();
    const showFilterContext = isEmptyState && hasActiveFilters;
    if (showFilterContext) {
      const hint = document.createElement('p');
      hint.className = 'table-empty__hint';
      hint.textContent = 'Os filtros selecionados podem estar ocultando as ocorrências recentes.';
      wrapper.appendChild(hint);

      const chipsHolder = document.createElement('div');
      chipsHolder.className = 'table-active-filters table-active-filters--floating';
      chipsHolder.dataset.filterChips = 'occ-empty';
      wrapper.appendChild(chipsHolder);
      if (typeof context.attachFilterChipHandler === 'function') {
        context.attachFilterChipHandler(chipsHolder);
      }

      const actions = document.createElement('div');
      actions.className = 'table-empty__actions';
      const clearButton = document.createElement('button');
      clearButton.type = 'button';
      clearButton.className = 'table-empty__clear';
      clearButton.textContent = 'Limpar filtros';
      clearButton.addEventListener('click', () => {
        if (typeof context.clearAllFilters === 'function') {
          context.clearAllFilters();
        }
      });
      actions.appendChild(clearButton);
      wrapper.appendChild(actions);
    }

    cell.appendChild(wrapper);
    row.appendChild(cell);
    occTableBody.appendChild(row);
    if (isEmptyState) {
      state.occHasResults = false;
      if (typeof context.renderFilterChips === 'function') {
        context.renderFilterChips();
      }
    }
  };

  const renderOccurrenceRows = (items) => {
    if (!occTableBody) {
      return;
    }
    occTableBody.innerHTML = '';
    const rows = Array.isArray(items) ? items : [];
    if (!rows.length) {
      renderOccurrencesPlaceholder('nenhuma ocorrência por aqui.');
      return;
    }

    state.occHasResults = true;
    rows.forEach((item) => {
      const row = document.createElement('tr');
      row.className = 'table__row';

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

      const statusCell = document.createElement('td');
      statusCell.className = 'table__cell';
      statusCell.textContent = context.formatStatusLabel(item?.status);
      row.appendChild(statusCell);

      const daysCell = document.createElement('td');
      daysCell.className = 'table__cell';
      daysCell.textContent = context.formatDaysValue(item?.days_overdue);
      row.appendChild(daysCell);

      const balanceCell = document.createElement('td');
      balanceCell.className = 'table__cell';
      balanceCell.textContent = context.formatCurrencyValue(item?.balance);
      row.appendChild(balanceCell);

      const statusDateCell = document.createElement('td');
      statusDateCell.className = 'table__cell';
      statusDateCell.textContent = context.formatDateLabel(item?.status_date);
      row.appendChild(statusDateCell);

      const actionsCell = document.createElement('td');
      actionsCell.className = 'table__cell';
      actionsCell.textContent = '—';
      row.appendChild(actionsCell);

      occTableBody.appendChild(row);
    });

    if (typeof context.renderFilterChips === 'function') {
      context.renderFilterChips();
    }
  };

  const resetOccurrencesPagination = () => {
    occPager.page = 1;
    occPager.nextCursor = null;
    occPager.prevCursor = null;
    occPager.hasMore = false;
    occPager.showingFrom = 0;
    occPager.showingTo = 0;
    occPager.totalCount = null;
    occPager.totalPages = null;
  };

  const updateOccPagerUI = () => {
    if (occPagerLabel) {
      const totalPagesRaw = occPager.totalPages ?? null;
      const totalPagesNumber =
        totalPagesRaw && Number.isFinite(totalPagesRaw) && totalPagesRaw > 0
          ? Number(totalPagesRaw)
          : 1;
      const currentPage = Math.max(1, occPager.page || 1);
      occPagerLabel.textContent = `pág. ${currentPage} de ${totalPagesNumber}`;
    }
    if (occPagerRange) {
      const totalKnown = occPager.totalCount !== null && occPager.totalCount !== undefined;
      const totalLabel = totalKnown ? String(occPager.totalCount) : `~${Math.max(occPager.showingTo, 0)}`;
      const from = occPager.showingFrom || 0;
      const to = occPager.showingTo || 0;
      occPagerRange.textContent = `exibindo ${from}–${to} de ${totalLabel} planos para tratamento manual`;
    }
    if (occPagerPrevBtn) {
      const canGoPrev = occPager.page > 1;
      occPagerPrevBtn.disabled = !canGoPrev;
      occPagerPrevBtn.setAttribute('aria-disabled', String(!canGoPrev));
    }
    if (occPagerNextBtn) {
      const canGoNext = !!occPager.hasMore;
      occPagerNextBtn.disabled = !canGoNext;
      occPagerNextBtn.setAttribute('aria-disabled', String(!canGoNext));
    }
  };

  const buildOccurrencesRequestUrl = ({ direction = null } = {}) => {
    const baseUrl =
      window.location.origin && window.location.origin !== 'null'
        ? window.location.origin
        : window.location.href;
    const url = new URL(PLANS_ENDPOINT, baseUrl);
    url.searchParams.set('occurrences_only', 'true');
    url.searchParams.set('page', String(occPager.page));
    url.searchParams.set('page_size', String(occPager.pageSize));
    if (direction === 'next' && occPager.nextCursor) {
      url.searchParams.set('cursor', occPager.nextCursor);
      url.searchParams.set('direction', 'next');
    } else if (direction === 'prev' && occPager.prevCursor) {
      url.searchParams.set('cursor', occPager.prevCursor);
      url.searchParams.set('direction', 'prev');
    }
    if (state.currentOccurrencesSearchTerm) {
      url.searchParams.set('q', state.currentOccurrencesSearchTerm);
    }
    if (filtersState.situacao.length) {
      filtersState.situacao.forEach((value) => {
        url.searchParams.append('situacao', value);
      });
    }
    if (filtersState.diasMin !== null) {
      url.searchParams.set('dias_min', String(filtersState.diasMin));
    }
    if (filtersState.saldoMin !== null) {
      url.searchParams.set('saldo_min', String(filtersState.saldoMin));
    }
    if (filtersState.dtRange) {
      url.searchParams.set('dt_sit_range', filtersState.dtRange);
    }
    return url.toString();
  };

  const refreshOccurrences = async ({ showLoading, direction = null } = {}) => {
    if (!occTableBody || state.isFetchingOccurrences) {
      return;
    }
    if (!context.canAccessBase?.()) {
      state.occurrencesLoaded = true;
      renderOccurrencesPlaceholder('Área disponível apenas para perfil Gestor.', 'empty');
      return;
    }

    const shouldShowLoading = showLoading ?? !state.occurrencesLoaded;
    if (shouldShowLoading) {
      renderOccurrencesPlaceholder('carregando ocorrências...', 'loading');
    }

    state.isFetchingOccurrences = true;
    try {
      if (state.occFetchController) {
        state.occFetchController.abort();
      }
      state.occFetchController = new AbortController();
      const requestHeaders = new Headers({ Accept: 'application/json' });
      const matricula = state.currentUser?.username?.trim();
      if (matricula) {
        requestHeaders.set('X-User-Registration', matricula);
      }
      const response = await fetch(buildOccurrencesRequestUrl({ direction }), {
        headers: requestHeaders,
        signal: state.occFetchController.signal,
      });
      if (!response.ok) {
        throw new Error('Não foi possível carregar as ocorrências.');
      }
      const payload = await response.json();
      const items = Array.isArray(payload?.items) ? payload.items : [];
      renderOccurrenceRows(items);

      const paging = payload?.paging || {};
      if (paging && typeof paging === 'object') {
        occPager.page = Number(paging.page) || occPager.page;
        occPager.pageSize = Number(paging.page_size) || occPager.pageSize;
        occPager.hasMore = Boolean(paging.has_more);
        occPager.nextCursor = paging.next_cursor || null;
        occPager.prevCursor = paging.prev_cursor || null;
        occPager.showingFrom = Number(paging.showing_from) || (items.length ? 1 : 0);
        occPager.showingTo = Number(paging.showing_to) || (items.length ? items.length : 0);
        occPager.totalCount = typeof paging.total_count === 'number' ? paging.total_count : null;
        occPager.totalPages = typeof paging.total_pages === 'number' ? paging.total_pages : null;
        if (direction === 'prev') {
          occPager.hasMore = true;
        }
      } else {
        occPager.page = 1;
        occPager.pageSize = DEFAULT_PLAN_PAGE_SIZE;
        occPager.hasMore = false;
        occPager.nextCursor = null;
        occPager.prevCursor = null;
        occPager.showingFrom = items.length ? 1 : 0;
        occPager.showingTo = items.length;
        occPager.totalCount = typeof payload?.total === 'number' ? payload.total : null;
        occPager.totalPages = occPager.totalCount ? 1 : null;
      }
      updateOccPagerUI();

      state.occurrencesLoaded = true;
    } catch (error) {
      if (error?.name === 'AbortError') {
        return;
      }
      console.error('Erro ao carregar ocorrências.', error);
      if (!state.occurrencesLoaded) {
        renderOccurrencesPlaceholder('Não foi possível carregar as ocorrências.', 'error');
      }
    } finally {
      state.occFetchController = null;
      state.isFetchingOccurrences = false;
    }
  };

  const setupOccurrencesCounter = () => {
    const countElement = document.getElementById('occurrencesCount');
    const occurrencesPanel = document.getElementById('occurrencesTablePanel');

    if (!countElement || !occurrencesPanel) {
      state.scheduleOccurrencesCountUpdate = () => {};
      return;
    }

    const updateCount = () => {
      const total = typeof occPager.totalCount === 'number' ? occPager.totalCount : 0;
      countElement.textContent = `(${total})`;
      countElement.classList.toggle('section-switch__count--alert', total > 0);
    };

    let pendingHandle = null;
    const supportsAnimationFrame = typeof window.requestAnimationFrame === 'function';

    const runPendingUpdate = () => {
      pendingHandle = null;
      updateCount();
    };

    const cancelScheduledUpdate = () => {
      if (pendingHandle === null) {
        return;
      }

      if (supportsAnimationFrame) {
        window.cancelAnimationFrame(pendingHandle);
      } else {
        window.clearTimeout(pendingHandle);
      }

      pendingHandle = null;
    };

    state.scheduleOccurrencesCountUpdate = () => {
      if (pendingHandle !== null) {
        return;
      }

      if (supportsAnimationFrame) {
        pendingHandle = window.requestAnimationFrame(runPendingUpdate);
        return;
      }

      pendingHandle = window.setTimeout(runPendingUpdate, 0);
    };

    const forceUpdateCount = () => {
      cancelScheduledUpdate();
      updateCount();
    };

    forceUpdateCount();
  };

  if (occPagerPrevBtn) {
    occPagerPrevBtn.addEventListener('click', () => {
      if (occPager.page <= 1) {
        return;
      }
      occPager.page = Math.max(1, occPager.page - 1);
      void refreshOccurrences({ showLoading: true, direction: 'prev' });
    });
  }

  if (occPagerNextBtn) {
    occPagerNextBtn.addEventListener('click', () => {
      if (!occPager.hasMore) {
        return;
      }
      occPager.page = occPager.page + 1;
      void refreshOccurrences({ showLoading: true, direction: 'next' });
    });
  }

  context.renderOccurrencesPlaceholder = renderOccurrencesPlaceholder;
  context.renderOccurrenceRows = renderOccurrenceRows;
  context.resetOccurrencesPagination = resetOccurrencesPagination;
  context.updateOccPagerUI = updateOccPagerUI;
  context.refreshOccurrences = refreshOccurrences;
  context.setupOccurrencesCounter = setupOccurrencesCounter;
}
