import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
    // 확장자 없는 import 가 남아 있는 .vue 파일로 붙지 않도록 명시합니다.
    extensions: ['.mjs', '.js', '.jsx', '.json'],
  },
  css: {
    modules: {
      // Vue 의 scoped 스타일을 그대로 옮기려고 CSS Modules 를 씁니다.
      // 원래 이름(.auth-page)과 camelCase(styles.authPage) 를 모두 쓸 수 있게 둡니다.
      localsConvention: 'camelCase',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
  },
})
