import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {fileURLToPath} from 'node:url';
const folder=(path:string)=>fileURLToPath(new URL(path,import.meta.url));
export default defineConfig({
 root:folder('../mobile/offline/'),base:'./',plugins:[react()],
 publicDir:folder('../mobile/offline/public/'),
 resolve:{alias:{'react':folder('./node_modules/react'),'react-dom':folder('./node_modules/react-dom'),'lucide-react':folder('./node_modules/lucide-react')}},
 build:{outDir:folder('../mobile/web/'),emptyOutDir:true,chunkSizeWarningLimit:1500},
 server:{host:'127.0.0.1'}
});
