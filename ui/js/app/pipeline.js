export function registerPipelineModule(context) {
  const state = context;
  const {
    PIPELINE_ENDPOINT,
    btnStart,
    btnPause,
    btnContinue,
    statusText,
    progressContainer,
    progressBar,
    lblLastUpdate,
    lblLastDuration,
  } = context;

  const defaultMessages = {
    idle: 'Ocioso',
    running: 'Executando',
    succeeded: 'Concluída',
    failed: 'Falha',
  };

  const setProgressVisibility = (visible) => {
    if (!progressContainer) {
      return;
    }

    progressContainer.classList.toggle('progress--hidden', !visible);
    progressContainer.setAttribute('aria-hidden', visible ? 'false' : 'true');
  };

  const stopProgressTimer = () => {
    if (state.progressIntervalHandle !== null) {
      window.clearInterval(state.progressIntervalHandle);
      state.progressIntervalHandle = null;
    }
  };

  const setProgressWidth = (ratio) => {
    if (!progressBar) {
      return;
    }

    const boundedRatio = Math.max(0, Math.min(ratio, 1));
    progressBar.style.width = `${(boundedRatio * 100).toFixed(2)}%`;
  };

  const tickProgress = () => {
    if (!progressBar || state.progressStartTimestamp === null) {
      return;
    }

    const elapsed = Math.max(0, Date.now() - state.progressStartTimestamp);
    const ratio = Math.min(
      elapsed / context.PROGRESS_TOTAL_DURATION_MS,
      context.PROGRESS_MAX_RATIO_BEFORE_COMPLETION,
    );
    setProgressWidth(ratio);
  };

  const beginProgressTracking = (startTimestamp) => {
    if (!progressBar) {
      return;
    }

    const normalizedTimestamp =
      typeof startTimestamp === 'number' && !Number.isNaN(startTimestamp)
        ? startTimestamp
        : Date.now();

    state.progressStartTimestamp = normalizedTimestamp;
    progressBar.classList.remove('progress__bar--complete');
    setProgressVisibility(true);
    tickProgress();
    stopProgressTimer();
    state.progressIntervalHandle = window.setInterval(tickProgress, 1000);
  };

  const completeProgressTracking = () => {
    if (!progressBar) {
      return;
    }

    setProgressVisibility(true);
    stopProgressTimer();
    progressBar.classList.add('progress__bar--complete');
    setProgressWidth(1);
  };

  const resetProgress = () => {
    stopProgressTimer();
    state.progressStartTimestamp = null;

    if (progressBar) {
      progressBar.classList.remove('progress__bar--complete');
      setProgressWidth(0);
    }

    setProgressVisibility(false);
  };

  const parseTimestamp = (value) => {
    if (!value) {
      return null;
    }

    if (value instanceof Date) {
      return value.getTime();
    }

    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }

    if (typeof value === 'string') {
      const timestamp = Date.parse(value);
      return Number.isNaN(timestamp) ? null : timestamp;
    }

    return null;
  };

  const updateProgressFromState = (pipelineState) => {
    if (!progressContainer || !progressBar) {
      return;
    }

    const status = pipelineState.status;
    const startedTimestamp = parseTimestamp(pipelineState.started_at);

    if (status === 'running') {
      const effectiveStart =
        startedTimestamp ?? state.progressStartTimestamp ?? Date.now();
      beginProgressTracking(effectiveStart);
      return;
    }

    if (status === 'succeeded') {
      if (startedTimestamp && state.progressStartTimestamp === null) {
        state.progressStartTimestamp = startedTimestamp;
      }
      completeProgressTracking();
      return;
    }

    resetProgress();
  };

  const toggleButtons = ({ start, pause, cont }) => {
    if (!context.canAccessBase?.()) {
      [btnStart, btnPause, btnContinue].forEach((btn) => {
        if (!btn) {
          return;
        }
        btn.disabled = true;
        btn.classList.add('btn--disabled');
        btn.setAttribute('aria-disabled', 'true');
      });
      return;
    }

    if (btnStart) {
      btnStart.disabled = !start;
      btnStart.classList.toggle('btn--disabled', btnStart.disabled);
    }
    if (btnPause) {
      btnPause.disabled = !pause;
      btnPause.classList.toggle('btn--disabled', btnPause.disabled);
      btnPause.classList.toggle('btn--ghost', true);
    }
    if (btnContinue) {
      btnContinue.disabled = !cont;
      btnContinue.classList.toggle('btn--disabled', btnContinue.disabled);
      btnContinue.classList.toggle('btn--ghost', true);
    }
  };

  const stopPolling = () => {
    if (state.pollHandle !== null) {
      window.clearInterval(state.pollHandle);
      state.pollHandle = null;
    }
  };

  const refreshPipelineMeta = async () => {
    if (!context.canAccessBase?.()) {
      context.setText?.(lblLastUpdate, '', null);
      context.setText?.(lblLastDuration, '', null);
      return null;
    }
    if (state.isFetchingPipelineMeta) {
      return null;
    }
    state.isFetchingPipelineMeta = true;
    try {
      if (state.pipelineMetaController) {
        state.pipelineMetaController.abort();
      }
      state.pipelineMetaController = new AbortController();
      const baseUrl =
        window.location.origin && window.location.origin !== 'null'
          ? window.location.origin
          : window.location.href;
      const url = new URL(`${PIPELINE_ENDPOINT}/status`, baseUrl);
      url.searchParams.set('job_name', 'gestao_base');
      const headers = new Headers({ Accept: 'application/json' });
      const matricula = state.currentUser?.username?.trim();
      if (matricula) {
        headers.set('X-User-Registration', matricula);
      }
      const response = await fetch(url.toString(), {
        headers,
        signal: state.pipelineMetaController.signal,
      });
      if (!response.ok) {
        throw new Error('Não foi possível consultar o status da pipeline.');
      }
      const payload = await response.json();
      const lastUpdateAt = payload?.last_update_at ?? null;
      const durationText = payload?.duration_text ?? null;
      const formattedDuration = context.formatDurationLabel?.(durationText);
      context.setText?.(lblLastUpdate, '', context.formatDateTime?.(lastUpdateAt));
      context.setText?.(lblLastDuration, '', formattedDuration);
      return payload;
    } catch (error) {
      console.error('Falha ao carregar metadados da pipeline.', error);
      context.setText?.(lblLastUpdate, '', null);
      context.setText?.(lblLastDuration, '', null);
      return null;
    } finally {
      state.pipelineMetaController = null;
      state.isFetchingPipelineMeta = false;
    }
  };

  const applyState = (pipelineState) => {
    const message =
      pipelineState.message || defaultMessages[pipelineState.status] || defaultMessages.idle;
    updateProgressFromState(pipelineState);
    const runningPlan = context.resolveRunningPlanFromState?.(pipelineState);
    context.updateRunningPlanInfo?.(runningPlan);
    switch (pipelineState.status) {
      case 'running':
        toggleButtons({ start: false, pause: true, cont: false });
        state.shouldRefreshPlansAfterRun = true;
        break;
      case 'succeeded':
      case 'failed':
      case 'idle':
      default:
        toggleButtons({ start: true, pause: false, cont: false });
        if (state.shouldRefreshPlansAfterRun) {
          state.shouldRefreshPlansAfterRun = false;
          void context.refreshPlans?.({ showLoading: false });
          void context.refreshOccurrences?.({ showLoading: false });
        }
        break;
    }
    context.setStatus?.(message);
  };

  const fetchPipelineState = async () => {
    if (!context.canAccessBase?.()) {
      return null;
    }
    try {
      const response = await fetch(`${PIPELINE_ENDPOINT}/state`, {
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) {
        throw new Error('Não foi possível consultar o estado da pipeline.');
      }
      return await response.json();
    } catch (error) {
      console.error(error);
      return null;
    }
  };

  const schedulePolling = () => {
    if (!context.canAccessBase?.()) {
      stopPolling();
      return;
    }
    stopPolling();
    state.pollHandle = window.setInterval(async () => {
      const pipelineState = await fetchPipelineState();
      if (pipelineState) {
        applyState(pipelineState);
        await refreshPipelineMeta();
        if (pipelineState.status !== 'running') {
          stopPolling();
        }
      }
    }, 5000);
  };

  const startPipeline = async () => {
    if (!context.canAccessBase?.()) {
      context.showPermissionDeniedToast?.();
      return;
    }
    toggleButtons({ start: false, pause: false, cont: false });
    context.setStatus?.('Iniciando...');

    try {
      const payload = {};
      if (state.currentUser?.username) {
        payload.matricula = state.currentUser.username;
      }

      const response = await fetch(`${PIPELINE_ENDPOINT}/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({ detail: 'Erro desconhecido.' }));
        throw new Error(errorPayload.detail || 'Não foi possível iniciar a pipeline.');
      }

      const pipelineState = await response.json();
      applyState(pipelineState);
      void refreshPipelineMeta();
      if (pipelineState.status === 'running') {
        schedulePolling();
      }
    } catch (error) {
      console.error(error);
      context.setStatus?.(`Erro: ${error.message}`);
      toggleButtons({ start: true, pause: false, cont: false });
      resetProgress();
    }
  };

  if (btnStart) {
    btnStart.addEventListener('click', () => {
      void startPipeline();
    });
  }

  if (btnPause) {
    btnPause.addEventListener('click', () => {
      toggleButtons({ start: false, pause: false, cont: true });
      context.setStatus?.('Pausado');
    });
  }

  if (btnContinue) {
    btnContinue.addEventListener('click', () => {
      toggleButtons({ start: false, pause: true, cont: false });
      context.setStatus?.('Executando');
    });
  }

  document.addEventListener('visibilitychange', async () => {
    if (document.hidden) {
      stopPolling();
      return;
    }
    if (!context.canAccessBase?.()) {
      return;
    }
    const pipelineState = await fetchPipelineState();
    if (pipelineState) {
      applyState(pipelineState);
      await refreshPipelineMeta();
      if (pipelineState.status === 'running') {
        schedulePolling();
      }
    }
  });

  context.refreshPipelineMeta = refreshPipelineMeta;
  context.togglePipelineButtons = toggleButtons;
  context.resetProgress = resetProgress;
  context.updateProgressFromState = updateProgressFromState;
  context.fetchPipelineState = fetchPipelineState;
  context.schedulePolling = schedulePolling;
  context.stopPolling = stopPolling;
  context.applyPipelineState = applyState;
  context.startPipeline = startPipeline;
}
