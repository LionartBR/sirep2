document.addEventListener('DOMContentLoaded', () => {
  if (!window.Auth) {
    console.error('Módulo de autenticação indisponível.');
    return;
  }

  if (Auth.isAuthenticated()) {
    window.location.replace('index.html');
    return;
  }

  const form = document.getElementById('loginForm');
  const usernameInput = document.getElementById('username');
  const passwordInput = document.getElementById('password');
  const rememberInput = document.getElementById('rememberMe');
  const feedback = document.getElementById('loginError');

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

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    showFeedback('');

    const credentials = validate();
    if (!credentials) {
      return;
    }

    const username = credentials.username;
    const displayName = username
      .split(/[\.\s_-]+/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');

    Auth.login({ username, remember: rememberInput.checked, name: displayName });
    form.reset();
    window.location.replace('index.html');
  });
});
