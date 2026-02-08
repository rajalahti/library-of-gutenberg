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

// Very small in-memory cache to avoid hammering Gutendex (prevents 429s)
const GUTENDEX_CACHE_TTL_MS = 5 * 60 * 1000;
const gutendexCache = new Map();

async function fetchCachedJson(url) {
  const now = Date.now();
  const hit = gutendexCache.get(url);
  if (hit && (now - hit.t) < GUTENDEX_CACHE_TTL_MS) return hit;

  const response = await fetch(url);
  const contentType = response.headers.get('content-type') || '';

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    const out = { t: now, ok: false, status: response.status, bodyText: text, contentType };
    // Cache errors briefly too (esp. 429) to reduce repeated hits
    gutendexCache.set(url, out);
    return out;
  }

  const data = await response.json();
  const out = { t: now, ok: true, status: 200, data, contentType };
  gutendexCache.set(url, out);
  return out;
}

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
      const out = await fetchCachedJson(url);
      if (!out.ok) {
        res.writeHead(out.status, { ...headers, 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Gutendex search failed', status: out.status, body: String(out.bodyText || '').slice(0, 500) }));
        return;
      }
      res.writeHead(200, { ...headers, 'Content-Type': 'application/json' });
      res.end(JSON.stringify(out.data));
      return;
    }

    // Book metadata endpoint
    if (params.has('meta')) {
      const url = `https://gutendex.com/books/${params.get('meta')}`;
      const out = await fetchCachedJson(url);
      if (!out.ok) {
        res.writeHead(out.status, { ...headers, 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Gutendex meta failed', status: out.status, body: String(out.bodyText || '').slice(0, 500) }));
        return;
      }
      res.writeHead(200, { ...headers, 'Content-Type': 'application/json' });
      res.end(JSON.stringify(out.data));
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
      const out = await fetchCachedJson(url);
      if (!out.ok) {
        res.writeHead(out.status, { ...headers, 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Gutendex page failed', status: out.status, body: String(out.bodyText || '').slice(0, 500) }));
        return;
      }
      res.writeHead(200, { ...headers, 'Content-Type': 'application/json' });
      res.end(JSON.stringify(out.data));
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

function sendJson(res, status, obj) {
  res.writeHead(status, {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Content-Type': 'application/json; charset=utf-8',
  });
  res.end(JSON.stringify(obj));
}

function tryReadJson(filePath) {
  const data = fs.readFileSync(filePath, 'utf-8');
  return JSON.parse(data);
}

// Layout cache (loaded lazily)
let layoutCache = {
  floors: null,
  primaryLoc: null,
  tagsIndex: new Set(),
};

function loadLayoutIfNeeded() {
  if (!layoutCache.floors) {
    const floorsPath = path.join(__dirname, 'data', 'layout', 'floors7.v1.json');
    layoutCache.floors = tryReadJson(floorsPath);
  }
  if (!layoutCache.primaryLoc) {
    const locPath = path.join(__dirname, 'data', 'layout', 'primaryLocationByBookId.v1.json');
    layoutCache.primaryLoc = tryReadJson(locPath);
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

  // Layout API
  if (pathname === '/api/layout/floors') {
    try {
      loadLayoutIfNeeded();
      sendJson(res, 200, layoutCache.floors);
    } catch (e) {
      console.error('layout floors error:', e);
      sendJson(res, 500, { error: 'layout floors error' });
    }
    return;
  }

  if (pathname.startsWith('/api/layout/tags/room/')) {
    const roomStr = pathname.split('/').pop();
    const room = parseInt(roomStr, 10);
    if (Number.isNaN(room)) {
      sendJson(res, 400, { error: 'invalid room' });
      return;
    }
    try {
      const tagPath = path.join(__dirname, 'data', 'layout', 'tags', `room-${String(room).padStart(3, '0')}.v1.json`);
      const obj = tryReadJson(tagPath);
      sendJson(res, 200, obj);
    } catch (e) {
      if (e && e.code === 'ENOENT') {
        sendJson(res, 404, { error: 'room tags not found' });
      } else {
        console.error('room tags error:', e);
        sendJson(res, 500, { error: 'room tags error' });
      }
    }
    return;
  }

  if (pathname === '/api/layout/loc') {
    const bookId = parseInt(parsedUrl.searchParams.get('bookId') || '', 10);
    if (!bookId) {
      sendJson(res, 400, { error: 'missing bookId' });
      return;
    }
    try {
      loadLayoutIfNeeded();
      const loc = layoutCache.primaryLoc[String(bookId)];
      if (!loc) {
        sendJson(res, 404, { error: 'bookId not found' });
        return;
      }
      sendJson(res, 200, loc);
    } catch (e) {
      console.error('loc error:', e);
      sendJson(res, 500, { error: 'loc error' });
    }
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
