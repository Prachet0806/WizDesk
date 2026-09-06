/**
 * WizDesk Theme Engine
 * Handles light/dark/system theme switching with localStorage persistence
 */

(function() {
  'use strict';

  const THEME_KEY = 'wizdesk-theme';
  const THEME_ATTR = 'data-theme';
  const UI_VERSION_ATTR = 'data-ui';

  const THEMES = {
    LIGHT: 'light',
    DARK: 'dark',
    SYSTEM: 'system'
  };

  let currentTheme = THEMES.LIGHT;
  let systemPrefersDark = false;
  let listeners = [];

  /**
   * Check if system prefers dark mode
   */
  function checkSystemPreference() {
    try {
      return window.matchMedia('(prefers-color-scheme: dark)').matches;
    } catch (e) {
      return false;
    }
  }

  /**
   * Get the effective theme (resolves 'system' to actual theme)
   */
  function getEffectiveTheme(theme) {
    if (theme === THEMES.SYSTEM) {
      return systemPrefersDark ? THEMES.DARK : THEMES.LIGHT;
    }
    return theme;
  }

  /**
   * Apply theme to document
   */
  function applyTheme(theme) {
    const effectiveTheme = getEffectiveTheme(theme);
    document.documentElement.setAttribute(THEME_ATTR, effectiveTheme);
    document.documentElement.setAttribute(UI_VERSION_ATTR, 'v2');

    // Dispatch custom event for components that need to react
    const event = new CustomEvent('themechange', {
      detail: { theme: effectiveTheme, raw: theme }
    });
    document.dispatchEvent(event);

    // Notify listeners
    listeners.forEach(listener => listener(effectiveTheme, theme));
  }

  /**
   * Get stored theme or default to system
   */
  function getStoredTheme() {
    try {
      const stored = localStorage.getItem(THEME_KEY);
      if (stored && Object.values(THEMES).includes(stored)) {
        return stored;
      }
    } catch (e) {
      // localStorage not available
    }
    return THEMES.SYSTEM;
  }

  /**
   * Store theme preference
   */
  function storeTheme(theme) {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch (e) {
      // localStorage not available
    }
  }

  /**
   * Initialize theme engine
   */
  function init() {
    // Check system preference
    systemPrefersDark = checkSystemPreference();

    // Listen for system preference changes
    try {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      mediaQuery.addEventListener('change', (e) => {
        systemPrefersDark = e.matches;
        // If current theme is 'system', re-apply
        if (currentTheme === THEMES.SYSTEM) {
          applyTheme(THEMES.SYSTEM);
        }
      });
    } catch (e) {
      // matchMedia not supported
    }

    // Get and apply stored theme
    currentTheme = getStoredTheme();
    applyTheme(currentTheme);
  }

  /**
   * Public API
   */
  window.WizDeskTheme = {
    /**
     * Get current raw theme (light|dark|system)
     */
    getTheme() {
      return currentTheme;
    },

    /**
     * Get effective theme (light|dark)
     */
    getEffectiveTheme() {
      return getEffectiveTheme(currentTheme);
    },

    /**
     * Set theme
     * @param {string} theme - 'light', 'dark', or 'system'
     */
    setTheme(theme) {
      if (!Object.values(THEMES).includes(theme)) {
        console.warn('[WizDeskTheme] Invalid theme:', theme);
        return false;
      }

      currentTheme = theme;
      storeTheme(theme);
      applyTheme(theme);
      return true;
    },

    /**
     * Toggle between light and dark (skips system)
     */
    toggle() {
      const effective = this.getEffectiveTheme();
      const newTheme = effective === THEMES.DARK ? THEMES.LIGHT : THEMES.DARK;
      return this.setTheme(newTheme);
    },

    /**
     * Check if dark mode is active
     */
    isDark() {
      return this.getEffectiveTheme() === THEMES.DARK;
    },

    /**
     * Subscribe to theme changes
     * @param {Function} listener - callback(theme, rawTheme)
     * @returns {Function} unsubscribe function
     */
    onChange(listener) {
      if (typeof listener !== 'function') {
        throw new Error('Listener must be a function');
      }
      listeners.push(listener);
      return () => {
        const idx = listeners.indexOf(listener);
        if (idx > -1) listeners.splice(idx, 1);
      };
    },

    /**
     * Check if system prefers dark
     */
    prefersDark() {
      return systemPrefersDark;
    },

    // Constants
    THEMES
  };

  // Auto-initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();