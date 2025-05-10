// static/js/authFlow.js
function authFlowComponent() {
  return {
    isLoggedIn: false,
    userEmail: null,
    creditBalance: null,
    authBillingEnabled: window.AUTH_BILLING_ENABLED,

    async init() {
      console.log('Auth flow initializing...', this);
      console.log('Initial isLoggedIn state:', this.isLoggedIn);
      console.log('Initial authBillingEnabled state:', this.authBillingEnabled);

      window.addEventListener('amplifyAuthReady', async (event) => {
        console.log('amplifyAuthReady event received:', event.detail);
        this.isLoggedIn = event.detail.isLoggedIn;
        this.authDisabled = event.detail.authDisabled;

        if (this.isLoggedIn && event.detail.user) {
          this.userEmail = event.detail.user.attributes ? event.detail.user.attributes.email : null;
          console.log('User is logged in via amplifyAuthReady, fetching user data...');
          await this.fetchUserData(event.detail.user);
        } else {
          console.log('User is NOT logged in or no user object in amplifyAuthReady event');
          this.userEmail = null;
          this.creditBalance = null;
          window.currentUserId = null;
          window.dispatchEvent(new CustomEvent('logoutSuccess'));
        }
      });

      if (window.location.hash.includes('id_token')) {
        console.log('Detected id_token in URL hash. Amplify should handle this and dispatch amplifyAuthReady.');
      }

      window.addEventListener('logoutSuccess', () => {
          console.log('Logout success event received, clearing user data in Alpine component...');
          this.isLoggedIn = false;
          this.userEmail = null;
          this.creditBalance = null;
          window.currentUserId = null;
      });
    },

    async fetchUserData(user = null) {
        console.log('Fetching user data from /users/me...');
        if (!this.isLoggedIn) {
          console.warn('fetchUserData called but isLoggedIn is false (or not yet true from event), aborting');
          return;
        }

        let userId = user ? (user.username || user.id || (user.attributes ? user.attributes.sub : null)) : window.currentUserId;

        if (!userId && window.currentUserId) {
          userId = window.currentUserId;
        }

        if (!userId) {
          console.error('fetchUserData: User ID not available from event.detail.user or window.currentUserId. Cannot fetch data.');
          return;
        }
        console.log('Using User ID for fetchUserData:', userId);

        try {
            console.log('window.authHeaders is defined:', typeof window.authHeaders === 'function');
            const headers = await window.authHeaders();
            console.log('Auth headers for /users/me:', headers);

            const response = await fetch('/users/me', { headers });
            if (!response.ok) {
                const errorText = await response.text();
                console.error(`Failed to fetch user data: ${response.status} ${response.statusText}`, errorText);
                if (response.status === 401 || response.status === 403) {
                    console.log('Auth error fetching user data, attempting to sign out user.');
                    this.isLoggedIn = false;
                    this.userEmail = null;
                    this.creditBalance = null;
                    window.currentUserId = null;
                    window.dispatchEvent(new CustomEvent('logoutSuccess'));
                }
                throw new Error(`Failed to fetch user data: ${response.statusText}`);
            }
            const userData = await response.json();
            console.log('User data received:', userData);
            this.userEmail = userData.email;
            this.creditBalance = userData.credits;
            console.log('Credit balance set to:', this.creditBalance);

            window.currentUserId = userData.id;

            if (window.connectSSE && window.currentUserId) {
              window.connectSSE(window.currentUserId);
            }

        } catch (error) {
            console.error('Error fetching user data:', error);
            this.isLoggedIn = false;
            this.userEmail = null;
            this.creditBalance = null;
            window.currentUserId = null;
            window.dispatchEvent(new CustomEvent('logoutSuccess'));
        }
    },

    handleLogin() {
      Auth.federatedSignIn();
    },

    async handleLogout() {
      console.log('handleLogout called');
      try {
          await Auth.signOut();
          console.log('User signed out successfully.');
          localStorage.removeItem('isLoggedIn');
          console.log('isLoggedIn removed from localStorage');
          window.dispatchEvent(new CustomEvent('logoutSuccess'));
      } catch (error) {
          console.error('Error signing out: ', error);
      }
    },

    async buyCredits() {
        if (!this.isLoggedIn) {
            console.warn('User not logged in, cannot buy credits.');
            return;
        }
        console.log('Attempting to buy credits...');
        try {
            const response = await fetch('/billing/checkout-session', {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  ...(await window.authHeaders())
                },
                body: JSON.stringify({ product_id: 'credits_50' })
            });
            if (!response.ok) {
                if (response.status === 401 || response.status === 403) {
                    console.error(`Authentication error (${response.status}) accessing /billing/checkout-session. Redirecting to login.`);
                    if (window.showToast) {
                        window.showToast("Your session may have expired. Please sign in again.", "error");
                    }
                    window.dispatchEvent(new CustomEvent('logoutSuccess'));
                    Auth.federatedSignIn();
                    return;
                }
                const errorData = await response.json().catch(() => ({ detail: `Server error: ${response.status}` }));
                throw new Error(errorData.detail || 'Failed to create Stripe checkout session');
            }
            const session = await response.json();
            console.log('Stripe session created:', session);
            if (session.url) {
                window.location.href = session.url;
            }
        } catch (error) {
            console.error('Error buying credits:', error);
            if (window.showToast) {
                window.showToast(`Error: ${error.message}`, 'error');
            }
        }
    }
  };
}

// Register the component with Alpine.js
document.addEventListener('alpine:init', () => {
  Alpine.data('authFlow', authFlowComponent);
});