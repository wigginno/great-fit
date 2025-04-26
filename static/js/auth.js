/* auth.js – Cognito Hosted-UI token handling & helper headers */

(function () {
  // 1. Capture id_token from Cognito Hosted-UI redirect fragment
  const hash = window.location.hash;
  if (hash && hash.includes('id_token=')) {
    const params = new URLSearchParams(hash.slice(1));
    const token = params.get('id_token');
    if (token) {
      localStorage.setItem('id_token', token);
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
    if (!localStorage.getItem('id_token')) {
      // Not signed-in – nothing to do for now
      return;
    }
    try {
      const res = await fetch('/users/me', { headers: window.authHeaders() });
      if (res.ok) {
        const user = await res.json();
        window.currentUserId = user.id;
      } else {
        console.error('Failed to fetch /users/me', await res.text());
      }
    } catch (err) {
      console.error('Error fetching /users/me', err);
    }
  });
})();
