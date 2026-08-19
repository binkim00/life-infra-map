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
    // 프런트엔드 소스에서 사용하는 모듈 확장자만 명시합니다.
    extensions: ['.mjs', '.js', '.jsx', '.json'],
  },
  css: {
    modules: {
      // 컴포넌트별 스타일 격리를 위해 CSS Modules를 씁니다.
      // 원래 이름(.auth-page)과 camelCase(styles.authPage) 를 모두 쓸 수 있게 둡니다.
      localsConvention: 'camelCase',
    },
  },
  build: {
    rollupOptions: {
      input: {
        app: fileURLToPath(new URL('./index.html', import.meta.url)),
        kakaoMap: fileURLToPath(
          new URL('./kakao-map-embed.html', import.meta.url),
        ),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
  },
})
