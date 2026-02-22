'use client';

import { useMemo, useState, useEffect } from 'react';

/**
 * Encoding Test Component
 * 
 * This component tests and displays WebSocket encoding capabilities,
 * specifically for Chinese characters.
 */
export function EncodingTest() {
  const testResults = useMemo(() => {
    const testData = {
      brand: '特斯拉',
      content: '品牌分析测试',
      phase: '思考',
    };
    const jsonStr = JSON.stringify(testData);
    const parsed = JSON.parse(jsonStr);
    const hasChinese = /[\u4e00-\u9fff]/.test(jsonStr);
    const encoder = new TextEncoder();
    const bytes = encoder.encode(jsonStr);
    const utf8Support = bytes.length > jsonStr.length;

    return {
      jsonStringify: jsonStr,
      jsonParse: JSON.stringify(parsed, null, 2),
      byteCheck: hasChinese,
      utf8Support,
    };
  }, []);

  return (
    <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
      <h3 className="text-lg font-semibold mb-4">编码测试 (Encoding Test)</h3>
      
      <div className="space-y-4">
        <div>
          <h4 className="font-medium text-gray-700">JSON Stringify:</h4>
          <pre className="mt-1 p-2 bg-white rounded border text-sm overflow-x-auto">
            {testResults.jsonStringify}
          </pre>
        </div>

        <div>
          <h4 className="font-medium text-gray-700">JSON Parse Result:</h4>
          <pre className="mt-1 p-2 bg-white rounded border text-sm overflow-x-auto">
            {testResults.jsonParse}
          </pre>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className={`p-3 rounded ${testResults.byteCheck ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
            <span className="font-medium">中文字符检测:</span>
            <span className="ml-2">{testResults.byteCheck ? '✅ 通过' : '❌ 失败'}</span>
          </div>

          <div className={`p-3 rounded ${testResults.utf8Support ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
            <span className="font-medium">UTF-8 支持:</span>
            <span className="ml-2">{testResults.utf8Support ? '✅ 通过' : '❌ 失败'}</span>
          </div>
        </div>

        <div className="text-sm text-gray-600">
          <p>如果以上测试都通过，说明浏览器端编码正常。</p>
          <p>WebSocket 传输应该能够正确处理中文字符。</p>
        </div>
      </div>
    </div>
  );
}

/**
 * WebSocket Message Inspector
 * 
 * Displays raw WebSocket messages for debugging encoding issues.
 */
export function WebSocketMessageInspector() {
  const [messages, setMessages] = useState<Array<{
    id: number;
    timestamp: string;
    event: string;
    rawData: string;
    hasChinese: boolean;
  }>>([]);

  useEffect(() => {
    // Listen for WebSocket messages from useWebSocket hook
    const handleMessage = (event: CustomEvent) => {
      try {
        const { event: eventName, rawData } = event.detail;
        const hasChinese = /[\u4e00-\u9fff]/.test(rawData);

        setMessages(prev => [
          {
            id: Date.now(),
            timestamp: new Date().toLocaleTimeString(),
            event: eventName || 'unknown',
            rawData: rawData.substring(0, 500), // Limit length
            hasChinese,
          },
          ...prev.slice(0, 9), // Keep last 10 messages
        ]);
      } catch {
        // Ignore parse errors
      }
    };

    window.addEventListener('websocket-message', handleMessage as EventListener);

    return () => {
      window.removeEventListener('websocket-message', handleMessage as EventListener);
    };
  }, []);

  return (
    <div className="p-4 bg-[--bg-primary] rounded-lg border border-[--border-default] mt-4">
      <h3 className="text-lg font-semibold mb-4 text-[--text-primary]">WebSocket 消息检查器</h3>

      {messages.length === 0 ? (
        <p className="text-[--text-tertiary]">等待 WebSocket 消息...</p>
      ) : (
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`p-3 rounded border ${
                msg.hasChinese ? 'bg-green-500/10 border-green-500/20' : 'bg-[--bg-secondary] border-[--border-default]'
              }`}
            >
              <div className="flex justify-between text-xs text-[--text-tertiary] mb-1">
                <span>{msg.timestamp}</span>
                <span className="font-medium text-[--text-primary]">{msg.event}</span>
              </div>
              <pre className="text-xs overflow-x-auto whitespace-pre-wrap break-all text-[--text-primary]">
                {msg.rawData}
              </pre>
              {msg.hasChinese && (
                <div className="mt-1 text-xs text-emerald-300">
                  ✅ 包含中文字符
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
