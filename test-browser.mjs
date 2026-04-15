import { chromium } from 'playwright';

async function test() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log('Opening http://localhost:3001 ...');
  await page.goto('http://localhost:3001', { waitUntil: 'networkidle', timeout: 30000 });
  console.log('Page loaded. Title:', await page.title());

  // Check if logged in via page content
  console.log('\nChecking page content...');
  const pageText = await page.textContent('body');
  const hasLoginBtn = pageText.includes('登录') || pageText.includes('注册');
  const hasUserInfo = pageText.includes('退出') || pageText.includes('个人');
  console.log('Has login button:', hasLoginBtn);
  console.log('Has user info/logout:', hasUserInfo);

  // Try fetching through the page's browser context (this handles HttpOnly cookies)
  console.log('\n--- Testing chat via page fetch ---');
  const chatResult = await page.evaluate(async () => {
    const res = await fetch('http://localhost:8000/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: '请用一句话介绍自己', session_id: 'test-gemma' }),
      credentials: 'include',  // This sends HttpOnly cookies
    });
    const text = await res.text();
    return { status: res.status, body: text };
  });

  console.log('Chat status:', chatResult.status);
  console.log('Response:', chatResult.body.substring(0, 2000));

  await browser.close();
}

test().catch(err => {
  console.error('Test failed:', err.message);
  process.exit(1);
});
