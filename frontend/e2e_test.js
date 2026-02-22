const main = async () => {
  const { chromium } = await import('playwright-core');
  console.log('启动端到端测试...');
  
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 }
  });
  const page = await context.newPage();

  try {
    // 1. 访问首页
    console.log('1. 访问首页 http://localhost:3000');
    await page.goto('http://localhost:3000', { timeout: 30000 });
    await page.waitForTimeout(2000);
    
    // 截图首页
    await page.screenshot({ path: 'd:\\AGEO\\test_results\\01_homepage.png', fullPage: true });
    console.log('   ✓ 首页截图已保存');

    // 2. 进入聊天页面
    console.log('2. 进入聊天页面');
    await page.goto('http://localhost:3000/chat/test-yazi-e2e-001', { timeout: 30000 });
    await page.waitForTimeout(3000);
    
    // 截图聊天页面初始状态
    await page.screenshot({ path: 'd:\\AGEO\\test_results\\02_chat_initial.png', fullPage: true });
    console.log('   ✓ 聊天页面初始状态截图已保存');

    // 3. 等待输入框并输入"雅姿"
    console.log('3. 输入品牌名称"雅姿"');
    await page.waitForSelector('textarea', { timeout: 10000 });
    await page.fill('textarea', '雅姿');
    await page.waitForTimeout(500);
    
    // 截图输入状态
    await page.screenshot({ path: 'd:\\AGEO\\test_results\\03_input_filled.png', fullPage: true });
    console.log('   ✓ 输入完成截图已保存');

    // 4. 点击发送按钮
    console.log('4. 发送消息');
    const sendButton = await page.$('button[type="submit"]');
    if (sendButton) {
      await sendButton.click();
    } else {
      // 尝试通过键盘发送
      await page.press('textarea', 'Enter');
    }
    
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'd:\\AGEO\\test_results\\04_message_sent.png', fullPage: true });
    console.log('   ✓ 消息发送截图已保存');

    // 5. 等待 WebSocket 连接和响应
    console.log('5. 等待 WebSocket 响应 (最多30秒)...');
    
    // 监听 WebSocket 消息
    let wsMessages = [];
    page.on('websocket', ws => {
      console.log(`   WebSocket 连接: ${ws.url()}`);
      ws.on('framereceived', data => {
        console.log(`   WS 收到: ${data.payload.substring(0, 200)}...`);
        wsMessages.push(data.payload);
      });
    });

    // 等待一段时间观察响应
    await page.waitForTimeout(15000);
    
    // 截图响应状态
    await page.screenshot({ path: 'd:\\AGEO\\test_results\\05_response_received.png', fullPage: true });
    console.log('   ✓ 响应截图已保存');

    // 6. 检查页面内容
    console.log('6. 检查页面内容');
    const pageContent = await page.content();
    const hasUserMessage = pageContent.includes('雅姿');
    const hasAgentResponse = pageContent.includes('Agent') || pageContent.includes('分析') || pageContent.includes('品牌');
    
    console.log(`   - 用户消息显示: ${hasUserMessage ? '✓' : '✗'}`);
    console.log(`   - Agent响应显示: ${hasAgentResponse ? '✓' : '✗'}`);
    console.log(`   - WebSocket消息数: ${wsMessages.length}`);

    // 7. 最终截图
    await page.waitForTimeout(5000);
    await page.screenshot({ path: 'd:\\AGEO\\test_results\\06_final.png', fullPage: true });
    console.log('   ✓ 最终截图已保存');

    console.log('\n=== 测试完成 ===');
    console.log('所有截图已保存到 d:\\AGEO\\test_results\\ 目录');
    
  } catch (error) {
    console.error('测试出错:', error);
    await page.screenshot({ path: 'd:\\AGEO\\test_results\\error.png', fullPage: true });
  } finally {
    await browser.close();
  }
};

main();
