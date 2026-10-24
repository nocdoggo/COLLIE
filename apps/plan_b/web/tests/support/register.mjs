// Registers the test-only TypeScript/JSX hooks (see ts-loader.mjs) before any test file loads.
import { register } from "node:module";

register("./ts-loader.mjs", import.meta.url);
