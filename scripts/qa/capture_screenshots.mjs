import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';

const SCREENSHOT_DIR = path.resolve('docs/audit/screenshots');
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

const SCREENS = [
  { route: '/dashboard', name: '01_dashboard' },
  { route: '/assets', name: '02_assets' },
  { route: '/scans', name: '03_scans' },
  { route: '/active-assessments', name: '04_active_assessments' },
  { route: '/findings', name: '05_findings' },
  { route: '/remediation', name: '06_remediation' },
  { route: '/checklist', name: '07_checklist' },
  { route: '/empire-modules', name: '08_empire_modules' },
  { route: '/engine-runs', name: '09_engine_runs' },
  { route: '/detection-rules', name: '10_detection_rules' },
  { route: '/threat-intel', name: '11_threat_intel' },
  { route: '/reports', name: '12_reports' },
  { route: '/schedules', name: '13_schedules' },
  { route: '/settings', name: '14_settings' },
];

class CDP {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 1;
    this.callbacks = new Map();
  }
  async connect() {
    return new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
      this.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.id && this.callbacks.has(msg.id)) {
          const { resolve, reject } = this.callbacks.get(msg.id);
          this.callbacks.delete(msg.id);
          if (msg.error) reject(msg.error);
          else resolve(msg.result);
        }
      };
    });
  }
  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = this.id++;
      this.callbacks.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  close() {
    this.ws.close();
  }
}

async function main() {
  console.log('[*] Step 1: Logging in to get owner session token...');
  const loginRes = await fetch('http://localhost:8080/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: 'dangnhutnguyen0910@gmail.com',
      password: 'ValidOwnerPassword123!',
    }),
  });
  if (!loginRes.ok) {
    throw new Error(`Login failed: ${loginRes.status} ${await loginRes.text()}`);
  }
  const loginData = await loginRes.json();
  const accessToken = loginData.access_token;
  console.log(`[+] Logged in as: ${loginData.user.email} (${loginData.user.role})`);

  console.log('[*] Step 2: Spawning headless Google Chrome on port 9222...');
  const chrome = spawn('google-chrome', [
    '--headless=new',
    '--no-sandbox',
    '--disable-gpu',
    '--remote-debugging-port=9222',
    '--window-size=1920,1080',
    'about:blank',
  ]);

  // Wait for Chrome to bind port
  let wsUrl = null;
  for (let i = 0; i < 20; i++) {
    await new Promise((r) => setTimeout(r, 500));
    try {
      const res = await fetch('http://127.0.0.1:9222/json/new', { method: 'PUT' });
      if (res.ok) {
        const tab = await res.json();
        wsUrl = tab.webSocketDebuggerUrl;
        break;
      }
    } catch (_) {}
  }

  if (!wsUrl) {
    chrome.kill();
    throw new Error('Failed to connect to headless Chrome debugging port.');
  }
  console.log(`[+] Connected to Chrome tab: ${wsUrl}`);

  const cdp = new CDP(wsUrl);
  await cdp.connect();

  await cdp.send('Page.enable');
  await cdp.send('Network.enable');
  await cdp.send('DOM.enable');

  // Inject session cookies
  await cdp.send('Network.setCookie', {
    name: 'noospire_session',
    value: accessToken,
    domain: 'localhost',
    path: '/',
    httpOnly: true,
    sameSite: 'Strict',
  });
  await cdp.send('Network.setCookie', {
    name: 'sentinel_access_token',
    value: accessToken,
    domain: 'localhost',
    path: '/',
    sameSite: 'Strict',
  });

  // Helper to capture a screenshot
  const capture = async (route, name, themeMode) => {
    const url = `http://localhost:8080${route}`;
    await cdp.send('Page.navigate', { url });
    // Wait for network idle / render
    await new Promise((r) => setTimeout(r, 1200));

    // Apply theme
    if (themeMode === 'warm-light') {
      await cdp.send('Runtime.evaluate', {
        expression: `
          try {
            localStorage.setItem('sentinel_theme', 'warm-light');
            document.documentElement.classList.remove('dark');
            document.documentElement.classList.add('light', 'theme-warm');
            document.documentElement.setAttribute('data-theme', 'warm');
          } catch(e) {}
        `,
      });
    } else {
      await cdp.send('Runtime.evaluate', {
        expression: `
          try {
            localStorage.setItem('sentinel_theme', 'obsidian-dark');
            document.documentElement.classList.remove('light', 'theme-warm');
            document.documentElement.classList.add('dark');
            document.documentElement.setAttribute('data-theme', 'obsidian-dark');
          } catch(e) {}
        `,
      });
    }

    await new Promise((r) => setTimeout(r, 400));

    const shot = await cdp.send('Page.captureScreenshot', {
      format: 'png',
      quality: 90,
      fromSurface: true,
    });

    const filename = `${name}_${themeMode === 'warm-light' ? 'warm_light' : 'obsidian_dark'}.png`;
    const filepath = path.join(SCREENSHOT_DIR, filename);
    fs.writeFileSync(filepath, Buffer.from(shot.data, 'base64'));
    const sizeKb = (fs.statSync(filepath).size / 1024).toFixed(1);
    console.log(`    [+] Captured: ${filename} (${sizeKb} KB)`);
  };

  console.log('[*] Step 3: Capturing all 14 Operator Screens in Obsidian Dark Mode...');
  for (const screen of SCREENS) {
    await capture(screen.route, screen.name, 'obsidian-dark');
  }

  console.log('[*] Step 4: Capturing all 14 Operator Screens in Warm Light Mode (Invert)...');
  for (const screen of SCREENS) {
    await capture(screen.route, screen.name, 'warm-light');
  }

  cdp.close();
  chrome.kill();
  console.log('[+] Screenshot capture mission completed successfully!');
}

main().catch((err) => {
  console.error('[-] Error in screenshot capture:', err);
  process.exit(1);
});
