import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import svelte from 'eslint-plugin-svelte';
import globals from 'globals';

const noRawFetch = {
	selector: "CallExpression[callee.name='fetch']",
	message:
		'Raw fetch() is forbidden outside lib/api/. Use the engineApi wrapper from lib/api/engine.ts instead.'
};

export default tseslint.config(
	{
		ignores: [
			'build/',
			'.svelte-kit/',
			'dist/',
			'src-tauri/',
			'static/',
			'vite.config.ts.timestamp-*',
			'svelte.config.js'
		]
	},
	js.configs.recommended,
	...tseslint.configs.recommended,
	...svelte.configs.recommended,
	{
		languageOptions: {
			globals: {
				...globals.browser,
				...globals.node
			}
		}
	},
	{
		files: ['**/*.svelte'],
		languageOptions: {
			parserOptions: {
				parser: tseslint.parser
			}
		}
	},
	{
		files: ['src/**/*.{ts,js,svelte}'],
		rules: {
			'no-restricted-syntax': ['error', noRawFetch]
		}
	},
	{
		files: ['src/lib/api/**/*.{ts,js,svelte}'],
		rules: {
			'no-restricted-syntax': 'off'
		}
	},
	{
		files: ['**/*.test.ts', '**/*.config.{js,ts}'],
		languageOptions: {
			globals: {
				...globals.node
			}
		}
	}
);
