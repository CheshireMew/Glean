# Third-party notices

News reports, headlines, images, market data, model output, and material retrieved from external APIs remain subject to their publishers' and providers' terms.

Software dependencies remain under the licenses shipped with those dependencies. The AGPL license for Glean does not replace those notices.

The native WeChat public-account adapter was independently implemented against the public-platform web workflow, with protocol and login-selector references from [WeRSS / we-mp-rss](https://github.com/rachelos/we-mp-rss) (MIT). It does not bundle or require a running WeRSS instance. WeChat's web endpoints are not a guaranteed official RSS API.

The main runtime dependencies are FastAPI, Uvicorn, Playwright, Beautiful Soup, lxml, OpenAI's Python SDK, HTTPX, PyJWT, python-dotenv and python-multipart. The frontend directly uses React, React DOM, React Router, Vite, Ant Design, Axios, Day.js, Phosphor Icons and React Icons. Test and lint tools include Ruff, Vitest, Testing Library and ESLint. Exact versions are recorded in `requirements.lock`, `requirements-dev.lock` and `frontend/package-lock.json`; those lock files do not change the dependencies' own licenses.

Site names, trademarks, headlines, article text and links collected by source adapters belong to their respective owners. Telegram and configured AI providers are external services governed by their own terms. No third-party content is relicensed by Glean.
