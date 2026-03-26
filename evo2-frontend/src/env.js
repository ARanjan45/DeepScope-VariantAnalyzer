import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

export const env = createEnv({
  server: {
    BACKEND_URL: z.string().url(),
    NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  },
  client: {
    // This is only used as fallback reference, actual calls go through /api/analyze
    NEXT_PUBLIC_ANALYZE_SINGLE_VARIANT_BASE_URL: z.string().default("/api/analyze"),
  },
  runtimeEnv: {
    BACKEND_URL: process.env.BACKEND_URL,
    NODE_ENV: process.env.NODE_ENV,
    NEXT_PUBLIC_ANALYZE_SINGLE_VARIANT_BASE_URL: process.env.NEXT_PUBLIC_ANALYZE_SINGLE_VARIANT_BASE_URL,
  },
  skipValidation: !!process.env.SKIP_ENV_VALIDATION,
  emptyStringAsUndefined: true,
});