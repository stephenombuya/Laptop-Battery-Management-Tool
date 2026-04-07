/**
 * webpack.config.js — BatteryOS Electron Build Configuration
 * ===========================================================
 * Bundles the renderer-process scripts into a single output file.
 * The main process and preload are NOT bundled (they run in Node directly).
 *
 * Usage
 * -----
 *   npm run build       # production bundle
 *   NODE_ENV=development npx webpack --watch   # development watch mode
 */

"use strict";

const path = require("path");

const isDev = process.env.NODE_ENV === "development";

/** @type {import('webpack').Configuration} */
module.exports = {
  mode:   isDev ? "development" : "production",
  target: "electron-renderer",

  entry: {
    renderer: path.resolve(__dirname, "src", "renderer.js"),
  },

  output: {
    path:     path.resolve(__dirname, "dist"),
    filename: "[name].bundle.js",
    clean:    true,
  },

  // Source maps only in development — keeps production builds lean
  devtool: isDev ? "eval-source-map" : false,

  resolve: {
    extensions: [".js"],
  },

  module: {
    rules: [
      {
        // Transpile modern JS for Electron's Chromium version
        test:    /\.js$/,
        exclude: /node_modules/,
        use:     {
          loader: "babel-loader",
          options: {
            presets: [
              ["@babel/preset-env", { targets: { electron: "30" } }],
            ],
          },
        },
      },
      {
        // Inline CSS files imported from JS (if any)
        test: /\.css$/,
        use:  ["style-loader", "css-loader"],
      },
    ],
  },

  optimization: {
    // Split vendor chunks for faster incremental rebuilds in dev
    splitChunks: isDev
      ? { chunks: "all" }
      : false,
  },

  performance: {
    // Silence size warnings in dev; enforce limits in production
    hints: isDev ? false : "warning",
    maxAssetSize:      512_000,
    maxEntrypointSize: 512_000,
  },
};
