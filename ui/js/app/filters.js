export function registerFiltersModule(context) {
  const { filtersState, FILTER_LABELS } = context;

  const hasActiveFilters = () =>
    (Array.isArray(filtersState.situacao) && filtersState.situacao.length > 0) ||
    filtersState.diasMin !== null ||
    filtersState.saldoMin !== null ||
    Boolean(filtersState.dtRange);

  const resetFiltersState = () => {
    filtersState.situacao = [];
    filtersState.diasMin = null;
    filtersState.saldoMin = null;
    filtersState.dtRange = null;
  };

  const getFilterLabel = (filterKey, value) => {
    const labels = FILTER_LABELS[filterKey];
    if (!labels) {
      return String(value);
    }
    const stringValue = String(value);
    return labels[stringValue] ?? labels[value] ?? String(value);
  };

  const renderFilterChips = () => {
    const containers = Array.from(document.querySelectorAll('[data-filter-chips]')).filter(
      (node) => node instanceof HTMLElement,
    );
    if (!containers.length) {
      return;
    }

    const chips = [];
    filtersState.situacao.forEach((value) => {
      chips.push({ type: 'situacao', value });
    });
    if (filtersState.diasMin !== null) {
      chips.push({ type: 'diasMin', value: String(filtersState.diasMin) });
    }
    if (filtersState.saldoMin !== null) {
      chips.push({ type: 'saldoMin', value: String(filtersState.saldoMin) });
    }
    if (filtersState.dtRange) {
      chips.push({ type: 'dtRange', value: filtersState.dtRange });
    }

    const hasChips = chips.length > 0;

    containers.forEach((container) => {
      const scope = container.getAttribute('data-filter-chips') ?? '';
      const isPlanContainer = scope.startsWith('plans');
      const isPlanEmptyContainer = scope === 'plans-empty';
      const isOccContainer = scope.startsWith('occ');
      const isOccEmptyContainer = scope === 'occ-empty';

      let shouldShow = hasChips;

      if (isPlanContainer) {
        shouldShow =
          hasChips &&
          ((context.plansHasResults && !isPlanEmptyContainer) ||
            (!context.plansHasResults && isPlanEmptyContainer));
      } else if (isOccContainer) {
        shouldShow =
          hasChips &&
          ((context.occHasResults && !isOccEmptyContainer) ||
            (!context.occHasResults && isOccEmptyContainer));
      }

      if (!shouldShow) {
        container.hidden = true;
        container.innerHTML = '';
        return;
      }

      container.hidden = false;
      container.innerHTML = '';

      chips.forEach(({ type, value }) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'filter-chip';
        button.dataset.filterType = type;
        button.dataset.filterValue = value;
        const label = getFilterLabel(type, value);
        button.setAttribute('aria-label', `Remover filtro ${label}`);
        button.innerHTML = `
          <span class="filter-chip__label">${label}</span>
          <span class="filter-chip__remove" aria-hidden="true">×</span>
          <span class="sr-only">Remover filtro ${label}</span>
        `;
        container.appendChild(button);
      });
    });
  };

  const syncFilterInputs = () => {
    const inputs = document.querySelectorAll('[data-filter-input]');
    inputs.forEach((input) => {
      const filterType = input.dataset.filterInput;
      const { value } = input;
      if (!filterType) {
        return;
      }

      if (filterType === 'situacao') {
        input.checked = filtersState.situacao.includes(value);
        return;
      }

      if (filterType === 'dias') {
        input.checked =
          filtersState.diasMin !== null && Number(value) === Number(filtersState.diasMin);
        return;
      }

      if (filterType === 'saldo') {
        input.checked =
          filtersState.saldoMin !== null && Number(value) === Number(filtersState.saldoMin);
        return;
      }

      if (filterType === 'dt') {
        input.checked = filtersState.dtRange === value;
      }
    });
  };

  const closeAllFilterDropdowns = () => {
    context.filterWrappers.forEach((wrapper) => {
      wrapper.classList.remove('table-filter--open');
      const trigger = wrapper.querySelector('.table-filter__trigger');
      if (trigger) {
        trigger.setAttribute('aria-expanded', 'false');
      }
    });
  };

  const clearFilter = (filterType) => {
    switch (filterType) {
      case 'situacao':
        filtersState.situacao = [];
        break;
      case 'dias':
        filtersState.diasMin = null;
        break;
      case 'saldo':
        filtersState.saldoMin = null;
        break;
      case 'dt':
        filtersState.dtRange = null;
        break;
      default:
        break;
    }
  };

  const applyFilters = ({ closeDropdown = false } = {}) => {
    if (typeof context.resetPlansPagination === 'function') {
      context.resetPlansPagination();
    }
    if (typeof context.resetOccurrencesPagination === 'function') {
      context.resetOccurrencesPagination();
    }
    syncFilterInputs();
    renderFilterChips();
    if (typeof context.refreshPlans === 'function') {
      void context.refreshPlans({ showLoading: true });
    }
    if (typeof context.refreshOccurrences === 'function') {
      void context.refreshOccurrences({ showLoading: true });
    }
    if (closeDropdown) {
      closeAllFilterDropdowns();
    }
  };

  const clearAllFilters = ({ closeDropdown = true } = {}) => {
    resetFiltersState();
    applyFilters({ closeDropdown });
  };

  const attachFilterChipHandler = (container) => {
    if (!container) {
      return;
    }
    container.addEventListener('click', (event) => {
      const target = event.target instanceof Element ? event.target.closest('.filter-chip') : null;
      if (!target) {
        return;
      }
      event.preventDefault();
      const filterType = target.getAttribute('data-filter-type');
      const filterValue = target.getAttribute('data-filter-value');
      if (!filterType) {
        return;
      }

      switch (filterType) {
        case 'situacao':
          if (filterValue) {
            filtersState.situacao = filtersState.situacao.filter((item) => item !== filterValue);
          }
          break;
        case 'diasMin':
          filtersState.diasMin = null;
          break;
        case 'saldoMin':
          filtersState.saldoMin = null;
          break;
        case 'dtRange':
          filtersState.dtRange = null;
          break;
        default:
          break;
      }

      applyFilters();
    });
  };

  const setupFilters = () => {
    context.filterWrappers = Array.from(document.querySelectorAll('[data-filter-group]'));
    if (!context.filterWrappers.length) {
      return;
    }

    context.filterWrappers.forEach((wrapper) => {
      const trigger = wrapper.querySelector('.table-filter__trigger');
      const dropdown = wrapper.querySelector('.table-filter__dropdown');
      if (!trigger || !dropdown) {
        return;
      }

      trigger.addEventListener('click', (event) => {
        event.stopPropagation();
        const isOpen = wrapper.classList.toggle('table-filter--open');
        context.filterWrappers.forEach((other) => {
          if (other !== wrapper) {
            other.classList.remove('table-filter--open');
            const otherTrigger = other.querySelector('.table-filter__trigger');
            if (otherTrigger) {
              otherTrigger.setAttribute('aria-expanded', 'false');
            }
          }
        });
        trigger.setAttribute('aria-expanded', String(isOpen));
      });

      dropdown.addEventListener('click', (event) => {
        event.stopPropagation();
      });

      const inputs = dropdown.querySelectorAll('[data-filter-input]');
      inputs.forEach((input) => {
        input.addEventListener('change', (event) => {
          const target = event.currentTarget;
          if (!(target instanceof HTMLInputElement)) {
            return;
          }
          const filterType = target.dataset.filterInput;
          if (!filterType) {
            return;
          }

          if (filterType === 'situacao') {
            const { value } = target;
            if (target.checked) {
              if (!filtersState.situacao.includes(value)) {
                filtersState.situacao.push(value);
              }
            } else {
              filtersState.situacao = filtersState.situacao.filter((item) => item !== value);
            }
            applyFilters();
            return;
          }

          if (filterType === 'dias') {
            filtersState.diasMin = Number(target.value);
            applyFilters({ closeDropdown: true });
            return;
          }

          if (filterType === 'saldo') {
            filtersState.saldoMin = Number(target.value);
            applyFilters({ closeDropdown: true });
            return;
          }

          if (filterType === 'dt') {
            filtersState.dtRange = target.value;
            applyFilters({ closeDropdown: true });
          }
        });
      });

      const clearButton = dropdown.querySelector('[data-filter-clear]');
      if (clearButton) {
        clearButton.addEventListener('click', (event) => {
          event.preventDefault();
          const filterType = clearButton.getAttribute('data-filter-clear');
          if (!filterType) {
            return;
          }
          clearFilter(filterType);
          applyFilters({ closeDropdown: true });
        });
      }
    });

    document.addEventListener('click', () => {
      closeAllFilterDropdowns();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        closeAllFilterDropdowns();
      }
    });

    syncFilterInputs();
    renderFilterChips();
  };

  context.hasActiveFilters = hasActiveFilters;
  context.resetFiltersState = resetFiltersState;
  context.renderFilterChips = renderFilterChips;
  context.syncFilterInputs = syncFilterInputs;
  context.applyFilters = applyFilters;
  context.clearAllFilters = clearAllFilters;
  context.attachFilterChipHandler = attachFilterChipHandler;
  context.closeAllFilterDropdowns = closeAllFilterDropdowns;
  context.setupFilters = setupFilters;
}
