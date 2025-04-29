/**
 * auth.js - Authentication management using AWS Amplify
 * Handles Cognito Hosted UI login/logout via Authorization Code Grant w/ PKCE.
 */

// --- Configuration ---
function configureAmplify() {
  if (!window.COGNITO_USER_POOL_ID || !window.COGNITO_APP_CLIENT_ID || !window.COGNITO_DOMAIN) {
    console.warn("Cognito env vars not set, Amplify auth disabled.");
    return false; // Indicates auth is disabled
  }

  Amplify.configure({
    Auth: {
      region: window.AWS_REGION || 'us-east-1', // Fallback region if not set
      userPoolId: window.COGNITO_USER_POOL_ID,
      userPoolWebClientId: window.COGNITO_APP_CLIENT_ID,
      // OAUTH settings - REQUIRED for Authorization Code Grant
      oauth: {
        domain: window.COGNITO_DOMAIN, // e.g., your-domain.auth.us-east-1.amazoncognito.com
        scope: ['openid', 'email', 'profile'],
        redirectSignIn: window.location.origin + '/', // Redirect back to root after sign in
        redirectSignOut: window.location.origin + '/', // Redirect back to root after sign out
        responseType: 'code' // Must be 'code' for Authorization Code Grant
      }
    }
  });
  console.log("Amplify Auth configured.");
  return true; // Indicates auth is enabled
}

// --- Global State & Helpers ---
window.currentUserId = null; // Will be set after successful auth
window.authHeaders = async () => {
  if (window.AUTH_BILLING_ENABLED === false) {
    return {};
  }
  try {
    // Amplify automatically refreshes tokens if needed
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
    // Local development mode: backend auto-creates a default user. Fetch it so
    // the frontend knows the user_id, enabling profile and job loading after a page refresh.
    try {
      const res = await fetch('/users/me'); // No auth header needed in local mode
      if (res.ok) {
        const user = await res.json();
        window.currentUserId = user.id;
        console.log('Local mode: User ID set to', window.currentUserId);
        // Establish SSE connection once the user ID is known
        if (typeof connectToSSE === 'function') connectToSSE(window.currentUserId);
      } else {
        console.error('Local mode: Failed to fetch /users/me', await res.text());
      }
    } catch (err) {
      console.error('Local mode: Error fetching /users/me', err);
    }
    renderAuthNav(false, false);
    return;
  }

  const authEnabled = configureAmplify();
  if (!authEnabled) {
    // Auth disabled - try to fetch user info assuming local mode
    try {
      // Use the backend's local mode logic directly
      const res = await fetch('/users/me'); // No auth header needed in local mode
      if (res.ok) {
        const user = await res.json();
        window.currentUserId = user.id;
        console.log('Local mode: User ID set to', window.currentUserId);
        // Trigger SSE connection now that userId is set
        if (typeof connectToSSE === 'function') connectToSSE(window.currentUserId);
      } else {
        console.error('Local mode: Failed to fetch /users/me', await res.text());
      }
    } catch (err) {
      console.error('Local mode: Error fetching /users/me', err);
    }
    renderAuthNav(false, false); // Render as not logged in, auth disabled
    return;
  }

  // Auth enabled - use Amplify
  try {
    const user = await Auth.currentAuthenticatedUser();
    const session = await Auth.currentSession(); // Ensure session is valid
    const cognitoUser = await Auth.currentUserInfo();
    window.currentUserId = cognitoUser.attributes.sub; // Use Cognito 'sub' as ID
    console.log('User authenticated via Amplify:', cognitoUser.attributes);
    renderAuthNav(true, true); // Render as logged in, auth enabled

    // Now fetch our internal user record (to ensure it exists/create if needed)
    // This mimics the backend's get_current_user upsert logic which happens on first API hit anyway
    const meResponse = await fetch('/users/me', { headers: await window.authHeaders() });
    if (meResponse.ok) {
        const dbUser = await meResponse.json();
        // Optional: Verify dbUser.id matches cognitoUser.attributes.sub if needed,
        // though backend validation should handle mismatches.
        console.log('Backend user record confirmed/created for', dbUser.email);
        // Trigger SSE connection now that userId is set
        if (typeof connectToSSE === 'function') connectToSSE(dbUser.id);
    } else {
        console.error("Failed to verify/create backend user record via /users/me", await meResponse.text());
    }


  } catch (error) {
    // console.log('User not authenticated via Amplify:', error);
    window.currentUserId = null;
    renderAuthNav(false, true); // Render as not logged in, auth enabled
  }

  // Clean up Cognito code from URL if present (Amplify might do this, but belt-and-suspenders)
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
    document.getElementById('signInLink')?.addEventListener('click', (e) => {
        e.preventDefault();
        Auth.federatedSignIn(); // This initiates the redirect to Cognito Hosted UI
    });
  }
}

// --- Initialization ---
document.addEventListener('DOMContentLoaded', checkAuthState);
