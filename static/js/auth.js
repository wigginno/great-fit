/**
 * auth.js - Authentication management using AWS Amplify
 * Handles Cognito Hosted UI login/logout via Authorization Code Grant w/ PKCE.
 */

// --- Configuration ---
let amplifyConfigPromise = null;

function configureAmplify() {
  if (amplifyConfigPromise) {
    return amplifyConfigPromise;
  }

  amplifyConfigPromise = new Promise((resolve, reject) => {
    if (!window.COGNITO_USER_POOL_ID || !window.COGNITO_APP_CLIENT_ID || !window.COGNITO_DOMAIN) {
      const errMsg = "Cognito env vars not set, Amplify auth disabled.";
      console.warn(errMsg);
      reject(new Error(errMsg)); // Reject if auth cannot be configured
      return;
    }

    try {
      const amplifyAuthConfig = {
        Auth: {
          region: window.AWS_REGION || 'us-east-1', // Fallback region if not set
          userPoolId: window.COGNITO_USER_POOL_ID,
          userPoolWebClientId: window.COGNITO_APP_CLIENT_ID,
          oauth: {
            domain: window.COGNITO_DOMAIN,
            scope: ['openid', 'email', 'profile'],
            redirectSignIn: window.location.origin + '/',
            redirectSignOut: window.location.origin + '/',
            responseType: 'code'
          }
        }
      };
      /* 1️⃣  Always call configure — Amplify.merge ensures idempotency.
         This overwrites / extends any bare‑bones config created by the
         bundle itself, so required Auth keys are guaranteed to exist. */
      Amplify.configure(amplifyAuthConfig);
      console.log("Amplify Auth configured (merged) successfully.");
      resolve(true); // Resolve indicating auth is configured and enabled
    } catch (error) {
      console.error("Error configuring Amplify:", error);
      reject(error); // Reject on configuration error
    }
  });
  return amplifyConfigPromise;
}

// --- Global State & Helpers ---
window.currentUserId = null; // Will be set after successful auth
window.authHeaders = async () => {
  if (window.AUTH_BILLING_ENABLED === false) {
    return {};
  }

  try {
    await configureAmplify(); // Ensure Amplify is configured
  } catch (configError) {
    console.error('Amplify configuration failed, cannot get auth headers:', configError);
    return {}; // Cannot get headers if Amplify isn't configured
  }

  if (window.location.search.includes('code=')) {
    // let Amplify exchange the code first
    // This delay might still be needed if Auth.currentSession() is called too soon after redirect
    await new Promise(r => setTimeout(r, 800));
  }

  try {
    const session = await Auth.currentSession();
    const idToken = session.getIdToken().getJwtToken();
    return idToken ? { Authorization: `Bearer ${idToken}` } : {};
  } catch (error) {
    // console.log('No active session found for authHeaders:', error);
    return {}; // No authenticated session
  }
};

