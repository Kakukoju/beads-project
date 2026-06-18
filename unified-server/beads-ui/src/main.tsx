import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import BeadsOpsUI from './BeadsOpsUI'   // ← 換成 BeadsOpsUI

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BeadsOpsUI />
  </StrictMode>,
)
