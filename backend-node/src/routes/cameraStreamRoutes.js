const express = require('express');
const http = require('http');
const https = require('https');

const requireAuth = require('../middlewares/autoMiddleware');

const router = express.Router();

const cameraApiBaseUrl = process.env.CAMERA_API_URL || 'http://127.0.0.1:5002';

router.get('/camera-stream/offline', requireAuth, (req, res) => {
  const target = new URL('/video_feed/offline', cameraApiBaseUrl);
  const transport = target.protocol === 'https:' ? https : http;

  const upstream = transport.get(target, { timeout: 15000 }, upstreamResponse => {
    if (upstreamResponse.statusCode !== 200) {
      upstreamResponse.resume();
      return res.status(502).send('Fluxo da câmera indisponível.');
    }

    res.status(200);
    res.set({
      'Content-Type': upstreamResponse.headers['content-type'] ||
        'multipart/x-mixed-replace; boundary=frame',
      'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
      Pragma: 'no-cache',
      Expires: '0'
    });

    upstreamResponse.pipe(res);
  });

  upstream.on('timeout', () => {
    upstream.destroy(new Error('Tempo limite ao conectar à API da câmera.'));
  });

  upstream.on('error', error => {
    console.error(`Falha no proxy da câmera: ${error.message}`);
    if (!res.headersSent) {
      res.status(502).send('Não foi possível conectar à API da câmera.');
    } else {
      res.end();
    }
  });

  res.on('close', () => upstream.destroy());
});

module.exports = router;
