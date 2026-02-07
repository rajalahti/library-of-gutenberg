// Netlify function to proxy Gutenberg book text requests (bypasses CORS)
export async function handler(event) {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
  };

  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  const params = event.queryStringParameters || {};

  // Search endpoint: proxy to Gutendex with optional filters
  if (params.search) {
    try {
      let url = `https://gutendex.com/books/?search=${encodeURIComponent(params.search)}`;
      
      // Add language filter if provided
      if (params.languages) {
        url += `&languages=${encodeURIComponent(params.languages)}`;
      }
      
      // Add topic/subject filter if provided
      if (params.topic) {
        url += `&topic=${encodeURIComponent(params.topic)}`;
      }
      
      const response = await fetch(url);
      const data = await response.json();
      return {
        statusCode: 200,
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      };
    } catch (error) {
      return {
        statusCode: 500,
        headers,
        body: JSON.stringify({ error: 'Failed to search Gutendex' }),
      };
    }
  }

  // Book metadata endpoint
  if (params.meta) {
    try {
      const url = `https://gutendex.com/books/${params.meta}`;
      const response = await fetch(url);
      const data = await response.json();
      return {
        statusCode: 200,
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      };
    } catch (error) {
      return {
        statusCode: 500,
        headers,
        body: JSON.stringify({ error: 'Failed to fetch book metadata' }),
      };
    }
  }

  // Book text endpoint
  if (params.id) {
    const bookId = params.id;
    
    // Try multiple Gutenberg mirror URLs for plain text
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
          return {
            statusCode: 200,
            headers: { ...headers, 'Content-Type': 'text/plain; charset=utf-8' },
            body: text,
          };
        }
      } catch (e) {
        // Try next URL
      }
    }

    return {
      statusCode: 404,
      headers,
      body: 'Book text not found',
    };
  }

  // List books endpoint (paginated)
  if (params.page !== undefined) {
    try {
      const page = parseInt(params.page) || 1;
      let url = `https://gutendex.com/books/?page=${page}`;
      
      // Support language filter for browsing
      if (params.languages) {
        url += `&languages=${encodeURIComponent(params.languages)}`;
      }
      
      const response = await fetch(url);
      const data = await response.json();
      return {
        statusCode: 200,
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      };
    } catch (error) {
      return {
        statusCode: 500,
        headers,
        body: JSON.stringify({ error: 'Failed to fetch book list' }),
      };
    }
  }

  return {
    statusCode: 400,
    headers,
    body: JSON.stringify({ error: 'Missing required parameter: id, search, meta, or page' }),
  };
}
