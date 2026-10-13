import { fileURLToPath } from 'node:url'
import { join } from 'node:path'
const path = (value) => fileURLToPath(new URL(value, import.meta.url))
const frontendModules = process.env.LIFEMAP_FRONTEND_NODE_MODULES || path('../frontend/node_modules')
export default {
 oxc: { jsx: { runtime: 'automatic' } },
 server: { fs: { allow: [path('../'), frontendModules] } },
 resolve: { alias: { '@': path('./src'), 'react': join(frontendModules, 'react'), '@testing-library/react': join(frontendModules, '@testing-library/react'), '@testing-library/user-event': join(frontendModules, '@testing-library/user-event'), 'vitest': join(frontendModules, 'vitest') } },
 test: { environment: 'jsdom', include: ['tests/ux/*.test.jsx'], setupFiles: ['./tests/ux/setup.jsx'] }
}
