import { chromium } from 'playwright';
import { spawn } from 'child_process';

async function test() {
  // Start monitoring Docker logs in background
  const logProc = spawn('docker', ['logs', '-f', '--tail', '0', 'contract-review-copilot-backend-1'], {
    stdio: ['ignore', 'pipe', 'pipe']
  });

  let devCode = null;
  const logLines = [];

  logProc.stdout.on('data', (data) => {
    const line = data.toString();
    logLines.push(line);
    const match = line.match(/verification code for [^:]+: (\d{6})/);
    if (match) {
      devCode = match[1];
      console.log('Found dev code in logs:', devCode);
    }
  });

  logProc.stderr.on('data', (data) => {
    const line = data.toString();
    logLines.push(line);
  });

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log('=== Step 1: Register ===');
  const email = `test_${Date.now()}@example.com`;
  console.log('Email:', email);

  // Send code
  const sendRes = await page.request.post('http://localhost:8000/api/auth/send-code', {
    headers: { 'Content-Type': 'application/json' },
    data: JSON.stringify({ email }),
    timeout: 10000,
  });
  console.log('Send code status:', sendRes.status());

  // Wait for dev code from logs (max 10s)
  console.log('Waiting for dev code from Docker logs...');
  let waitCount = 0;
  while (!devCode && waitCount < 20) {
    await new Promise(r => setTimeout(r, 500));
    waitCount++;
    if (waitCount % 4 === 0) console.log('Waiting...', waitCount * 500, 'ms');
  }

  if (!devCode) {
    console.log('Could not find dev code in logs. Last log lines:');
    logLines.slice(-10).forEach(l => console.log(' ', l.substring(0, 200)));
    logProc.kill();
    await browser.close();
    return;
  }

  // Register
  const regRes = await page.request.post('http://localhost:8000/api/auth/register', {
    headers: { 'Content-Type': 'application/json' },
    data: JSON.stringify({ email, code: devCode, password: 'test123456' }),
    timeout: 10000,
  });
  console.log('Register status:', regRes.status(), await regRes.text().then(t => t.substring(0, 100)));

  // Login
  const loginRes = await page.request.post('http://localhost:8000/api/auth/login', {
    headers: { 'Content-Type': 'application/json' },
    data: JSON.stringify({ email, password: 'test123456' }),
    timeout: 10000,
  });
  console.log('Login status:', loginRes.status());
  const loginBody = await loginRes.json();
  console.log('Login:', JSON.stringify(loginBody).substring(0, 200));

  // Get cookies
  const cookies = await context.cookies('http://localhost:8000');
  console.log('Cookies:', cookies.map(c => c.name).join(', '));

  // Go to app
  await page.goto('http://localhost:3001', { waitUntil: 'networkidle' });

  console.log('\n=== Step 2: Test Chat ===');
  const chatRes = await page.request.post('http://localhost:8000/api/chat', {
    headers: { 'Content-Type': 'application/json' },
    data: JSON.stringify({ message: '你好', session_id: 'test' }),
    timeout: 120000,
  });
  console.log('Chat status:', chatRes.status());
  console.log('Chat:', (await chatRes.text()).substring(0, 500));

  console.log('\n=== Step 3: Upload Contract ===');
  const contractPath = 'C:\\Users\\吴少然\\Desktop\\sample_contracts\\01_正规长租公寓合同.docx';
  const fileInput = page.locator('input[type="file"]').first();
  if (await fileInput.isVisible({ timeout: 3000 })) {
    console.log('Uploading...');
    await fileInput.setInputFiles(contractPath);
    await page.waitForTimeout(3000);
  }

  const reviewBtn = page.locator('button:has-text("开始审查")').first();
  if (await reviewBtn.isVisible({ timeout: 5000 })) {
    console.log('Clicking review...');
    await reviewBtn.click();
    console.log('Waiting for review (60s)...');
    await page.waitForTimeout(60000);
  }

  console.log('\nPage content:', (await page.textContent('body')).substring(0, 1500));

  logProc.kill();
  await browser.close();
  console.log('\n=== DONE ===');
}

test().catch(err => {
  console.error('Failed:', err.message);
  process.exit(1);
});
