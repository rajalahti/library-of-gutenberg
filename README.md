# The Library of Babel

**[Live Demo](https://library-of-babel-3d.netlify.app)**

A 3D immersive recreation of Jorge Luis Borges's 1941 short story "The Library of Babel" — an infinite library containing every possible book that could ever be written.

![The Library of Babel](images/hero.png)

## The Library

> *"The universe (which others call the Library) is composed of an indefinite, perhaps infinite, number of hexagonal galleries..."*

Walk through infinite hexagonal rooms lined with bookshelves. Each room holds 640 books across 4 walls of 5 shelves. Every book contains 410 pages of 40 lines, each 80 characters long, drawn from 29 symbols.

The total number of distinct pages is 29^3200 — a number with over 4,600 digits. For comparison, the observable universe contains roughly 10^80 atoms.

Somewhere in these hexagons exists every poem, every scientific paper, every novel, every lie, and every truth — buried in an ocean of gibberish.

## Features

- **First-person 3D exploration** — Walk through hexagonal galleries connected by narrow vestibules with spiral staircases, mirrors, and sleeping alcoves, faithful to Borges's descriptions
- **Click any book to read it** — Each book's content is deterministic and permanent. Return to the same shelf and you'll find the same text
- **Search for any text** — Type anything and the algorithm computes the exact room, wall, shelf, volume, page, and line where that text has always existed
- **Navigate between floors** — Use the spiral staircases (Q/E keys) to move between the Library's vertical levels
- **Direct navigation** — Jump to any coordinates by hexagon ID, wall, shelf, volume, and page
- **Atmospheric details** — Flickering amber lamps, floating dust particles, ambient ventilation hum, film grain

## How It Works

The Library uses an 8-round Feistel cipher as a format-preserving permutation over the space of 29^80 possible lines (~390 bits). This creates a bijective mapping: every address produces exactly one line of text, and every possible line of text exists at exactly one address.

- **Forward**: Library coordinates &rarr; Feistel encrypt &rarr; base-29 decode &rarr; text
- **Reverse (search)**: text &rarr; base-29 encode &rarr; Feistel decrypt &rarr; coordinates

See [CIPHER.md](CIPHER.md) for the full technical explanation.

## Controls

| Key | Action |
|-----|--------|
| **Click** | Enter / look around |
| **WASD** | Walk |
| **Click book** | Open and read |
| **Arrow keys** | Turn pages |
| **Escape** | Close book / release mouse |
| **Q / E** | Descend / ascend floors (near staircases) |
| **S** | Open search |
| **N** | Open navigation |
| **R** | Random room |

## Running Locally

The project is a single HTML file with no build step. Serve it over HTTP (required for ES modules):

```
npx serve
```

## Acknowledgments

Inspired by Jonathan Basile's [libraryofbabel.info](https://libraryofbabel.info), the original digital Library of Babel. Basile's implementation uses a Linear Congruential Generator with modular inverses; this one uses a Feistel cipher at line-level granularity. Different math, same beautiful idea.

Based on "La biblioteca de Babel" by Jorge Luis Borges (1941).

Built with [Three.js](https://threejs.org/).

## License

MIT
