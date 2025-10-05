/* global flatpickr */
import { createAppContext } from './app/context.js';
import { registerHelperModule } from './app/helpers.js';
import { registerProfileModule } from './app/profile.js';
import { registerFiltersModule } from './app/filters.js';
import { registerPlansModule } from './app/plans.js';
import { registerOccurrencesModule } from './app/occurrences.js';
import { registerTreatmentModule } from './app/treatment.js';
import { registerSearchModule } from './app/search.js';
import { registerPipelineModule } from './app/pipeline.js';
import { registerUiModule } from './app/ui.js';

document.addEventListener('DOMContentLoaded', () => {
  const auth = window.Auth ?? globalThis.Auth ?? null;
  if (!auth || typeof auth.isAuthenticated !== 'function' || !auth.isAuthenticated()) {
    window.location.replace('/app/login.html');
    return;
  }

  if (window.feather) {
    window.feather.replace();
  }

  const context = createAppContext();

  context.formatDocument = (value) => {
    if (window.SirepUtils?.formatDocument) {
      return window.SirepUtils.formatDocument(value);
    }
    return String(value ?? '');
  };

  registerHelperModule(context);
  registerProfileModule(context);
  registerFiltersModule(context);
  registerPlansModule(context);
  registerOccurrencesModule(context);
  registerTreatmentModule(context);
  registerSearchModule(context);
  registerPipelineModule(context);
  registerUiModule(context);

  context.updateUserName?.();
  context.setupSignOut?.();

  context.refreshProfileFromStore?.();
  context.applyProfilePermissions?.();

  context.setupFilters?.();
  context.setupCopyableCells?.();
  context.setupDocumentObserver?.();
  context.setupOccurrencesSearchObserver?.();
  context.setupOccurrencesCounter?.();
  context.setupTableSwitching?.();
  context.setupMainTabsSwitching?.();
  context.initializeDatePickers?.();
  context.setupLogsAccordion?.();

  context.togglePipelineButtons?.({ start: true, pause: false, cont: false });
  context.setStatus?.('Ocioso');
  context.resetProgress?.();
  context.updateTreatmentKpis?.();

  void context.refreshPlans?.({ showLoading: true });
  void context.refreshOccurrences?.({ showLoading: true });
  void context.fetchTreatmentState?.({ refreshItems: true });

  const loadPipelineState = async () => {
    if (!context.canAccessBase?.()) {
      return;
    }
    await context.refreshPipelineMeta?.();
    const pipelineState = await context.fetchPipelineState?.();
    if (pipelineState) {
      context.applyPipelineState?.(pipelineState);
      if (pipelineState.status === 'running') {
        context.schedulePolling?.();
      }
    } else {
      context.togglePipelineButtons?.({ start: true, pause: false, cont: false });
      context.setStatus?.('Ocioso');
    }
  };

  void loadPipelineState();
  void context.refreshUserProfile?.();
});
