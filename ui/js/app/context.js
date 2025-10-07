/* global Auth */

export function createAppContext() {
  const currentUser = Auth.getUser();

  const context = {
    currentUser,

    // Topbar references
    userNameLabel: document.getElementById('currentUserName'),
    signOutLink: document.querySelector('.topbar__signout'),

    // Pipeline controls
    statusText: document.getElementById('statusText'),
    btnStart: document.getElementById('btnStart'),
    btnPause: document.getElementById('btnPause'),
    btnContinue: document.getElementById('btnContinue'),
    btnCloseTreatment: document.getElementById('btnCloseTreatment'),
    progressContainer: document.querySelector('.progress'),
    progressBar: document.querySelector('.progress')?.querySelector('.progress__bar') ?? null,

    // Running plan details
    runningPlanNumberEl: document.getElementById('currentPlanNumber'),
    runningPlanDocumentEl: document.getElementById('currentPlanDocument'),
    runningPlanCompanyEl: document.getElementById('currentPlanCompanyName'),
    runningPlanStatusEl: document.getElementById('currentPlanStatus'),
    runningPlanStageEl: document.getElementById('currentPlanStage'),

    // Pipeline metadata labels
    lblLastUpdate: document.getElementById('lbl-last-update'),
    lblLastDuration: document.getElementById('lbl-last-duration'),

    // Date filters
    dateFromInput: document.getElementById('date-from'),
    dateToInput: document.getElementById('date-to'),
    openDateFromButton: document.getElementById('open-date-from'),
    openDateToButton: document.getElementById('open-date-to'),
  };

  // Plans table references
  context.plansTablePanel = document.getElementById('plansTablePanel');
  context.plansTableElement = context.plansTablePanel?.querySelector('table') ?? null;
  context.plansTableBody = context.plansTableElement?.tBodies?.[0] ?? null;
  context.plansColumnCount =
    context.plansTableElement?.tHead?.rows?.[0]?.cells?.length ??
    context.plansTableElement?.rows?.[0]?.cells?.length ??
    8;

  context.plansActionsMenuContainer = document.querySelector('[data-plans-actions-menu]');
  context.plansActionsTrigger = document.getElementById('plansActionsTrigger');
  context.plansActionsMenu = document.getElementById('plansActionsMenu');
  context.plansSelectAllAction = context.plansActionsMenu?.querySelector('[data-action="select-all"]') ?? null;
  context.plansSelectAllLabel = context.plansSelectAllAction?.querySelector('span') ?? null;
  context.plansLockAction = context.plansActionsMenu?.querySelector('[data-action="lock"]') ?? null;
  context.plansLockActionLabel = context.plansLockAction?.querySelector('span') ?? null;
  context.plansActionsSeparator = context.plansActionsMenu?.querySelector('[data-role="separator"]') ?? null;
  context.plansFiltersChipsContainer = document.getElementById('plansFiltersChips');
  context.occFiltersChipsContainer = document.getElementById('occFiltersChips');

  // Occurrences table references
  context.occTablePanel = document.getElementById('occurrencesTablePanel');
  context.occTableElement = context.occTablePanel?.querySelector('table') ?? null;
  context.occTableBody = context.occTableElement?.tBodies?.[0] ?? null;
  context.occColumnCount =
    context.occTableElement?.tHead?.rows?.[0]?.cells?.length ??
    context.occTableElement?.rows?.[0]?.cells?.length ??
    8;

  // Treatment table references
  context.treatmentPanelEl = document.getElementById('panel-treatment');
  context.treatmentTableElement = context.treatmentPanelEl?.querySelector('table.data-table') ?? null;
  context.treatmentTableBody = context.treatmentTableElement?.tBodies?.[0] ?? null;
  context.treatmentColumnCount =
    context.treatmentTableElement?.tHead?.rows?.[0]?.cells?.length ??
    context.treatmentTableElement?.rows?.[0]?.cells?.length ??
    6;
  context.treatmentPagerRange = document.getElementById('treatmentPagerRange');
  context.treatmentPagerLabel = document.getElementById('treatmentPagerLabel');
  context.treatmentPagerPrevBtn = document.getElementById('treatmentPagerPrev');
  context.treatmentPagerNextBtn = document.getElementById('treatmentPagerNext');

  context.plansPagerPrevBtn = document.getElementById('plansPagerPrev');
  context.plansPagerNextBtn = document.getElementById('plansPagerNext');
  context.plansPagerLabel = document.getElementById('plansPagerLabel');
  context.plansPagerRange = document.getElementById('plansPagerRange');

  context.occPagerPrevBtn = document.getElementById('occPagerPrev');
  context.occPagerNextBtn = document.getElementById('occPagerNext');
  context.occPagerLabel = document.getElementById('occPagerLabel');
  context.occPagerRange = document.getElementById('occPagerRange');

  context.kpiQueueEl = document.getElementById('kpiQueueCount');
  context.kpiRescindedEl = document.getElementById('kpiRescindedCount');
  context.kpiFailuresEl = document.getElementById('kpiFailuresCount');

  // Endpoints & constants
  context.PIPELINE_ENDPOINT = '/api/pipeline';
  context.PLANS_ENDPOINT = '/api/plans';
  context.TREATMENT_ENDPOINT = '/api/treatment';
  context.PROFILE_ENDPOINT = '/api/auth/me';
  context.DEFAULT_PLAN_PAGE_SIZE = 10;
  context.TREATMENT_GRID = 'PLANOS_P_RESCISAO';

  context.userProfile = typeof Auth?.getProfile === 'function' ? Auth.getProfile() : null;

  context.treatmentBatchId = null;
  context.treatmentTotals = { pending: 0, processed: 0, skipped: 0 };
  context.treatmentStatusFilter = 'pending';
  context.treatmentLoaded = false;

  context.tableSearchState = { plans: '', occurrences: '' };
  context.filtersState = {
    situacao: [],
    diasMin: null,
    saldoMin: null,
    dtRange: null,
  };
  context.plansSelection = new Set();
  context.FILTER_LABELS = {
    situacao: {
      EM_DIA: 'EM DIA',
      EM_ATRASO: 'EM ATRASO',
      P_RESCISAO: 'P. RESCISAO',
      SIT_ESPECIAL: 'SIT. ESPECIAL',
      RESCINDIDO: 'RESCINDIDO',
      LIQUIDADO: 'LIQUIDADO',
      GRDE_EMITIDA: 'GRDE Emitida',
    },
    diasMin: {
      90: '90+ dias',
      100: '100+ dias',
      120: '120+ dias',
    },
    saldoMin: {
      10000: 'R$ 10 mil+',
      50000: 'R$ 50 mil+',
      150000: 'R$ 150 mil+',
      500000: 'R$ 500 mil+',
      1000000: 'R$ 1 mi+',
    },
    dtRange: {
      LAST_3_MONTHS: 'Até 3 meses',
      LAST_2_MONTHS: 'Até 2 meses',
      LAST_MONTH: 'Até 1 mês',
      THIS_MONTH: 'Mês atual',
    },
  };

  context.plansHasResults = false;
  context.occHasResults = false;
  context.filterWrappers = [];
  context.currentPlansSearchTerm = '';
  context.currentOccurrencesSearchTerm = '';
  context.activeTableSearchTarget = 'plans';

  context.plansPager = {
    page: 1,
    pageSize: context.DEFAULT_PLAN_PAGE_SIZE,
    nextCursor: null,
    prevCursor: null,
    hasMore: false,
    totalCount: null,
    totalPages: null,
    showingFrom: 0,
    showingTo: 0,
    currentCursor: null,
    currentDirection: null,
  };

  context.occPager = {
    page: 1,
    pageSize: context.DEFAULT_PLAN_PAGE_SIZE,
    nextCursor: null,
    prevCursor: null,
    hasMore: false,
    totalCount: null,
    totalPages: null,
    showingFrom: 0,
    showingTo: 0,
  };

  context.treatmentPager = {
    page: 1,
    pageSize: context.DEFAULT_PLAN_PAGE_SIZE,
    nextCursor: null,
    prevCursor: null,
    hasMoreNext: false,
    hasMorePrev: false,
    lastCount: 0,
    currentCursor: null,
    currentDirection: 'next',
  };

  context.plansFetchController = null;
  context.occFetchController = null;
  context.pipelineMetaController = null;

  context.currencyFormatter = new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 2,
  });

  context.PROGRESS_TOTAL_DURATION_MS = 15 * 60 * 1000;
  context.PROGRESS_MAX_RATIO_BEFORE_COMPLETION = 0.99;
  context.progressStartTimestamp = null;
  context.progressIntervalHandle = null;

  context.pollHandle = null;
  context.isFetchingPipelineMeta = false;
  context.isFetchingPlans = false;
  context.isFetchingOccurrences = false;
  context.isFetchingTreatment = false;
  context.isFetchingTreatmentState = false;
  context.plansLoaded = false;
  context.occurrencesLoaded = false;

  context.permissionToastHandle = null;
  context.isPlansActionsMenuOpen = false;
  context.shouldRefreshPlansAfterRun = false;
  context.lastSuccessfulFinishedAt = null;
  context.scheduleOccurrencesCountUpdate = () => {};

  context.hasActiveFilters = () => false;
  context.resetFiltersState = () => {};
  context.renderFilterChips = () => {};
  context.syncFilterInputs = () => {};
  context.applyFilters = () => {};
  context.clearAllFilters = () => {};
  context.attachFilterChipHandler = () => {};

  context.resetPlansPagination = () => {};
  context.resetOccurrencesPagination = () => {};
  context.resetTreatmentPagination = () => {};

  context.refreshPlans = async () => undefined;
  context.refreshOccurrences = async () => undefined;
  context.refreshTreatment = async () => undefined;
  context.fetchTreatmentState = async () => null;
  context.buildTreatmentFilters = () => null;
  context.updateTreatmentKpis = () => {};

  context.togglePipelineButtons = () => {};
  context.refreshPipelineMeta = async () => null;
  context.fetchPipelineState = async () => null;
  context.schedulePolling = () => {};
  context.stopPolling = () => {};
  context.applyPipelineState = () => {};
  context.resetProgress = () => {};

  context.setupFilters = () => {};
  context.setupCopyableCells = () => {};
  context.setupDocumentObserver = () => {};
  context.setupOccurrencesSearchObserver = () => {};
  context.setupOccurrencesCounter = () => {};
  context.setupTableSwitching = () => {};
  context.setupMainTabsSwitching = () => {};
  context.initializeDatePickers = () => {};
  context.setupLogsAccordion = () => {};

  return context;
}
