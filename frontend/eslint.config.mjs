import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";
import tseslint from "typescript-eslint";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
    baseDirectory: __dirname,
});

// The @typescript-eslint plugin is registered explicitly so that the
// `// eslint-disable-next-line @typescript-eslint/no-explicit-any`
// directives scattered through the codebase resolve to a real rule.
// Without it, `next build` errors on every such directive with
// "Definition for rule ... was not found" — only surfaced on prod
// build, not dev / `tsc --noEmit`, which is how this hid for a while.
//
// The rule itself is set to "warn": widget-config and integration
// surfaces use `any` deliberately and already carry line-level
// suppressions. Warn keeps the pattern visible in dev without
// failing builds.
const eslintConfig = [
    ...compat.extends("next/core-web-vitals"),
    {
        plugins: {
            "@typescript-eslint": tseslint.plugin,
        },
        rules: {
            "react/no-unescaped-entities": "off",
            "@next/next/no-img-element": "off",
            "@typescript-eslint/no-explicit-any": "warn",
        },
    },
];

export default eslintConfig;
