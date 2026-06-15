import { Router } from 'express';
import http from 'http';

const router = Router();

// 代理 API 请求到 FastAPI 后端
const backendHost = 'localhost';
const backendPort = 8000;

router.use('/api', (req, res) => {
  const body = JSON.stringify(req.body);
  
  const options: http.RequestOptions = {
    hostname: backendHost,
    port: backendPort,
    path: req.originalUrl,
    method: req.method,
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(body),
    },
  };

  const proxyReq = http.request(options, (proxyRes) => {
    let data = '';
    proxyRes.on('data', (chunk) => {
      data += chunk;
    });
    proxyRes.on('end', () => {
      res.status(proxyRes.statusCode || 500);
      if (proxyRes.headers['content-type']) {
        res.set('Content-Type', proxyRes.headers['content-type']);
      }
      res.send(data);
    });
  });

  proxyReq.on('error', (err) => {
    console.error('Proxy error:', err.message);
    if (!res.headersSent) {
      res.status(502).json({ error: 'Backend service unavailable' });
    }
  });

  proxyReq.write(body);
  proxyReq.end();
});

export default router;
