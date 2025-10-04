(function () {
  const STORAGE_KEY = 'sirep.auth';
  let memorySession = null;
  const LEGACY_PROFILE_MAP = {
    admin: 'GESTOR',
    gestor: 'GESTOR',
    worker: 'RESCISAO',
    rescisao: 'RESCISAO',
  };

  const normalizeProfile = (value) => {
    if (!value) {
      return null;
    }
    const raw = String(value).trim();
    if (!raw) {
      return null;
    }
    const lower = raw.toLowerCase();
    const upper = raw.toUpperCase();
    const mapped = LEGACY_PROFILE_MAP[lower] || LEGACY_PROFILE_MAP[upper] || upper;
    if (mapped === 'GESTOR' || mapped === 'RESCISAO') {
      return mapped;
    }
    return null;
  };

  const normalizeSession = (session) => {
    if (!session || typeof session !== 'object') {
      return null;
    }
    const normalizedProfile = normalizeProfile(session.profile);
    const remember = Boolean(session.remember);
    const normalizedSession = {
      ...session,
      remember,
    };
    if (normalizedProfile) {
      normalizedSession.profile = normalizedProfile;
    } else if ('profile' in normalizedSession) {
      delete normalizedSession.profile;
    }
    return normalizedSession;
  };

  const safeGetItem = (storage, key = STORAGE_KEY) => {
    if (!storage) {
      return null;
    }
    try {
      return storage.getItem(key);
    } catch (error) {
      console.warn('Não foi possível acessar o armazenamento.', error);
      return null;
    }
  };

  const safeSetItem = (storage, value, key = STORAGE_KEY) => {
    if (!storage) {
      return;
    }
    try {
      storage.setItem(key, value);
    } catch (error) {
      console.warn('Não foi possível salvar o estado de autenticação.', error);
    }
  };

  const safeRemoveItem = (storage, key = STORAGE_KEY) => {
    if (!storage) {
      return;
    }
    try {
      storage.removeItem(key);
    } catch (error) {
      console.warn('Não foi possível remover o estado de autenticação.', error);
    }
  };

  const safeParse = (raw) => {
    try {
      if (!raw) {
        return null;
      }
      const parsed = JSON.parse(raw);
      if (typeof parsed !== 'object' || parsed === null) {
        return null;
      }
      return parsed;
    } catch (error) {
      console.warn('Não foi possível interpretar o estado de autenticação.', error);
      return null;
    }
  };

  const readAuth = () => {
    const sessionValue = normalizeSession(safeParse(safeGetItem(window.sessionStorage)));
    if (sessionValue) {
      memorySession = sessionValue;
      return sessionValue;
    }
    const persistentValue = normalizeSession(safeParse(safeGetItem(window.localStorage)));
    if (persistentValue) {
      memorySession = persistentValue;
      return persistentValue;
    }
    return normalizeSession(memorySession);
  };

  const writeAuth = (value, options = {}) => {
    const normalizedValue = normalizeSession(value);
    memorySession = normalizedValue ? { ...normalizedValue } : null;
    const persistent = options.persistent ?? Boolean(normalizedValue?.remember);
    if (!normalizedValue) {
      safeRemoveItem(window.sessionStorage);
      safeRemoveItem(window.localStorage);
      return;
    }

    const serialized = JSON.stringify(normalizedValue);
    if (persistent) {
      safeSetItem(window.localStorage, serialized);
      safeRemoveItem(window.sessionStorage);
    } else {
      safeSetItem(window.sessionStorage, serialized);
      safeRemoveItem(window.localStorage);
    }
  };

  const generateToken = () => {
    if (window.crypto?.getRandomValues) {
      const buffer = new Uint32Array(4);
      window.crypto.getRandomValues(buffer);
      return Array.from(buffer)
        .map((value) => value.toString(16).padStart(8, '0'))
        .join('');
    }
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  };

  const login = ({ username, remember, name, profile }) => {
    const now = new Date();
    const session = {
      username,
      name: name || username,
      authenticatedAt: now.toISOString(),
      token: generateToken(),
      remember: Boolean(remember),
    };

    const normalizedProfile = normalizeProfile(profile);
    if (normalizedProfile) {
      session.profile = normalizedProfile;
    }

    writeAuth(session, { persistent: session.remember });
    return memorySession;
  };

  const logout = () => {
    writeAuth(null, { persistent: false });
  };

  const isAuthenticated = () => {
    return Boolean(readAuth());
  };

  const getUser = () => {
    return readAuth();
  };

  const getProfile = () => {
    const session = readAuth();
    return normalizeProfile(session?.profile);
  };

  const setProfile = (perfil) => {
    const normalized = normalizeProfile(perfil);
    const session = readAuth();
    if (!session) {
      return null;
    }
    if (!normalized) {
      return session;
    }
    if (session.profile === normalized) {
      return session;
    }
    const updated = { ...session, profile: normalized };
    writeAuth(updated);
    return memorySession;
  };

  window.Auth = {
    login,
    logout,
    isAuthenticated,
    getUser,
    getProfile,
    setProfile,
  };
})();
