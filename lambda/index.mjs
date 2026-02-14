import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
};

const JSON_HEADERS = {
  ...CORS_HEADERS,
  'Content-Type': 'application/json; charset=utf-8',
};

// Small in-memory cache to reduce repeat traffic to Gutendex.
const GUTENDEX_CACHE_TTL_MS = 5 * 60 * 1000;
const gutendexCache = new Map();

let floorsCache = null;
let primaryLocationCache = null;
const tagsCache = new Map();
let localMetaById = null;

function response(statusCode, body, headers = JSON_HEADERS) {
  return {
    statusCode,
    headers,
    body,
  };
}

function json(statusCode, obj) {
  return response(statusCode, JSON.stringify(obj), JSON_HEADERS);
}

function text(statusCode, bodyText) {
  return response(statusCode, bodyText, {
    ...CORS_HEADERS,
    'Content-Type': 'text/plain; charset=utf-8',
  });
}

function parseEvent(event) {
  const method = event?.requestContext?.http?.method || event?.httpMethod || 'GET';
  const pathname = event?.rawPath || event?.path || '/';
  const query = event?.queryStringParameters || {};
  return { method, pathname, query };
}

function getQueryParam(query, key) {
  const value = query?.[key];
  if (Array.isArray(value)) return value[0];
  return value;
}

function readJson(filePath) {
  const data = fs.readFileSync(filePath, 'utf-8');
  return JSON.parse(data);
}

function loadLayoutIfNeeded() {
  if (!floorsCache) {
    floorsCache = readJson(path.join(__dirname, 'data', 'layout', 'floors7.v1.json'));
  }
  if (!primaryLocationCache) {
    primaryLocationCache = readJson(path.join(__dirname, 'data', 'layout', 'primaryLocationByBookId.v1.json'));
  }
}

function loadLocalMetaIndexIfNeeded() {
  if (localMetaById) return;

  const jsonlPath = path.join(__dirname, 'data', 'book-meta', 'bookMetaById.v1.jsonl');
  const lines = fs.readFileSync(jsonlPath, 'utf-8').split('\n');
  const index = new Map();

  for (const line of lines) {
    if (!line) continue;
    try {
      const row = JSON.parse(line);
      if (row && Number.isInteger(row.id)) {
        index.set(row.id, row);
      }
    } catch {
      // Ignore malformed lines.
    }
  }

  localMetaById = index;
}

async function fetchCachedJson(url) {
  const now = Date.now();
  const cached = gutendexCache.get(url);
  if (cached && now - cached.t < GUTENDEX_CACHE_TTL_MS) {
    return cached;
  }

  const res = await fetch(url);
  const contentType = res.headers.get('content-type') || '';

  if (!res.ok) {
    const bodyText = await res.text().catch(() => '');
    const out = { t: now, ok: false, status: res.status, bodyText, contentType };
    gutendexCache.set(url, out);
    return out;
  }

  const data = await res.json();
  const out = { t: now, ok: true, status: 200, data, contentType };
  gutendexCache.set(url, out);
  return out;
}

async function handleGutenbergProxy(query) {
  const search = getQueryParam(query, 'search');
  const meta = getQueryParam(query, 'meta');
  const id = getQueryParam(query, 'id');
  const page = getQueryParam(query, 'page');

  if (search) {
    const url = `https://gutendex.com/books/?search=${encodeURIComponent(search)}`;
    const out = await fetchCachedJson(url);
    if (!out.ok) {
      return json(out.status, {
        error: 'Gutendex search failed',
        status: out.status,
        body: String(out.bodyText || '').slice(0, 500),
      });
    }
    return json(200, out.data);
  }

  if (meta) {
    const url = `https://gutendex.com/books/${meta}`;
    const out = await fetchCachedJson(url);
    if (!out.ok) {
      return json(out.status, {
        error: 'Gutendex meta failed',
        status: out.status,
        body: String(out.bodyText || '').slice(0, 500),
      });
    }
    return json(200, out.data);
  }

  if (id) {
    const textUrls = [
      `https://www.gutenberg.org/cache/epub/${id}/pg${id}.txt`,
      `https://www.gutenberg.org/files/${id}/${id}-0.txt`,
      `https://www.gutenberg.org/files/${id}/${id}.txt`,
    ];

    for (const url of textUrls) {
      try {
        const res = await fetch(url, {
          headers: { 'User-Agent': 'LibraryOfGutenberg/1.0' },
        });
        if (res.ok) {
          const bodyText = await res.text();
          return text(200, bodyText);
        }
      } catch {
        // Try next mirror.
      }
    }

    return text(404, 'Book text not found');
  }

  if (page !== undefined) {
    const pageNum = Number.parseInt(page, 10) || 1;
    const url = `https://gutendex.com/books/?page=${pageNum}`;
    const out = await fetchCachedJson(url);
    if (!out.ok) {
      return json(out.status, {
        error: 'Gutendex page failed',
        status: out.status,
        body: String(out.bodyText || '').slice(0, 500),
      });
    }
    return json(200, out.data);
  }

  return json(400, { error: 'Missing required parameter' });
}

function handleLayoutTags(pathname) {
  const roomStr = pathname.split('/').pop();
  const room = Number.parseInt(roomStr, 10);
  if (Number.isNaN(room)) {
    return json(400, { error: 'invalid room' });
  }

  const key = String(room).padStart(3, '0');
  const cached = tagsCache.get(key);
  if (cached) {
    return json(200, cached);
  }

  try {
    const tagPath = path.join(__dirname, 'data', 'layout', 'tags', `room-${key}.v1.json`);
    const doc = readJson(tagPath);
    tagsCache.set(key, doc);
    return json(200, doc);
  } catch (err) {
    if (err && err.code === 'ENOENT') {
      return json(404, { error: 'room tags not found' });
    }
    console.error('room tags error:', err);
    return json(500, { error: 'room tags error' });
  }
}

export async function handler(event) {
  const { method, pathname, query } = parseEvent(event);

  if (method === 'OPTIONS') {
    return response(200, '', CORS_HEADERS);
  }

  try {
    if (pathname === '/api/local/meta') {
      const bookId = Number.parseInt(getQueryParam(query, 'bookId') || '', 10);
      if (!bookId) {
        return json(400, { error: 'missing bookId' });
      }

      loadLocalMetaIndexIfNeeded();
      const row = localMetaById.get(bookId);
      if (!row) {
        return json(404, { error: 'bookId not found in local snapshot' });
      }

      return json(200, row);
    }

    if (pathname === '/api/layout/floors') {
      loadLayoutIfNeeded();
      return json(200, floorsCache);
    }

    if (pathname.startsWith('/api/layout/tags/room/')) {
      return handleLayoutTags(pathname);
    }

    if (pathname === '/api/layout/loc') {
      const bookId = Number.parseInt(getQueryParam(query, 'bookId') || '', 10);
      if (!bookId) {
        return json(400, { error: 'missing bookId' });
      }

      loadLayoutIfNeeded();
      const loc = primaryLocationCache[String(bookId)];
      if (!loc) {
        return json(404, { error: 'bookId not found' });
      }

      return json(200, loc);
    }

    if (pathname === '/api/gutenberg' || pathname === '/.netlify/functions/gutenberg') {
      return await handleGutenbergProxy(query);
    }

    return json(404, { error: 'Not found' });
  } catch (err) {
    console.error('unhandled api error:', err);
    return json(500, { error: 'Internal server error' });
  }
}
