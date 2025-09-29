/* global flatpickr */
document.addEventListener('DOMContentLoaded', () => {
  if (!window.Auth || !Auth.isAuthenticated()) {
    window.location.replace('login.html');
    return;
  }

  if (window.feather) {
    window.feather.replace();
  }

  const currentUser = Auth.getUser();
  const userNameLabel = document.getElementById('currentUserName');
  if (userNameLabel) {
    const displayName = currentUser?.name || currentUser?.username || 'Operador';
    userNameLabel.textContent = displayName;
  }

  const signOutLink = document.querySelector('.topbar__signout');
  if (signOutLink) {
    signOutLink.addEventListener('click', (event) => {
      event.preventDefault();
      Auth.logout();
      window.location.replace('login.html');
    });
  }

  const statusText = document.getElementById('statusText');
  const btnStart = document.getElementById('btnStart');
  const btnPause = document.getElementById('btnPause');
  const btnContinue = document.getElementById('btnContinue');

  const PIPELINE_ENDPOINT = '/api/pipeline';
  let pollHandle = null;

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

  const stopPolling = () => {
    if (pollHandle !== null) {
      window.clearInterval(pollHandle);
      pollHandle = null;
    }
  };

  const defaultMessages = {
    idle: 'Ocioso',
    running: 'Executando',
    succeeded: 'Concluída',
    failed: 'Falha',
  };

  toggleButtons({ start: true, pause: false, cont: false });
  setStatus(defaultMessages.idle);

  const schedulePolling = () => {
    stopPolling();
    pollHandle = window.setInterval(async () => {
      const state = await fetchPipelineState();
      if (state) {
        applyState(state);
        if (state.status !== 'running') {
          stopPolling();
        }
      }
    }, 5000);
  };

  const applyState = (state) => {
    const message = state.message || defaultMessages[state.status] || defaultMessages.idle;
    switch (state.status) {
      case 'running':
        toggleButtons({ start: false, pause: true, cont: false });
        break;
      case 'succeeded':
      case 'failed':
      case 'idle':
      default:
        toggleButtons({ start: true, pause: false, cont: false });
        break;
    }
    setStatus(message);
  };

  const fetchPipelineState = async () => {
    try {
      const response = await fetch(`${PIPELINE_ENDPOINT}/state`, { headers: { 'Accept': 'application/json' } });
      if (!response.ok) {
        throw new Error('Não foi possível consultar o estado da pipeline.');
      }
      return await response.json();
    } catch (error) {
      console.error(error);
      return null;
    }
  };

  const startPipeline = async () => {
    toggleButtons({ start: false, pause: false, cont: false });
    setStatus('Iniciando...');

    try {
      const response = await fetch(`${PIPELINE_ENDPOINT}/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({ detail: 'Erro desconhecido.' }));
        throw new Error(payload.detail || 'Não foi possível iniciar a pipeline.');
      }

      const state = await response.json();
      applyState(state);
      if (state.status === 'running') {
        schedulePolling();
      }
    } catch (error) {
      console.error(error);
      setStatus(`Erro: ${error.message}`);
      toggleButtons({ start: true, pause: false, cont: false });
    }
  };

  btnStart.addEventListener('click', () => {
    startPipeline();
  });

  btnPause.addEventListener('click', () => {
    toggleButtons({ start: false, pause: false, cont: true });
    setStatus('Pausado');
  });

  btnContinue.addEventListener('click', () => {
    toggleButtons({ start: false, pause: true, cont: false });
    setStatus('Executando');
  });

  (async () => {
    const state = await fetchPipelineState();
    if (state) {
      applyState(state);
      if (state.status === 'running') {
        schedulePolling();
      }
    } else {
      toggleButtons({ start: true, pause: false, cont: false });
      setStatus(defaultMessages.idle);
    }
  })();

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
