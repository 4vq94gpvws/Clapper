# Third-party software

This repository contains no third-party source code. The Docker image installs:

| Component | Where it comes from | License |
|---|---|---|
| Remotion 4.0.547 (`remotion`, `@remotion/*`) | npm, from `render/package-lock.json` | [Remotion License](https://www.remotion.dev/docs/license): free for individuals, for-profit organizations of up to 3 employees and non-profits; a company license is required for larger for-profit organizations. **You** are responsible for being eligible. |
| React, React DOM | npm | MIT |
| Blender 5.3.0 (amd64 only) | downloaded at image build from download.blender.org, checked against a SHA-256 | GPL-3.0-or-later |
| Chromium, ffmpeg | Debian packages | various open-source licenses, see the Debian packages |
| Python 3.12, Node.js 22 | official Docker images | PSF / MIT |
| `mcp`, `httpx`, `uvicorn` | PyPI | MIT / BSD |

Each package's full license text is in the installed package (`/opt/render/node_modules/*`,
`pip show -f`). Services the tools call (Groq, Pexels, Unsplash) have their own terms; stock
photos require attribution, which the `stock_image` result provides.
