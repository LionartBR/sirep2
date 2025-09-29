document.addEventListener('DOMContentLoaded', () => {
  if (window.feather) {
    window.feather.replace();
  }

  const statusText = document.getElementById('statusText');
  const btnStart = document.getElementById('btnStart');
  const btnPause = document.getElementById('btnPause');
  const btnContinue = document.getElementById('btnContinue');

  const setStatus = (text) => {
    statusText.textContent = `Estado: ${text}`;
  };

  const toggleButtons = ({ start, pause, cont }) => {
    btnStart.disabled = !start;
    btnPause.disabled = !pause;
    btnContinue.disabled = !cont;

    btnStart.classList.toggle('btn--disabled', btnStart.disabled);
    btnPause.classList.toggle('btn--disabled', btnPause.disabled);
    btnContinue.classList.toggle('btn--disabled', btnContinue.disabled);

    btnPause.classList.toggle('btn--ghost', true);
    btnContinue.classList.toggle('btn--ghost', true);
  };

  btnStart.addEventListener('click', () => {
    toggleButtons({ start: false, pause: true, cont: false });
    setStatus('Executando');
  });

  btnPause.addEventListener('click', () => {
    toggleButtons({ start: false, pause: false, cont: true });
    setStatus('Pausado');
  });

  btnContinue.addEventListener('click', () => {
    toggleButtons({ start: false, pause: true, cont: false });
    setStatus('Executando');
  });

  toggleButtons({ start: true, pause: false, cont: false });
  setStatus('Ocioso');

  const fromPicker = flatpickr('#date-from', {
    locale: flatpickr.l10ns.pt,
    dateFormat: 'd/m/Y',
    allowInput: false,
  });

  const toPicker = flatpickr('#date-to', {
    locale: flatpickr.l10ns.pt,
    dateFormat: 'd/m/Y',
    allowInput: false,
  });

  const openPicker = (picker) => {
    if (picker) {
      picker.open();
    }
  };

  document.getElementById('open-date-from').addEventListener('click', () => openPicker(fromPicker));
  document.getElementById('open-date-to').addEventListener('click', () => openPicker(toPicker));

  document.getElementById('date-from').addEventListener('click', () => openPicker(fromPicker));
  document.getElementById('date-to').addEventListener('click', () => openPicker(toPicker));

  const logsToggle = document.getElementById('logsToggle');
  const logsPanel = document.getElementById('logsPanel');
  const accordion = logsToggle.closest('.accordion');

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

  logsToggle.addEventListener('click', (event) => {
    const textSpan = logsToggle.querySelector('span');
    if (event.target !== textSpan) {
      return;
    }
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
});
