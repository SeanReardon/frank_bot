import { defineConfig } from 'vite';
import { resolve } from 'path';

const isLibraryBuild = process.env.VITE_BUILD_MODE === 'library';

export default defineConfig({
  esbuild: {
    target: 'es2020',
  },
  build: isLibraryBuild
    ? {
        // Library build for embedding (IIFE bundle)
        target: 'es2020',
        outDir: 'dist-lib',
        emptyOutDir: true,
        lib: {
          entry: resolve(__dirname, 'src/frank-bot-embed.ts'),
          name: 'FrankBotEmbed',
          fileName: () => 'bundle.js',
          formats: ['iife'],
        },
        rollupOptions: {
          output: {
            inlineDynamicImports: true,
          },
        },
      }
    : {
        // Dev build for local development preview (SPA)
        target: 'es2020',
        outDir: 'dist',
        sourcemap: false,
        rollupOptions: {
          input: {
            main: resolve(__dirname, 'index.html'),
          },
        },
      },
  server: {
    proxy: {
      '/api': {
        target: 'http://frank-bot:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
