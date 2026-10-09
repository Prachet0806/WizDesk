const {defineConfig} = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests/browser',
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:8019',
    timezoneId: 'Asia/Kolkata',
    launchOptions: process.env.BROWSER_EXECUTABLE ? {executablePath: process.env.BROWSER_EXECUTABLE} : {},
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `"${process.env.PYTHON || 'python'}" tests/serve_browser.py`,
    url: 'http://127.0.0.1:8019/health/',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
});
