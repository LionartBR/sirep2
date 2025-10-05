export function registerSearchModule(context) {
  const state = context;
  const { tableSearchState, plansPager, occPager } = context;

  const tableSearchForm = document.getElementById('tableSearchForm');
  const tableSearchInput = document.getElementById('tableSearchInput');
  const SEARCH_DEBOUNCE_MS = 350;
  let searchDebounceHandle = null;

  const syncSearchInputValue = (target) => {
    if (!target || !tableSearchInput) {
      return;
    }
    const value = tableSearchState[target] ?? '';
    if (tableSearchInput.value !== value) {
      tableSearchInput.value = value;
    }
  };

  const setActiveSearchTarget = (target) => {
    if (!target) {
      return;
    }
    state.activeTableSearchTarget = target;
    if (tableSearchForm) {
      tableSearchForm.dataset.activeTable = target;
    }
    if (tableSearchInput) {
      const controlsTarget = target === 'occurrences' ? 'occurrencesTablePanel' : 'plansTablePanel';
      tableSearchInput.setAttribute('aria-controls', controlsTarget);
    }
  };

  const resolveTableSearchIntent = (term) => {
    const normalized = (term || '').trim();
    if (!normalized) {
      return {
        normalized,
        digits: '',
        intent: 'none',
      };
    }

    const digits = context.stripDigits?.(normalized) ?? '';
    const isDigitsOnly = /^\d+$/.test(normalized);

    if ([11, 12, 14].includes(digits.length)) {
      return {
        normalized,
        digits,
        intent: 'document',
      };
    }

    if (isDigitsOnly) {
      return {
        normalized,
        digits: normalized,
        intent: 'plan-number',
      };
    }

    return {
      normalized,
      digits,
      intent: 'text',
    };
  };

  const applyOccurrencesFilter = (term) => {
    const occurrencesPanel = document.getElementById('occurrencesTablePanel');
    if (!occurrencesPanel) {
      return;
    }

    const tbody = occurrencesPanel.querySelector('tbody');
    if (!tbody) {
      return;
    }

    const { normalized, digits, intent } = resolveTableSearchIntent(term);
    const normalizedLower = normalized.toLowerCase();

    const rows = Array.from(tbody.rows ?? []);
    let visibleRows = 0;

    rows.forEach((row) => {
      if (!row || row.classList.contains('table__row--empty')) {
        return;
      }

      const planCell = row.cells?.[0];
      const documentCell = row.cells?.[1];
      const nameCell = row.cells?.[2];

      const planDigits = context.stripDigits?.(planCell?.textContent ?? '') ?? '';
      const documentDigits = context.stripDigits?.(documentCell?.textContent ?? '') ?? '';
      const nameText = (nameCell?.textContent ?? '').toLowerCase();

      let matches = true;
      if (normalized) {
        if (intent === 'document') {
          matches = documentDigits === digits;
        } else if (intent === 'plan-number') {
          matches = planDigits.startsWith(digits);
        } else if (intent === 'text') {
          matches = nameText.includes(normalizedLower);
        }
      }

      row.hidden = !matches;
      if (matches) {
        visibleRows += 1;
      }
    });

    const placeholderRow = rows.find((row) => row.classList.contains('table__row--empty'));
    if (placeholderRow) {
      const placeholderCell = placeholderRow.cells?.[0];
      if (placeholderCell) {
        placeholderCell.textContent =
          visibleRows > 0 || !normalized
            ? 'nenhuma ocorrência por aqui.'
            : 'nenhuma ocorrência encontrada para a busca.';
      }
      placeholderRow.hidden = visibleRows > 0;
    }

    state.scheduleOccurrencesCountUpdate();
  };

  const handleOccurrencesSearch = (term, { forceRefresh = false } = {}) => {
    const normalized = (term || '').trim();
    if (!forceRefresh && normalized === state.currentOccurrencesSearchTerm) {
      return;
    }
    state.currentOccurrencesSearchTerm = normalized;
    tableSearchState.occurrences = normalized;
    occPager.page = 1;
    occPager.nextCursor = null;
    occPager.prevCursor = null;
    void context.refreshOccurrences?.({ showLoading: true });
  };

  const handlePlansSearch = (term, { forceRefresh = false } = {}) => {
    const normalized = (term || '').trim();
    if (!forceRefresh && normalized === state.currentPlansSearchTerm) {
      return;
    }
    state.currentPlansSearchTerm = normalized;
    tableSearchState.plans = normalized;
    plansPager.page = 1;
    plansPager.nextCursor = null;
    plansPager.prevCursor = null;
    void context.refreshPlans?.({ showLoading: true });
  };

  if (tableSearchForm) {
    tableSearchForm.addEventListener('submit', (event) => {
      event.preventDefault();
      if (searchDebounceHandle !== null) {
        window.clearTimeout(searchDebounceHandle);
        searchDebounceHandle = null;
      }
      const value = tableSearchInput?.value ?? '';
      if (state.activeTableSearchTarget === 'occurrences') {
        handleOccurrencesSearch(value, { forceRefresh: true });
      } else {
        plansPager.page = 1;
        plansPager.nextCursor = null;
        plansPager.prevCursor = null;
        handlePlansSearch(value, { forceRefresh: true });
      }
    });
  }

  if (tableSearchInput) {
    tableSearchInput.addEventListener('input', (event) => {
      const value = event.target?.value ?? '';
      tableSearchState[state.activeTableSearchTarget] = value;
      if (searchDebounceHandle !== null) {
        window.clearTimeout(searchDebounceHandle);
      }
      searchDebounceHandle = window.setTimeout(() => {
        searchDebounceHandle = null;
        if (state.activeTableSearchTarget === 'occurrences') {
          handleOccurrencesSearch(value);
          return;
        }
        if (value.trim()) {
          handlePlansSearch(value);
        } else if (state.currentPlansSearchTerm) {
          plansPager.page = 1;
          plansPager.nextCursor = null;
          plansPager.prevCursor = null;
          handlePlansSearch('', { forceRefresh: true });
        }
        if (!value.trim() && state.currentOccurrencesSearchTerm) {
          handleOccurrencesSearch('', { forceRefresh: true });
        }
      }, SEARCH_DEBOUNCE_MS);
    });
  }

  context.syncSearchInputValue = syncSearchInputValue;
  context.setActiveSearchTarget = setActiveSearchTarget;
  context.applyOccurrencesFilter = applyOccurrencesFilter;
}
