# The Library of Gutenberg

A 3D immersive virtual library containing **70,000 real books** from Project Gutenberg. Walk through hexagonal rooms inspired by Borges's "Library of Babel" and read classic literature in a beautiful, atmospheric setting.

![The Library of Gutenberg](images/hero.png)

## ✨ Features

### 3D Exploration
- **First-person navigation** through hexagonal galleries connected by corridors
- **WASD movement** with smooth collision detection
- **Atmospheric lighting** with flickering lamps and floating dust particles
- **In-world signage**: Room numbers, wall labels, and shelf indicators

### Reading Experience
- **Click any book** to open and read the full text
- **Paginated reader** with page turn animations
- **Two-page spread mode** for wider screens
- **Typography settings**: Choose from 3 fonts and 4 sizes
- **In-book search** (Ctrl+F) with highlighting and navigation
- **Chapter detection** with table of contents sidebar
- **Reading progress** saved automatically

### Search & Navigation
- **Full-text search** of the Gutenberg catalog
- **Filters**: Language (10+ languages) and subject/topic
- **Keyboard navigation** in search results (↑↓ to navigate, Enter to open)
- **Direct coordinates**: Jump to any room/wall/shelf/volume
- **Gutenberg ID lookup**: Enter a book ID to teleport directly to it
- **Random room** button for serendipitous discovery

### Personal Library
- **Bookmarks** saved to localStorage
- **Reading history** with recent books
- **Continue Reading** — resume where you left off
- **Progress tracking** across all books

### Atmosphere
- **Optional ambient audio** with volume control
- **Page turn sounds** (subtle paper rustle)
- **Enhanced dust particles** with gentle floating motion
- **Dynamic lamp flicker** with occasional stronger flickers
- **Warm color temperature shifts** on lamps

## 🎮 Controls

| Key/Action | Function |
|------------|----------|
| **Click** | Enter exploration mode / Select book |
| **WASD** | Walk around |
| **Mouse** | Look around (when locked) |
| **ESC** | Exit reader / Release mouse / Close panels |
| **←/→** | Turn pages in reader |
| **Ctrl+F** | Search within book |
| **B** | Toggle bookmark (in reader) |

## 🏗️ Architecture

```
library-of-babel-gutenberg/
├── index.html          # Main application (self-contained)
├── server.js           # Local development server
├── netlify/
│   └── functions/
│       └── gutenberg.js # Serverless API proxy for Gutenberg
├── images/
│   └── hero.png        # Background image
└── package.json
```

The library contains **110 hexagonal rooms**, each with:
- 4 bookshelf walls
- 5 shelves per wall
- 32 books per shelf
- = **640 books per room**

Books are mapped deterministically: Book #N is always at the same location.

## 🚀 Development

### Local Development (with Netlify Functions)

```bash
# Install dependencies
npm install

# Start Netlify dev server (recommended)
npx netlify dev

# Or use the simple Node.js server (no API proxy)
node server.js
```

Open http://localhost:8888 (Netlify) or http://localhost:8888 (Node).

### Without Netlify

The app will work without the Netlify function, but book searches and text loading will fail due to CORS. For local testing without API:
- Search panel will show errors
- Pre-cached book metadata still works
- You can navigate rooms and see the 3D environment

## 📦 Deployment

### Netlify (Recommended)

1. **Connect your repository** to Netlify
2. **Build settings**:
   - Build command: (leave empty)
   - Publish directory: `.`
3. **Deploy!**

The Netlify function at `/.netlify/functions/gutenberg` proxies:
- `/gutenberg?search=<query>&languages=<lang>&topic=<topic>` — Search books
- `/gutenberg?meta=<id>` — Get book metadata
- `/gutenberg?id=<id>` — Get book text
- `/gutenberg?page=<n>` — List books (paginated)

### Other Platforms

For Vercel, Cloudflare Workers, or similar:
- Adapt the `netlify/functions/gutenberg.js` to the platform's serverless format
- The function is just a CORS proxy for `gutendex.com` and `gutenberg.org`

### Static Hosting (Limited)

Deploy to GitHub Pages, S3, etc.:
- The 3D environment works
- Search/reading requires an external API proxy (set up separately)

## 🔧 Configuration

The app uses localStorage for:
- `gutenberg-library-bookmarks` — Saved bookmarks
- `gutenberg-library-recents` — Reading history
- `gutenberg-library-progress` — Page positions per book
- `gutenberg-library-meta-cache` — Cached book metadata (last 500)
- `gutenberg-library-settings` — User preferences

## 🙏 Credits

- **Book data**: [Project Gutenberg](https://www.gutenberg.org) via [Gutendex API](https://gutendex.com)
- **3D engine**: [Three.js](https://threejs.org)
- **Visual design**: Inspired by Jorge Luis Borges's "The Library of Babel" and [Ethan Mollick's digital recreation](https://twitter.com/emollick)
- **Fonts**: Cormorant Garamond, Libre Baskerville, IBM Plex Mono (Google Fonts)

## 📄 License

MIT

---

*"A library is not a luxury but one of the necessities of life."* — Henry Ward Beecher
