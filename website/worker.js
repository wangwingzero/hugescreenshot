/**
 * Cloudflare Worker - 路由分发
 * 
 * 功能：
 * - Supabase API 路径 (/auth/*, /rest/*, /storage/*, /functions/*) → 转发到 Supabase
 * - 其他路径 (/, /confirm.html, /payment-success.html) → 转发到 Pages 静态站点
 * 
 * 部署步骤：
 * 1. 在 Cloudflare Dashboard 创建 Worker
 * 2. 粘贴此代码
 * 3. 添加环境变量 SUPABASE_HOST (例如: xxxxx.supabase.co)
 * 4. 添加路由: hudawang.cn/* → 此 Worker
 * 5. 确保 Pages 项目绑定到不同的域名或使用 Service Binding
 */

// Supabase API 路径前缀
const SUPABASE_PATHS = [
  '/auth/',
  '/rest/',
  '/storage/',
  '/functions/',
  '/realtime/',
  '/graphql/',
];

// 静态文件扩展名
const STATIC_EXTENSIONS = [
  '.html',
  '.css',
  '.js',
  '.png',
  '.jpg',
  '.jpeg',
  '.gif',
  '.svg',
  '.ico',
  '.woff',
  '.woff2',
  '.ttf',
];

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const pathname = url.pathname;
    
    // 检查是否是 Supabase API 请求
    const isSupabaseRequest = SUPABASE_PATHS.some(prefix => pathname.startsWith(prefix));
    
    if (isSupabaseRequest) {
      // 转发到 Supabase
      return forwardToSupabase(request, env, url);
    } else {
      // 转发到 Pages 静态站点
      return forwardToPages(request, env, url);
    }
  },
};

/**
 * 转发请求到 Supabase
 */
async function forwardToSupabase(request, env, url) {
  // 从环境变量获取 Supabase 主机名
  const supabaseHost = env.SUPABASE_HOST;
  
  if (!supabaseHost) {
    return new Response('SUPABASE_HOST environment variable not set', { status: 500 });
  }
  
  // 构建新的 URL
  const newUrl = new URL(url.pathname + url.search, `https://${supabaseHost}`);
  
  // 创建新请求，保留原始请求的方法、头部和 body
  const newRequest = new Request(newUrl.toString(), {
    method: request.method,
    headers: request.headers,
    body: request.body,
    redirect: 'follow',
  });
  
  // 转发请求
  const response = await fetch(newRequest);
  
  // 返回响应，添加 CORS 头部
  const newResponse = new Response(response.body, response);
  
  // 允许跨域（如果需要）
  newResponse.headers.set('Access-Control-Allow-Origin', '*');
  
  return newResponse;
}

/**
 * 转发请求到 Cloudflare Pages
 */
async function forwardToPages(request, env, url) {
  // 方式 1: 使用 Service Binding（推荐，需要在 Worker 设置中绑定 Pages 项目）
  if (env.PAGES) {
    return env.PAGES.fetch(request);
  }
  
  // 方式 2: 直接请求 Pages 域名
  const pagesHost = env.PAGES_HOST || 'hugescreenshot.pages.dev';
  const newUrl = new URL(url.pathname + url.search, `https://${pagesHost}`);
  
  const newRequest = new Request(newUrl.toString(), {
    method: request.method,
    headers: request.headers,
    body: request.body,
  });
  
  return fetch(newRequest);
}
