# Library of Gutenberg (Library of Babel + Gutendex)

A local Three.js “infinite-library” style experience filled with real Project Gutenberg books.

This repo is being migrated from a legacy deterministic layout to a **server-driven, data-generated layout** based on Gutendex metadata.

## Run (local)

```bash
npm install
npm run dev
# open http://localhost:8888
```

If port `8888` is busy:

```bash
lsof -nP -iTCP:8888 -sTCP:LISTEN
kill <PID>
```

### Dev server survival

When started via OpenClaw exec sessions, the dev server may get SIGKILL’d. Recommended:

```bash
nohup npm run dev --silent > .devserver.log 2>&1 &
echo $! > .devserver.pid
```

Stop:

```bash
kill $(cat .devserver.pid)
```

## Deploy to AWS (Lambda + S3 + CloudFront + Route53)

This repo includes serverless AWS infrastructure for low cost:

- Static files (`index.html`, `images/`, `data/`) are served from private S3 through CloudFront.
- API routes (`/api/*` and `/.netlify/functions/*`) run on Lambda via Function URL.
- Route53 alias points `library.rajalahti.me` to CloudFront.
- Existing ACM cert in `us-east-1` is used for TLS.

### One-time prerequisites

- AWS CLI configured and authenticated.
- Certificate exists in ACM `us-east-1` and covers `library.rajalahti.me` (or `*.rajalahti.me`).
- Route53 hosted zone exists for `rajalahti.me`.
- `zip` installed locally.

### First deployment

```bash
npm install
npm run aws:deploy
```

Defaults used by the deploy script:

- `STACK_NAME=library-of-gutenberg`
- `AWS_REGION` from your AWS CLI config (fallback `eu-north-1`)
- `DOMAIN_NAME=library.rajalahti.me`
- `ROOT_DOMAIN=rajalahti.me`
- `CERT_MATCH_DOMAIN=*.rajalahti.me` (searched from ACM in `us-east-1`)

### Deploy a new version

After making code/data changes, run:

```bash
npm run aws:deploy
```

The script will:

1. Build `.dist/lambda.zip` and static site artifacts.
2. Upload Lambda artifact to the deployment artifacts bucket.
3. Update the CloudFormation stack.
4. Sync static files to the site S3 bucket.
5. Keep CloudFront cache cost low via short `index.html` TTL and longer asset TTL.

If you need the HTML change immediately instead of waiting for cache TTL:

```bash
INVALIDATE_CF=true npm run aws:deploy
```

### Useful overrides

```bash
STACK_NAME=library-of-gutenberg-prod \
AWS_REGION=eu-north-1 \
DOMAIN_NAME=library.rajalahti.me \
ROOT_DOMAIN=rajalahti.me \
CERT_ARN=arn:aws:acm:us-east-1:123456789012:certificate/abc... \
npm run aws:deploy
```

### Destroy stack

```bash
npm run aws:destroy
```

Files added for AWS deployment:

- `infra/aws/cloudformation.yml`
- `lambda/index.mjs`
- `scripts/aws/build_artifacts.sh`
- `scripts/aws/deploy.sh`
- `scripts/aws/destroy.sh`

## Layout (server-driven)

The canonical layout is generated offline and served via API endpoints.

### Generated assets

- `data/layout/floors7.v1.json`
  - 7 “floors” (theme sections)
  - contains `roomsTotal` and per-floor `roomStart` / `roomCount`
- `data/layout/tags/room-XYZ.v1.json`
  - shelf tags for each room (only at real section boundaries)
- `data/layout/primaryLocationByBookId.v1.json`
  - bookId → primary location (`room/wall/shelf/volume/floorId/subId`)
- `data/layout/slots7.v1.json`
  - (next step) the physical slot assignment for instanced book meshes

Generator:

```bash
python3 scripts/generate_layout_floors7.py
```

### Server endpoints

- `GET /api/layout/floors`
- `GET /api/layout/tags/room/:room` (room is 0-indexed, padded to 3 digits)
- `GET /api/layout/loc?bookId=<id>`
- `GET /api/gutenberg?id=<id>|meta=<id>|search=<query>|page=<n>`

Local metadata snapshot endpoint (avoids Gutendex 429s):

- `GET /api/local/meta?bookId=<id>`

## Navigation concepts

- **Room index** in code is **0-indexed**.
- UI generally displays rooms as **1-indexed** (“Room 1 of 128”).
- Location fields:
  - `wall` 0..3 (UI shows 1..4)
  - `shelf` 0..4 (UI shows 1..5)
  - `volume` 0..31 (UI shows 1..32)

## Debugging: verify book locations

### Why this exists

We are currently in a transition period:
- Teleport/navigation uses **API layout** (`/api/layout/loc`).
- Some UI text and/or instanced placement may still use legacy deterministic mapping.

Goal:
> The **only source of truth** for book locations should be the generated layout (loc + slots).

### Debug overlay (in-app)

A debug overlay is available to compare **apiLoc vs legacyLoc**.

- Toggle: press **`P`**
- When opening a book, it shows:
  - `bookId`
  - `apiLoc` (from `/api/layout/loc`)
  - `legacyLoc` (from old deterministic mapper)
  - `currentRoomIndex`

If `apiLoc` and `legacyLoc` differ, the legacy path is still affecting something.

### Example 1: check a bookId against the API

Pick a Gutenberg ID, e.g. `32082`.

```bash
curl -sS "http://localhost:8888/api/layout/loc?bookId=32082"
```
Expected fields:

```json
{"room":31,"wall":2,"shelf":3,"volume":30,"floorId":"literature_fiction","subId":"British Literature"}
```

Interpretation (UI 1-indexed):
- Room **32**
- Wall **3**
- Shelf **4**
- Volume **31**

Now in-app:
1) Search → “Jump by Gutenberg ID” → 32082 → “Go to Book”
2) Open the book
3) Debug overlay should show `apiLoc` matching the API response.

If reader header shows a different room/wall/shelf/volume than `apiLoc`, that is a bug (legacy mapping still used somewhere).

### Example 2: elevator floor sanity checks

Floor ranges (from `data/layout/floors7.v1.json`) are:

- History & War: Rooms 1–30
- Literature & Fiction: Rooms 31–58
- Crime, Mystery & Gothic: Rooms 59–62
- Sci‑Fi & Fantasy: Rooms 63–71
- Children & YA: Rooms 72–86
- Poetry & Drama: Rooms 87–97
- Non‑fiction & Thought: Rooms 98–128

So if you teleport to **History & War**, the HUD should land in **Room 1–30**.
If it lands in **Room 31**, you actually landed in **Literature & Fiction** → elevator mapping bug.

## Known issues / next steps

- **Slots integration**: books are not yet physically placed using `slots7.v1.json`.
  - Risk: API location resolves, but the book meshes are still laid out using legacy deterministic placement.
- After slots integration, the 3D placement, UI coords, and API loc must all match.

## Notes

- Work stays local; do not push to origin.
