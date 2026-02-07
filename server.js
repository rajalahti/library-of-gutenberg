// Simple development server with Gutenberg proxy
import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = 8888;

const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

// Proxy handler for Gutenberg API
async function handleGutenbergProxy(query, res) {
  const params = new URLSearchParams(query);
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
  };

  try {
    // Search endpoint
    if (params.has('search')) {
      const url = `https://gutendex.com/books/?search=${encodeURIComponent(params.get('search'))}`;
      const response = await fetch(url);
      const data = await response.json();
      res.writeHead(200, { ...headers, 'Content-Type': 'application/json' });
      res.end(JSON.stringify(data));
      return;
    }

    // Book metadata endpoint
    if (params.has('meta')) {
      const url = `https://gutendex.com/books/${params.get('meta')}`;
      const response = await fetch(url);
      const data = await response.json();
      res.writeHead(200, { ...headers, 'Content-Type': 'application/json' });
      res.end(JSON.stringify(data));
      return;
    }

    // Book text endpoint
    if (params.has('id')) {
      const bookId = params.get('id');
      const textUrls = [
        `https://www.gutenberg.org/cache/epub/${bookId}/pg${bookId}.txt`,
        `https://www.gutenberg.org/files/${bookId}/${bookId}-0.txt`,
        `https://www.gutenberg.org/files/${bookId}/${bookId}.txt`,
      ];

      for (const url of textUrls) {
        try {
          const response = await fetch(url, {
            headers: { 'User-Agent': 'LibraryOfGutenberg/1.0' }
          });
          if (response.ok) {
            const text = await response.text();
            res.writeHead(200, { ...headers, 'Content-Type': 'text/plain; charset=utf-8' });
            res.end(text);
            return;
          }
        } catch (e) {
          // Try next URL
        }
      }

      res.writeHead(404, headers);
      res.end('Book text not found');
      return;
    }

    // List books endpoint
    if (params.has('page')) {
      const page = parseInt(params.get('page')) || 1;
      const url = `https://gutendex.com/books/?page=${page}`;
      const response = await fetch(url);
      const data = await response.json();
      res.writeHead(200, { ...headers, 'Content-Type': 'application/json' });
      res.end(JSON.stringify(data));
      return;
    }

    res.writeHead(400, headers);
    res.end(JSON.stringify({ error: 'Missing required parameter' }));

  } catch (error) {
    console.error('Proxy error:', error);
    res.writeHead(500, headers);
    res.end(JSON.stringify({ error: 'Proxy error' }));
  }
}

const server = http.createServer(async (req, res) => {
  const parsedUrl = new URL(req.url, `http://localhost:${PORT}`);
  let pathname = parsedUrl.pathname;

  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(200, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
    });
    res.end();
    return;
  }

  // Proxy API requests
  if (pathname === '/.netlify/functions/gutenberg' || pathname === '/api/gutenberg') {
    await handleGutenbergProxy(parsedUrl.search.slice(1), res);
    return;
  }

  // Serve static files
  if (pathname === '/') {
    pathname = '/index.html';
  }

  const filePath = path.join(__dirname, pathname);
  const ext = path.extname(filePath);
  const contentType = MIME_TYPES[ext] || 'application/octet-stream';

  try {
    const data = fs.readFileSync(filePath);
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(data);
  } catch (err) {
    if (err.code === 'ENOENT') {
      res.writeHead(404);
      res.end('Not Found');
    } else {
      res.writeHead(500);
      res.end('Server Error');
    }
  }
});

server.listen(PORT, () => {
  console.log(`\n🏛️  Library of Gutenberg running at http://localhost:${PORT}\n`);
  console.log('Press Ctrl+C to stop.\n');
});
