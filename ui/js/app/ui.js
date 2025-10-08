export function registerUiModule(context) {
  const state = context;
  const { dateFromInput, dateToInput, openDateFromButton, openDateToButton } = context;

  const tooltipTimeouts = new WeakMap();

  const showCopyTooltip = (button) => {
    if (!button) {
      return;
    }

    const previousTimeout = tooltipTimeouts.get(button);
    if (typeof previousTimeout === 'number') {
      window.clearTimeout(previousTimeout);
    }

    button.setAttribute('data-tooltip-visible', 'true');

    const timeoutHandle = window.setTimeout(() => {
      button.removeAttribute('data-tooltip-visible');
      tooltipTimeouts.delete(button);
    }, 1500);

    tooltipTimeouts.set(button, timeoutHandle);
  };

  const copyToClipboard = async (value) => {
    if (!value) {
      return false;
    }

    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
        return true;
      }
    } catch (error) {
      console.warn('Falha ao copiar usando clipboard API.', error);
    }

    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', 'true');
    textarea.style.position = 'absolute';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.select();

    try {
      const success = document.execCommand('copy');
      return success;
    } catch (error) {
      console.error('Não foi possível copiar o valor.', error);
      return false;
    } finally {
      document.body.removeChild(textarea);
    }
  };

  const enhanceCopyableCell = (cell, { label }) => {
    if (!cell) {
      return;
    }

    const existingButton = cell.querySelector('.table__copy-trigger');
    const target = existingButton ?? cell;
    const currentText = target.textContent?.trim() ?? '';
    if (!currentText) {
      return;
    }

    const digits = context.stripDigits?.(currentText) ?? '';
    if (!digits) {
      return;
    }

    const ariaLabel = `${label} ${digits}. Clique para copiar.`;

    if (!existingButton) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'table__copy-trigger';
      button.dataset.copyValue = digits;
      button.dataset.tooltip = 'Item copiado';
      button.setAttribute('aria-label', ariaLabel);
      button.textContent = currentText;

      cell.classList.add('table__cell--copyable');
      cell.textContent = '';
      cell.appendChild(button);
      return;
    }

    existingButton.dataset.copyValue = digits;
    existingButton.setAttribute('aria-label', ariaLabel);
    if (!existingButton.dataset.tooltip) {
      existingButton.dataset.tooltip = 'Item copiado';
    }
    if (existingButton.textContent !== currentText) {
      existingButton.textContent = currentText;
    }
  };

  const applyCopyBehaviorToRow = (row) => {
    if (!row || row.classList.contains('table__row--empty')) {
      return;
    }

    const planCell = row.cells?.[0];
    if (planCell) {
      enhanceCopyableCell(planCell, { label: 'Plano' });
    }

    const documentCell = row.cells?.[1];
    if (documentCell) {
      enhanceCopyableCell(documentCell, { label: 'Documento' });
    }
  };

  const setupCopyableCells = () => {
    const tables = document.querySelectorAll('.data-table');
    if (!tables.length) {
      return;
    }

    tables.forEach((table) => {
      const tbody = table.tBodies?.[0];
      if (!tbody) {
        return;
      }

      Array.from(tbody.rows ?? []).forEach(applyCopyBehaviorToRow);

      tbody.addEventListener('click', async (event) => {
        const button = event.target instanceof HTMLElement
          ? event.target.closest('.table__copy-trigger')
          : null;
        if (!button) {
          return;
        }
        const value = button.dataset.copyValue ?? '';
        const success = await copyToClipboard(value);
        if (success) {
          showCopyTooltip(button);
        }
      });
    });
  };

  const applyDocumentFormatting = (row) => {
    if (!row) {
      return;
    }

    const documentCell = row.cells?.[1];
    if (!documentCell) {
      return;
    }

    const target = documentCell.querySelector('.table__copy-trigger') ?? documentCell;
    const current = target.textContent ?? '';
    const formatted = context.formatDocument?.(current);
    if (formatted && current.trim() !== formatted) {
      target.textContent = formatted;
    }

    if (target.classList.contains('table__copy-trigger')) {
      target.dataset.copyValue = context.stripDigits?.(target.textContent ?? '') ?? '';
    }
  };

  const setupDocumentObserver = () => {
    const tables = document.querySelectorAll('.data-table');
    if (!tables.length) {
      return;
    }

    tables.forEach((table) => {
      const tbody = table.tBodies?.[0];
      if (!tbody) {
        return;
      }

      const formatAllRows = () => {
        Array.from(tbody.rows ?? []).forEach((row) => applyDocumentFormatting(row));
      };

      formatAllRows();

      const observer = new MutationObserver(() => {
        formatAllRows();
      });

      observer.observe(tbody, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    });
  };

  const setupTableSwitching = () => {
    const tabs = Array.from(document.querySelectorAll('[data-table-target]'));
    const panels = Array.from(document.querySelectorAll('[data-table-panel]'));

    if (!tabs.length || !panels.length) {
      return;
    }

    const activateTable = (target) => {
      if (!target) {
        return;
      }

      tabs.forEach((tab) => {
        const isActive = tab.dataset.tableTarget === target;
        tab.classList.toggle('section-switch--active', isActive);
        tab.setAttribute('aria-selected', String(isActive));
        tab.setAttribute('tabindex', isActive ? '0' : '-1');
      });

      panels.forEach((panel) => {
        const isActive = panel.dataset.tablePanel === target;
        panel.classList.toggle('table-panel--hidden', !isActive);
        if (isActive) {
          panel.removeAttribute('hidden');
        } else {
          panel.setAttribute('hidden', 'hidden');
        }
      });

      context.setActiveSearchTarget?.(target);
      context.syncSearchInputValue?.();
      if (typeof context.scheduleOccurrencesCountUpdate === 'function') {
        context.scheduleOccurrencesCountUpdate();
      }
    };

    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => {
        activateTable(tab.dataset.tableTarget);
      });

      tab.addEventListener('keydown', (event) => {
        if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
          event.preventDefault();
          const direction = event.key === 'ArrowRight' ? 1 : -1;
          const nextIndex = (index + direction + tabs.length) % tabs.length;
          const nextTab = tabs[nextIndex];
          activateTable(nextTab.dataset.tableTarget);
          nextTab.focus();
        }
      });
    });

    const activeTab = tabs.find((tab) => tab.classList.contains('section-switch--active'));
    const initialTarget = activeTab?.dataset.tableTarget || tabs[0].dataset.tableTarget;
    activateTable(initialTarget);
  };

  const setupMainTabsSwitching = () => {
    const baseTab = document.getElementById('tab-base');
    const treatmentTab = document.getElementById('tab-treatment');
    const basePanel = document.getElementById('panel-base');
    const treatmentPanel = document.getElementById('panel-treatment');

    if (!baseTab || !treatmentTab || !basePanel || !treatmentPanel) {
      return;
    }

    const activate = (target) => {
      let desired = target;
      if (desired === 'base' && !context.canAccessBase?.()) {
        desired = 'treatment';
      }

      const isBase = desired === 'base';
      baseTab.classList.toggle('tabs__item--active', isBase);
      treatmentTab.classList.toggle('tabs__item--active', !isBase);
      baseTab.setAttribute('aria-selected', String(isBase));
      baseTab.setAttribute('tabindex', isBase ? '0' : context.canAccessBase?.() ? '0' : '-1');
      treatmentTab.setAttribute('aria-selected', String(!isBase));
      treatmentTab.setAttribute('tabindex', isBase ? '-1' : '0');

      basePanel.classList.toggle('card__panel--hidden', !isBase);
      treatmentPanel.classList.toggle('card__panel--hidden', isBase);
      if (isBase) {
        basePanel.removeAttribute('hidden');
        treatmentPanel.setAttribute('hidden', 'hidden');
      } else {
        treatmentPanel.removeAttribute('hidden');
        basePanel.setAttribute('hidden', 'hidden');
        void context.fetchTreatmentState?.({ refreshItems: !state.treatmentLoaded });
      }
    };

    const handleBaseClick = (event) => {
      event.preventDefault();
      if (!context.canAccessBase?.()) {
        return;
      }
      activate('base');
    };

    const handleTreatmentClick = (event) => {
      event.preventDefault();
      activate('treatment');
    };

    baseTab.addEventListener('click', handleBaseClick);
    treatmentTab.addEventListener('click', handleTreatmentClick);

    const handleKeyNav = (event) => {
      if (event.key === 'ArrowRight') {
        event.preventDefault();
        treatmentTab.focus();
        activate('treatment');
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        if (!context.canAccessBase?.()) {
          return;
        }
        baseTab.focus();
        activate('base');
      }
    };
    baseTab.addEventListener('keydown', handleKeyNav);
    treatmentTab.addEventListener('keydown', handleKeyNav);

    context.applyProfilePermissions?.();
    const isBaseInitiallyActive = baseTab.classList.contains('tabs__item--active');
    const initialTarget = context.canAccessBase?.() && isBaseInitiallyActive ? 'base' : 'treatment';
    activate(initialTarget);
  };

  const disableCalendarButton = (button) => {
    if (!button) {
      return;
    }
    button.disabled = true;
    button.setAttribute('aria-disabled', 'true');
    if (!button.title) {
      button.title = 'Calendário indisponível';
    }
  };

  const enableManualDateInput = (input) => {
    if (!input) {
      return;
    }
    input.readOnly = false;
    const manualHint = 'digite a data manualmente';
    const label = input.getAttribute('aria-label');
    if (label && !label.toLowerCase().includes(manualHint)) {
      input.setAttribute('aria-label', `${label} (digite a data manualmente)`);
    }
    if (!input.title) {
      input.title = 'Digite a data no formato dd/mm/aaaa';
    }
  };

  const fallbackDateInput = (input, button) => {
    enableManualDateInput(input);
    disableCalendarButton(button);
  };

  const registerPickerTriggers = (picker, input, button) => {
    if (!picker) {
      return;
    }

    const open = () => picker.open();
    if (input) {
      input.addEventListener('click', open);
    }
    if (button) {
      button.addEventListener('click', open);
    }
  };

  const initializeDatePicker = (input, button, options) => {
    if (!input) {
      disableCalendarButton(button);
      return null;
    }

    try {
      const picker = window.flatpickr(input, options);
      registerPickerTriggers(picker, input, button);
      return picker;
    } catch (error) {
      console.error('Não foi possível inicializar o calendário de data.', error);
      return null;
    }
  };

  const initializeDatePickers = () => {
    if (!dateFromInput && !dateToInput) {
      return;
    }

    if (typeof window.flatpickr !== 'function') {
      console.warn('flatpickr indisponível; habilitando entrada manual de datas.');
      fallbackDateInput(dateFromInput, openDateFromButton);
      fallbackDateInput(dateToInput, openDateToButton);
      return;
    }

    const options = {
      locale: window.flatpickr.l10ns?.pt ?? undefined,
      dateFormat: 'd/m/Y',
      allowInput: false,
    };

    const fromPicker = initializeDatePicker(dateFromInput, openDateFromButton, options);
    const toPicker = initializeDatePicker(dateToInput, openDateToButton, options);

    if (!fromPicker) {
      fallbackDateInput(dateFromInput, openDateFromButton);
    }
    if (!toPicker) {
      fallbackDateInput(dateToInput, openDateToButton);
    }
  };

  const setupLogsAccordion = () => {
    const logsToggle = document.getElementById('logsToggle');
    const logsPanel = document.getElementById('logsPanel');
    const accordion = logsToggle?.closest('.accordion');

    if (!logsToggle || !logsPanel || !accordion) {
      return;
    }

    const updateAccordionState = (isOpen) => {
      logsToggle.setAttribute('aria-expanded', String(isOpen));
      if (isOpen) {
        logsPanel.classList.add('is-open');
        accordion.classList.add('is-open');
      } else {
        logsPanel.classList.remove('is-open');
        accordion.classList.remove('is-open');
      }
    };

    logsToggle.addEventListener('click', () => {
      const isOpen = logsToggle.getAttribute('aria-expanded') === 'true';
      updateAccordionState(!isOpen);
    });

    logsToggle.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        const isOpen = logsToggle.getAttribute('aria-expanded') === 'true';
        updateAccordionState(!isOpen);
      }
    });

    updateAccordionState(false);
  };

  context.setupCopyableCells = setupCopyableCells;
  context.applyCopyBehaviorToRow = applyCopyBehaviorToRow;
  context.setupDocumentObserver = setupDocumentObserver;
  context.setupTableSwitching = setupTableSwitching;
  context.setupMainTabsSwitching = setupMainTabsSwitching;
  context.initializeDatePickers = initializeDatePickers;
  context.setupLogsAccordion = setupLogsAccordion;
}
