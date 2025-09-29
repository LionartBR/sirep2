(function () {
  const STORAGE_KEY = 'sirep.auth';
  let memorySession = null;

  const safeGetItem = (storage) => {
    if (!storage) {
      return null;
    }
    try {
      return storage.getItem(STORAGE_KEY);
    } catch (error) {
      console.warn('Não foi possível acessar o armazenamento.', error);
      return null;
    }
  };

  const safeSetItem = (storage, value) => {
    if (!storage) {
      return;
    }
    try {
      storage.setItem(STORAGE_KEY, value);
    } catch (error) {
      console.warn('Não foi possível salvar o estado de autenticação.', error);
    }
  };

  const safeRemoveItem = (storage) => {
    if (!storage) {
      return;
    }
    try {
      storage.removeItem(STORAGE_KEY);
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
    const sessionValue = safeParse(safeGetItem(window.sessionStorage));
    if (sessionValue) {
      memorySession = sessionValue;
      return sessionValue;
    }
    const persistentValue = safeParse(safeGetItem(window.localStorage));
    if (persistentValue) {
      memorySession = persistentValue;
      return persistentValue;
    }
    return memorySession;
  };

  const writeAuth = (value, { persistent }) => {
    memorySession = value;
    if (!value) {
      safeRemoveItem(window.sessionStorage);
      safeRemoveItem(window.localStorage);
      return;
    }

    const serialized = JSON.stringify(value);
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

  const login = ({ username, remember, name }) => {
    const now = new Date();
    const session = {
      username,
      name: name || username,
      authenticatedAt: now.toISOString(),
      token: generateToken(),
    };

    writeAuth(session, { persistent: Boolean(remember) });
    return session;
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

  window.Auth = {
    login,
    logout,
    isAuthenticated,
    getUser,
  };
})();
