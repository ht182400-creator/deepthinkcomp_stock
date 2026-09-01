// 测试替身：jsdom 环境的 app.js 动态 import('./modules/stock.js') 以测试文件为基址解析，
// 用本 stub 让 import 成功（真 stock.js 由 stock.test.js 直接加载测试）。
export function render() {}
export function loadAll() {}
export function cleanTimers() {}
