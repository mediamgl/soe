const path = require('path');
const { getLoaders, loaderByName } = require('@craco/craco');

module.exports = {
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    configure: (webpackConfig) => {
      // Inject Tailwind + Autoprefixer into every postcss-loader instance
      const { hasFoundAny, matches } = getLoaders(
        webpackConfig,
        loaderByName('postcss-loader')
      );
      if (hasFoundAny) {
        matches.forEach(({ loader }) => {
          if (!loader.options) loader.options = {};
          const prev = loader.options.postcssOptions;
          const prevPlugins =
            typeof prev === 'function'
              ? (prev().plugins || [])
              : (prev && prev.plugins) || [];
          loader.options.postcssOptions = () => ({
            ident: 'postcss',
            plugins: [
              ...(Array.isArray(prevPlugins) ? prevPlugins : []),
              require('tailwindcss'),
              require('autoprefixer'),
            ],
          });
        });
      }
      return webpackConfig;
    },
  },
};
