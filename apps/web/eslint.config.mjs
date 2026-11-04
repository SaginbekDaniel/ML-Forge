import next from "eslint-config-next";

const config = [...next, { ignores: [".next/**", ".next-e2e/**", "node_modules/**", "next-env.d.ts"] }];

export default config;
