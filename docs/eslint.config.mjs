import tseslint from "typescript-eslint";
import docusaurus from "@docusaurus/eslint-plugin";
import { flat, flatCodeBlocks } from "eslint-plugin-mdx";

export default [
  {
    ignores: ["build/**", ".docusaurus/**"],
  },
  ...tseslint.configs.recommended,
  flat,
  flatCodeBlocks,
  {
    plugins: {
      "@docusaurus": docusaurus,
    },
  },
];
