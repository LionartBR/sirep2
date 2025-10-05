export function registerProfileModule(context) {
  const winAuth = typeof window === 'object' ? window.Auth : undefined;
  const globalAuth = typeof globalThis === 'object' ? globalThis.Auth : undefined;
  const auth = winAuth ?? globalAuth ?? null;
  const canAccessBase = () => context.userProfile === 'GESTOR';

  const ensureToastElement = () => {
    let toast = document.getElementById('appToastMessage');
    if (toast) {
      return toast;
    }
    toast = document.createElement('div');
    toast.id = 'appToastMessage';
    toast.className = 'toast';
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    document.body.appendChild(toast);
    return toast;
  };

  context.showToast = (message) => {
    if (!message) {
      return;
    }
    const toast = ensureToastElement();
    toast.textContent = message;
    toast.classList.add('toast--visible');
    if (context.permissionToastHandle) {
      window.clearTimeout(context.permissionToastHandle);
    }
    context.permissionToastHandle = window.setTimeout(() => {
      toast.classList.remove('toast--visible');
    }, 3500);
  };

  context.showPermissionDeniedToast = () => {
    context.showToast("You don't have permission to view this area.");
  };

  context.refreshProfileFromStore = () => {
    if (typeof auth?.getProfile === 'function') {
      const storedProfile = auth.getProfile();
      if (storedProfile) {
        context.userProfile = storedProfile;
      }
    }
  };

  context.applyProfilePermissions = () => {
    const allowBase = canAccessBase();
    const baseTab = document.getElementById('tab-base');
    const treatmentTab = document.getElementById('tab-treatment');
    const basePanel = document.getElementById('panel-base');
    const treatmentPanel = document.getElementById('panel-treatment');

    if (baseTab) {
      if (allowBase) {
        baseTab.classList.remove('tabs__item--hidden');
        baseTab.removeAttribute('hidden');
        baseTab.setAttribute('aria-disabled', 'false');
        if (!baseTab.classList.contains('tabs__item--active')) {
          baseTab.setAttribute('tabindex', '0');
        }
      } else {
        baseTab.classList.remove('tabs__item--active');
        baseTab.classList.add('tabs__item--hidden');
        baseTab.setAttribute('hidden', 'hidden');
        baseTab.setAttribute('aria-disabled', 'true');
        baseTab.setAttribute('tabindex', '-1');
        baseTab.setAttribute('aria-selected', 'false');
      }
    }

    if (basePanel) {
      if (allowBase) {
        basePanel.classList.remove('card__panel--hidden');
        basePanel.removeAttribute('hidden');
      } else {
        basePanel.classList.add('card__panel--hidden');
        basePanel.setAttribute('hidden', 'hidden');
      }
    }

    if (treatmentPanel) {
      treatmentPanel.classList.remove('card__panel--hidden');
      treatmentPanel.removeAttribute('hidden');
    }

    if (!allowBase && treatmentTab) {
      treatmentTab.classList.add('tabs__item--active');
      treatmentTab.setAttribute('aria-selected', 'true');
      treatmentTab.setAttribute('tabindex', '0');
    }

    const pipelineButtons = [context.btnStart, context.btnPause, context.btnContinue];
    pipelineButtons.forEach((button) => {
      if (!button) {
        return;
      }
      if (!allowBase) {
        button.disabled = true;
        button.classList.add('btn--disabled');
        button.setAttribute('aria-disabled', 'true');
      } else {
        button.disabled = false;
        button.classList.remove('btn--disabled');
        button.setAttribute('aria-disabled', 'false');
      }
    });
  };

  const requestProfileFromServer = async () => {
    const matricula = context.currentUser?.username?.trim();
    if (!matricula) {
      return null;
    }
    try {
      const headers = new Headers({ Accept: 'application/json' });
      headers.set('X-User-Registration', matricula);
      const response = await fetch(context.PROFILE_ENDPOINT, { headers });
      if (!response.ok) {
        return null;
      }
      const payload = await response.json().catch(() => null);
      return payload?.perfil ?? null;
    } catch (error) {
      console.warn('Não foi possível obter o perfil do usuário.', error);
      return null;
    }
  };

  context.refreshUserProfile = async () => {
    const perfil = await requestProfileFromServer();
    if (!perfil) {
      return;
    }
    let normalizedProfile = perfil;
    if (typeof auth?.setProfile === 'function') {
      const updatedSession = auth.setProfile(perfil);
      if (updatedSession?.profile) {
        normalizedProfile = updatedSession.profile;
      }
    }
    if (normalizedProfile && normalizedProfile !== context.userProfile) {
      context.userProfile = normalizedProfile;
      context.applyProfilePermissions();
    }
  };

  context.updateUserName = () => {
    if (!context.userNameLabel) {
      return;
    }
    const displayName =
      context.currentUser?.name || context.currentUser?.username || 'Operador';
    context.userNameLabel.textContent = displayName;
  };

  context.setupSignOut = () => {
    if (!context.signOutLink) {
      return;
    }
    context.signOutLink.addEventListener('click', (event) => {
      event.preventDefault();
      if (typeof auth?.logout === 'function') {
        auth.logout();
      }
      window.location.replace('/app/login.html');
    });
  };

  context.canAccessBase = canAccessBase;
}
