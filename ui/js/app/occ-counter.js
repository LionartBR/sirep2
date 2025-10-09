export function registerOccurrenceCounterModule(context) {
  const state = {
    isFetching: false,
    pendingHandle: null,
    pendingRefresh: false,
  };

  const getBadgeElements = () => {
    const elements = [];
    const quickFilterBadge =
      context.quickFilterOccurrencesBadge ??
      document.getElementById('occurrencesCountQuickFilter');
    if (quickFilterBadge instanceof HTMLElement) {
      elements.push(quickFilterBadge);
    }
    const legacyBadge = document.getElementById('occurrencesCount');
    if (legacyBadge instanceof HTMLElement && !elements.includes(legacyBadge)) {
      elements.push(legacyBadge);
    }
    return elements;
  };

  const clampCountText = (value) => {
    if (value <= 0) {
      return '0';
    }
    if (value > 99) {
      return '99+';
    }
    return String(value);
  };

  const applyCountToBadges = (total) => {
    const badges = getBadgeElements();
    const count = Number.isFinite(total) && total > 0 ? Math.trunc(total) : 0;
    const shouldHide = count <= 0;
    badges.forEach((badge) => {
      badge.dataset.count = String(count);
      badge.hidden = shouldHide;
      if (!shouldHide) {
        badge.textContent = clampCountText(count);
      }
    });
  };

  const buildRequestUrl = () => {
    const baseUrl =
      window.location.origin && window.location.origin !== 'null'
        ? window.location.origin
        : window.location.href;
    const url = new URL(context.PLANS_ENDPOINT ?? '/api/plans', baseUrl);
    url.searchParams.set('occurrences_only', 'true');
    url.searchParams.set('page', '1');
    url.searchParams.set('page_size', '1');

    const searchTerm = context.currentPlansSearchTerm ?? '';
    if (searchTerm) {
      url.searchParams.set('q', searchTerm);
    }

    const filtersState = context.filtersState ?? {};
    if (Array.isArray(filtersState.situacao) && filtersState.situacao.length) {
      filtersState.situacao.forEach((value) => {
        url.searchParams.append('situacao', value);
      });
    }
    if (typeof filtersState.diasRange === 'string' && filtersState.diasRange) {
      url.searchParams.set('dias_range', filtersState.diasRange);
    }
    if (filtersState.saldoMin !== null && filtersState.saldoMin !== undefined) {
      url.searchParams.set('saldo_min', String(filtersState.saldoMin));
    }
    if (filtersState.dtRange) {
      url.searchParams.set('dt_sit_range', filtersState.dtRange);
    }

    return url.toString();
  };

  const refreshOccurrencesCount = async () => {
    if (state.isFetching) {
      state.pendingRefresh = true;
      return;
    }

    const badges = getBadgeElements();
    if (!badges.length) {
      return;
    }

    state.isFetching = true;
    try {
      const headers = new Headers({ Accept: 'application/json' });
      const matricula = context.currentUser?.username?.trim();
      if (matricula) {
        headers.set('X-User-Registration', matricula);
      }
      const response = await fetch(buildRequestUrl(), { headers });
      if (!response.ok) {
        throw new Error(`Falha ao carregar contagem de ocorrências: ${response.status}`);
      }
      const payload = await response.json();
      const paging = payload?.paging;
      let total = null;
      if (paging && typeof paging === 'object' && typeof paging.total_count === 'number') {
        total = paging.total_count;
      }
      if (total === null && typeof payload?.total === 'number') {
        total = payload.total;
      }
      if (total === null && Array.isArray(payload?.items)) {
        total = payload.items.length;
      }
      applyCountToBadges(total ?? 0);
    } catch (error) {
      console.error('Erro ao atualizar a contagem de ocorrências.', error);
    } finally {
      state.isFetching = false;
      if (state.pendingRefresh) {
        state.pendingRefresh = false;
        scheduleOccurrencesCountUpdate();
      }
    }
  };

  const scheduleOccurrencesCountUpdate = () => {
    if (state.pendingHandle !== null) {
      return;
    }
    const raf = typeof window.requestAnimationFrame === 'function';
    if (raf) {
      state.pendingHandle = window.requestAnimationFrame(() => {
        state.pendingHandle = null;
        void refreshOccurrencesCount();
      });
      return;
    }
    state.pendingHandle = window.setTimeout(() => {
      state.pendingHandle = null;
      void refreshOccurrencesCount();
    }, 0);
  };

  context.refreshOccurrencesCount = refreshOccurrencesCount;
  context.scheduleOccurrencesCountUpdate = scheduleOccurrencesCountUpdate;

  scheduleOccurrencesCountUpdate();
}
