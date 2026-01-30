/// <reference types="vite/client" />

// Vite CSS module imports
declare module '*.css?inline' {
  const css: string;
  export default css;
}
