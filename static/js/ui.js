// ui.js - Shared UI utilities (toasts, etc.)
// Requires Alpine.js loaded on the page.

(function(){
  // Alpine store for toast notifications
  window.toastStore = function() {
    return {
      visible: false,
      message: '',
      type: 'info',
      timeoutId: null,
      duration: 4000,
      bgClass() {
        switch(this.type) {
          case 'success': return 'bg-green-600';
          case 'error':   return 'bg-red-600';
          case 'warning': return 'bg-yellow-600 text-gray-900';
          default:        return 'bg-blue-600';
        }
      },
      show(message, type = 'info', duration = 4000) {
        this.message = message;
        this.type = type;
        this.duration = duration;
        this.visible = true;
        clearTimeout(this.timeoutId);
        this.timeoutId = setTimeout(() => { this.visible = false; }, this.duration);
      },
      init() {
        // Listen for global toast events
        document.addEventListener('toast', (e) => {
          const { message, type, duration } = e.detail;
          this.show(message, type, duration);
        });
      }
    };
  };

  // Convenience function for scripts to trigger toasts
  window.showToast = function(message, type = 'info', duration = 4000) {
    document.dispatchEvent(new CustomEvent('toast', { detail: { message, type, duration } }));
  };
})();
