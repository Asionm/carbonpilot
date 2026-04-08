// proxy.js - API代理配置文件
const { createProxyMiddleware } = require('http-proxy-middleware');

const proxyMiddleware = (req, res, next) => {
  // 如果请求路径以/api开头，则代理到后端服务器
  if (req.url.startsWith('/api')) {
    const proxy = createProxyMiddleware({
      target: 'http://localhost:8000',
      changeOrigin: true,
      pathRewrite: {
        '^/api': '/api', // 重写路径，保持/api前缀
      },
    });
    
    return proxy(req, res, next);
  }
  
  // 如果不是API请求，则继续处理
  next();
};

module.exports = proxyMiddleware;