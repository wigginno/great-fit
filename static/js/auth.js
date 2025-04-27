/* auth.js – Cognito Hosted-UI token handling & helper headers */

(function () {
  // 1. Capture id_token from Cognito Hosted-UI redirect fragment
  const hash = window.location.hash;
  if (hash && hash.includes('id_token=')) {
    const params = new URLSearchParams(hash.slice(1));
    const token = params.get('id_token');
    if (token) {
      localStorage.setItem('id_token', token);
      // Show nav as authenticated immediately
      renderAuthNav(true);
    }
    // Clean the URL (remove fragment)
    history.replaceState({}, document.title, window.location.pathname);
  }

  // 2. Global helper to attach Authorization header
  window.authHeaders = function () {
    const token = localStorage.getItem('id_token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  // 3. Fetch current user id once the DOM is ready
  document.addEventListener('DOMContentLoaded', async () => {
    try {
      const res = await fetch('/users/me', { headers: window.authHeaders() });
      if (res.ok) {
        const user = await res.json();
        window.currentUserId = user.id;
        renderAuthNav(!!localStorage.getItem('id_token'));
      } else if (res.status === 401) {
        console.warn('Not authenticated');
        renderAuthNav(false);
      } else {
        console.error('Failed to fetch /users/me', await res.text());
        renderAuthNav(false);
      }
    } catch (err) {
      console.error('Error fetching /users/me', err);
    }
  });

  async function logout() {
    localStorage.removeItem("id_token");
    window.currentUserId = undefined;
    renderAuthNav(false);
    location.reload();
  }

  function renderAuthNav(isAuthed) {
    const nav = document.getElementById("authNav");
    if (!nav) return;
    if (!window.COGNITO_DOMAIN || !window.COGNITO_APP_CLIENT_ID) {
      nav.innerHTML = ""; // hide in local mode
      return;
    }
    if (isAuthed) {
      nav.innerHTML = `<button id="signOutBtn" class="text-sm text-white hover:text-gray-200">Sign Out</button>`;
      document.getElementById("signOutBtn").addEventListener("click", logout);
    } else {
      const clientId = window.COGNITO_APP_CLIENT_ID;
      const domain = window.COGNITO_DOMAIN;
      const redirect = encodeURIComponent(window.location.origin + "/");
      const loginUrl = `${domain}/login?response_type=token&client_id=${clientId}&redirect_uri=${redirect}`;
      nav.innerHTML = `<a href="${loginUrl}" class="text-sm text-white hover:text-gray-200">Sign In</a>`;
    }
  }

  // Expose to other scripts if needed
  window.logout = logout;
  window.renderAuthNav = renderAuthNav;
})();
