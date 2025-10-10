export function registerSearchModule(context) {
  const state = context;
  const { tableSearchState, plansPager } = context;

  const tableSearchForm = document.getElementById('tableSearchForm');
  const tableSearchInput = document.getElementById('tableSearchInput');
  const MIN_CNPJ_PREFIX_LENGTH = 5;
  const CNPJ_DIGITS = 14;
  const DOCUMENT_PATTERN = /^[\d./\-\s]+$/;
  const SEARCH_DEBOUNCE_MS = 350;
  let searchDebounceHandle = null;

  let currentDescriptor = null;

  const onlyDigits = (value) => {
    if (window.SirepUtils?.onlyDigits) {
      return window.SirepUtils.onlyDigits(value);
    }
    return String(value ?? '').replace(/\D+/g, '');
  };

  const resolveDocumentDescriptor = (term) => {
    const raw = String(term ?? '').trim();
    if (!raw) {
      return null;
    }
    const digits = onlyDigits(raw);
    if (!digits) {
      return null;
    }
    const looksLikeDocument = DOCUMENT_PATTERN.test(raw);
    if (!looksLikeDocument && digits !== raw) {
      return null;
    }
    if (digits.length === CNPJ_DIGITS) {
      return { mode: 'cnpj-exact', tipoDoc: 'CNPJ', digits };
    }
    if (digits.length >= MIN_CNPJ_PREFIX_LENGTH && digits.length < CNPJ_DIGITS) {
      return { mode: 'cnpj-prefix', tipoDoc: 'CNPJ', digits };
    }
    return null;
  };

  const updateSearchDescriptor = (term) => {
    currentDescriptor = resolveDocumentDescriptor(term);
  };

  context.getPlansSearchConfig = () => {
    if (!currentDescriptor) {
      return null;
    }
    return { tipoDoc: currentDescriptor.tipoDoc };
  };

  context.getPlansSearchChip = () => null;
  context.overridePlansSearch = () => {};

  const syncSearchInputValue = () => {
    if (!tableSearchInput) {
      return;
    }
    const value = tableSearchState.plans ?? '';
    if (tableSearchInput.value !== value) {
      tableSearchInput.value = value;
    }
  };

  const setActiveSearchTarget = () => {
    state.activeTableSearchTarget = 'plans';
    if (tableSearchForm) {
      tableSearchForm.dataset.activeTable = 'plans';
    }
    if (tableSearchInput) {
      tableSearchInput.setAttribute('aria-controls', 'plansTablePanel');
    }
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
    updateSearchDescriptor(normalized);
    void context.refreshPlans?.({ showLoading: true });
    if (typeof context.scheduleOccurrencesCountUpdate === 'function') {
      context.scheduleOccurrencesCountUpdate();
    }
  };

  if (tableSearchForm) {
    tableSearchForm.addEventListener('submit', (event) => {
      event.preventDefault();
      if (searchDebounceHandle !== null) {
        window.clearTimeout(searchDebounceHandle);
        searchDebounceHandle = null;
      }
      const value = tableSearchInput?.value ?? '';
      plansPager.page = 1;
      plansPager.nextCursor = null;
      plansPager.prevCursor = null;
      handlePlansSearch(value, { forceRefresh: true });
    });
  }

  if (tableSearchInput) {
    tableSearchInput.addEventListener('input', (event) => {
      const value = event.target?.value ?? '';
      tableSearchState.plans = value;
      if (searchDebounceHandle !== null) {
        window.clearTimeout(searchDebounceHandle);
      }
      searchDebounceHandle = window.setTimeout(() => {
        searchDebounceHandle = null;
        if (value.trim()) {
          handlePlansSearch(value);
        } else if (state.currentPlansSearchTerm) {
          plansPager.page = 1;
          plansPager.nextCursor = null;
          plansPager.prevCursor = null;
          handlePlansSearch('', { forceRefresh: true });
        }
      }, SEARCH_DEBOUNCE_MS);
    });
  }

  context.syncSearchInputValue = syncSearchInputValue;
  context.setActiveSearchTarget = setActiveSearchTarget;

  setActiveSearchTarget();
  syncSearchInputValue();
  updateSearchDescriptor(tableSearchState.plans ?? '');
}