// --- Core Auth Logic ---
async function checkAuthState() {
  if (window.AUTH_BILLING_ENABLED === false) {
    // Local development mode
    let localUser = null;
    try {
      const res = await fetch('/users/me');
      if (res.ok) {
        localUser = await res.json();
        window.currentUserId = localUser.id;
        console.log('Local mode: User ID set to', window.currentUserId);
        if (typeof connectToSSE === 'function') connectToSSE(window.currentUserId);
      } else {
        console.error('Local mode: Failed to fetch /users/me', await res.text());
      }
    } catch (err) {
      console.error('Local mode: Error fetching /users/me', err);
    }
    renderAuthNav(false, false);
    // Dispatch event indicating auth state (local mode, Amplify not used)
    window.dispatchEvent(new CustomEvent('amplifyAuthReady', {
      detail: { isLoggedIn: !!localUser, user: localUser, error: null, authDisabled: true }
    }));
    return;
  }

  // Auth enabled - attempt to configure and use Amplify
  let authEnabled = false;
  let configError = null;
  try {
    await configureAmplify();
    authEnabled = true; // If configureAmplify resolves, it's enabled
  } catch (error) {
    console.error('Failed to configure Amplify for checkAuthState:', error);
    configError = error;
    // authEnabled remains false
  }

  if (!authEnabled) {
    // Configuration failed or Cognito vars not set
    renderAuthNav(false, false); // Render as not logged in, auth effectively disabled
    window.dispatchEvent(new CustomEvent('amplifyAuthReady', {
      detail: { isLoggedIn: false, user: null, error: configError, authDisabled: true } // True because Amplify cannot be used
    }));
    return;
  }

  // Amplify is configured (or at least configuration was attempted and didn't throw an unhandled error here)
  try {
    const user = await Auth.currentAuthenticatedUser();
    const session = await Auth.currentSession();
    const idToken = session.getIdToken().getJwtToken();

    if (idToken) {
      localStorage.setItem('id_token', idToken);
      localStorage.setItem('isLoggedIn', 'true');
      console.log('auth.js: id_token and isLoggedIn set in localStorage.');
    } else {
      console.warn('auth.js: No idToken found in session to set in localStorage.');
    }
    const idPayload = session.getIdToken().decodePayload();
    window.currentUserId = idPayload.sub;
    console.log('User authenticated via Amplify (from idToken):', idPayload);
    renderAuthNav(true, true);

    // Dispatch event: success
    window.dispatchEvent(new CustomEvent('amplifyAuthReady', {
      detail: { isLoggedIn: true, user: user.attributes || idPayload, error: null, authDisabled: false }
    }));

    const meResponse = await fetch('/users/me', { headers: await window.authHeaders() });
    if (meResponse.ok) {
      const dbUser = await meResponse.json();
      console.log('Backend user record confirmed/created for', dbUser.email);
      if (typeof connectToSSE === 'function') connectToSSE(dbUser.id);
    } else {
      console.error("Failed to verify/create backend user record via /users/me", await meResponse.text());
    }

  } catch (authError) {
    console.log('User not authenticated via Amplify:', authError);
    window.currentUserId = null;
    localStorage.removeItem('id_token');
    localStorage.removeItem('isLoggedIn');
    console.log('auth.js: id_token and isLoggedIn removed from localStorage due to auth error.');
    renderAuthNav(false, true);

    // Dispatch event: not authenticated
    window.dispatchEvent(new CustomEvent('amplifyAuthReady', {
      detail: { isLoggedIn: false, user: null, error: authError, authDisabled: false }
    }));

    // Only redirect if on the main page ('/') and auth is enabled (which it is at this point if we reached here)
    if (window.location.pathname === '/') {
      console.log("User not authenticated on main page, redirecting to login...");
      await configureAmplify(); // Ensure configured before sign-in attempt
      Auth.federatedSignIn();
    }
  }

  if (window.location.search.includes('code=')) {
    const nextURL = window.location.origin + window.location.pathname;
    window.history.replaceState({}, document.title, nextURL);
  }
}

// --- UI Functions ---
function renderAuthNav(isAuthed, authEnabled) {
  const nav = document.getElementById('authNav');
  if (!nav) return;

  if (!authEnabled) {
    nav.innerHTML = ''; // Hide sign-in/out in local mode
    return;
  }

  if (isAuthed) {
    nav.innerHTML = `<button id="signOutBtn" class="text-sm text-white hover:text-gray-200">Sign Out</button>`;
    document.getElementById('signOutBtn')?.addEventListener('click', () => Auth.signOut());
  } else {
    // Use Amplify's federatedSignIn which handles the redirect based on config
    nav.innerHTML = `<a href="#" id="signInLink" class="text-sm text-white hover:text-gray-200">Sign In</a>`;
    document.getElementById('signInLink')?.addEventListener('click', async (e) => {
        e.preventDefault();
        try {
          await configureAmplify();
          Auth.federatedSignIn(); // This initiates the redirect to Cognito Hosted UI
        } catch (error) {
          console.error("Failed to configure Amplify before federated sign-in in renderAuthNav:", error);
          // Optionally, display a message to the user or handle appropriately
        }
    });
  }
}

// --- Initialization ---
/* 2️⃣  Kick‑off configuration as soon as auth.js is parsed, so nothing
       calls Auth.* before the promise has settled. */
configureAmplify().catch(() => {});      // swallow here; handled later

document.addEventListener('DOMContentLoaded', checkAuthState);
