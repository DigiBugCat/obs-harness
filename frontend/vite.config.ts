import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  build: {
    outDir: '../static/js',
    emptyOutDir: true,
    lib: {
      entry: {
        'channel': resolve(__dirname, 'src/channel.ts'),
        'dashboard': resolve(__dirname, 'src/dashboard.ts'),
        'santa': resolve(__dirname, 'src/santa.ts'),
        'text-animator': resolve(__dirname, 'src/text-animator.ts'),
      },
      formats: ['es'],
    },
    rollupOptions: {
      output: {
        entryFileNames: '[name].js',
      },
    },
  },
});
