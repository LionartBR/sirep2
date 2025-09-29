(function () {
  const STORAGE_KEY = 'sirep.auth';
  const PASSWORD_KEY = 'sirep.auth.password';
  let memorySession = null;
  let memoryPassword = null;

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

  const readPassword = () => {
    const sessionPassword = safeGetItem(window.sessionStorage, PASSWORD_KEY);
    if (sessionPassword) {
      memoryPassword = sessionPassword;
      return sessionPassword;
    }
    return memoryPassword;
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

  const writePassword = (value) => {
    memoryPassword = value || null;
    if (!value) {
      safeRemoveItem(window.sessionStorage, PASSWORD_KEY);
      return;
    }
    safeSetItem(window.sessionStorage, value, PASSWORD_KEY);
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

  const login = ({ username, remember, name, password }) => {
    const now = new Date();
    const session = {
      username,
      name: name || username,
      authenticatedAt: now.toISOString(),
      token: generateToken(),
    };

    writeAuth(session, { persistent: Boolean(remember) });
    writePassword(password);
    return session;
  };

  const logout = () => {
    writeAuth(null, { persistent: false });
    writePassword(null);
  };

  const isAuthenticated = () => {
    return Boolean(readAuth());
  };

  const getUser = () => {
    return readAuth();
  };

  const getPassword = () => {
    return readPassword();
  };

  window.Auth = {
    login,
    logout,
    isAuthenticated,
    getUser,
    getPassword,
  };
})();
