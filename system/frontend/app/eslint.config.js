export default [
  {
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      "no-restricted-imports": ["error", {
        patterns: [
          { group: ["**/api", "**/api.js"], message: "Import from sdk instead: import sdk from './sdk'" },
        ],
      }],
      "no-restricted-syntax": ["warn",
        { selector: "CallExpression[callee.name='fetch']", message: "Use sdk methods instead of raw fetch()." },
      ],
    },
  },
  {
    files: ["src/sdk/**/*.js"],
    rules: { "no-restricted-syntax": "off" },
  },
  {
    files: ["**/*.test.*", "**/test/**"],
    rules: { "no-restricted-syntax": "off", "no-restricted-imports": "off" },
  },
];
