import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { writeFileSync } from 'fs'

// 构建版本号：使用时间戳的 base36 编码，短且唯一
const APP_VERSION = Date.now().toString(36)

export default defineConfig({
  base: process.env.VITE_PUBLIC_BASE || '/',
  plugins: [
    vue(),
    {
      name: 'generate-version-json',
      writeBundle() {
        // 构建完成后在 dist/ 目录生成 version.json
        const versionInfo = {
          version: APP_VERSION,
          buildTime: new Date().toISOString(),
        }
        writeFileSync(
          resolve(__dirname, 'dist', 'version.json'),
          JSON.stringify(versionInfo),
        )
        console.log(`\n📦 version.json generated: ${APP_VERSION}\n`)
      },
    },
  ],
  define: {
    __APP_VERSION__: JSON.stringify(APP_VERSION),
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/labtrace-api': {
        target: 'http://localhost:11314',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:11314',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:11314',
        ws: true,
      },
      '/health': {
        target: 'http://localhost:11314',
        changeOrigin: true,
      },
    },
  },
})
