document.addEventListener('DOMContentLoaded', () => {
  if (!window.Auth) {
    console.error('Módulo de autenticação indisponível.');
    return;
  }

  if (window.feather) {
    window.feather.replace();
  }

  if (Auth.isAuthenticated()) {
    window.location.replace('/app/index.html');
    return;
  }

  const form = document.getElementById('loginForm');
  const usernameInput = document.getElementById('username');
  const passwordInput = document.getElementById('password');
  const rememberInput = document.getElementById('rememberMe');
  const feedback = document.getElementById('loginError');
  const submitButton = document.querySelector('.login-form__submit');

  const setLoadingState = (isLoading) => {
    if (!submitButton) {
      return;
    }
    submitButton.disabled = isLoading;
    submitButton.classList.toggle('is-loading', isLoading);
    submitButton.setAttribute('aria-busy', isLoading ? 'true' : 'false');
  };

  setLoadingState(false);

  window.setTimeout(() => {
    if (usernameInput) {
      usernameInput.focus();
    }
  }, 0);

  const showFeedback = (message) => {
    if (!feedback) {
      return;
    }
    feedback.textContent = message;
    feedback.hidden = !message;
  };

  const clearFeedback = () => {
    showFeedback('');
  };

  usernameInput.addEventListener('input', clearFeedback);
  passwordInput.addEventListener('input', clearFeedback);

  const validate = () => {
    const username = usernameInput.value.trim();
    const password = passwordInput.value.trim();

    if (!username || !password) {
      showFeedback('Informe usuário e senha para continuar.');
      return null;
    }

    if (password.length < 4) {
      showFeedback('A senha deve conter pelo menos 4 caracteres.');
      return null;
    }

    return { username, password };
  };

  const authenticate = async ({ username, password }) => {
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ matricula: username, senha: password }),
      });

      if (response.ok) {
        return;
      }

      let message = '';
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        try {
          const payload = await response.json();
          message = payload?.detail || '';
        } catch (error) {
          console.warn('Resposta de autenticação inválida.', error);
        }
      } else {
        try {
          message = (await response.text()) || '';
        } catch (error) {
          console.warn('Não foi possível ler a resposta de autenticação.', error);
        }
      }

      if (response.status === 401) {
        throw new Error(message || 'Usuário não autorizado.');
      }

      throw new Error(message || 'Não foi possível autenticar. Tente novamente.');
    } catch (error) {
      if (error instanceof TypeError) {
        throw new Error('Não foi possível conectar ao servidor. Tente novamente.');
      }
      throw error;
    }
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    showFeedback('');

    const credentials = validate();
    if (!credentials) {
      return;
    }

    setLoadingState(true);

    try {
      await authenticate(credentials);
    } catch (error) {
      setLoadingState(false);
      showFeedback(error.message || 'Não foi possível autenticar. Tente novamente.');
      return;
    }

    const username = credentials.username;
    const displayName = username
      .split(/[\.\s_-]+/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');

    Auth.login({
      username,
      remember: rememberInput.checked,
      name: displayName,
    });
    form.reset();
    window.location.replace('/app/index.html');
  });
});
