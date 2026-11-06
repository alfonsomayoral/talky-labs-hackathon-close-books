import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { LucideProvider } from 'lucide-react'
import { QueryClientProvider } from '@tanstack/react-query'
import { routes } from '@/app/routes'
import { Toaster } from '@/components'
import { queryClient } from '@/data'
import '@/design/fonts'
import '@/design/global.css'

const router = createBrowserRouter(routes)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LucideProvider size={16} strokeWidth={1.5}>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
      <Toaster />
    </LucideProvider>
  </StrictMode>,
)
