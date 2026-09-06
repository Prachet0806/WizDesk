/**
 * WizDesk Lucide Icons Initialization
 * Initializes Lucide icons and provides utilities for dynamic content
 */

(function() {
  'use strict';

  const LUCIDE_VERSION = '0.294.0';
  const CDN_URL = `https://unpkg.com/lucide@${LUCIDE_VERSION}`;

  let lucideLoaded = false;
  let loadPromise = null;

  /**
   * Load Lucide from CDN
   */
  function loadLucide() {
    if (loadPromise) return loadPromise;

    loadPromise = new Promise((resolve, reject) => {
      // Check if already loaded
      if (window.lucide) {
        lucideLoaded = true;
        resolve(window.lucide);
        return;
      }

      const script = document.createElement('script');
      script.src = `${CDN_URL}/dist/umd/lucide.js`;
      script.async = true;
      script.onload = () => {
        lucideLoaded = true;
        resolve(window.lucide);
      };
      script.onerror = () => {
        reject(new Error('Failed to load Lucide from CDN'));
      };
      document.head.appendChild(script);
    });

    return loadPromise;
  }

  /**
   * Initialize Lucide icons in the document
   */
  async function initIcons(options = {}) {
    const {
      attrs = {},
      replace = true
    } = options;

    try {
      const lucide = await loadLucide();

      // Set default attributes
      const defaultAttrs = {
        strokeWidth: 2,
        strokeLinecap: 'round',
        strokeLinejoin: 'round',
        ...attrs
      };

      // Create icons
      lucide.createIcons({
        attrs: defaultAttrs,
        replace
      });

      return lucide;
    } catch (error) {
      console.error('[WizDesk Icons] Failed to initialize Lucide:', error);
      return null;
    }
  }

  /**
   * Create icons for dynamically added content
   */
  async function createIcons(container = document, options = {}) {
    const lucide = await loadLucide();
    if (!lucide) return null;

    return lucide.createIcons({
      ...options,
      nodes: Array.from(container.querySelectorAll('[data-lucide]'))
    });
  }

  /**
   * Replace a single element with its icon
   */
  async function replaceIcon(element, options = {}) {
    const lucide = await loadLucide();
    if (!lucide) return null;

    return lucide.createIcons({
      ...options,
      nodes: [element]
    });
  }

  /**
   * Get icon SVG as string (for programmatic use)
   */
  async function getIcon(name, attrs = {}) {
    const lucide = await loadLucide();
    if (!lucide || !lucide.icons[name]) {
      console.warn(`[WizDesk Icons] Icon "${name}" not found`);
      return null;
    }

    const defaultAttrs = {
      strokeWidth: 2,
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
      ...attrs
    };

    return lucide.icons[name].toSvg(defaultAttrs);
  }

  /**
   * Get all available icon names
   */
  async function getIconNames() {
    const lucide = await loadLucide();
    if (!lucide) return [];
    return Object.keys(lucide.icons);
  }

  // Auto-initialize when DOM is ready
  async function autoInit() {
    await loadLucide();

    // Wait for DOM
    if (document.readyState === 'loading') {
      await new Promise(resolve => document.addEventListener('DOMContentLoaded', resolve));
    }

    // Initialize icons
    await initIcons();
  }

  // Start auto-initialization
  autoInit();

  // Public API
  window.WizDeskIcons = {
    init: initIcons,
    create: createIcons,
    replace: replaceIcon,
    get: getIcon,
    getNames: getIconNames,
    load: loadLucide,
    isLoaded: () => lucideLoaded
  };
})();