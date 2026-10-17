import '@mantine/core/styles.css'
import '@fontsource/ibm-plex-sans-arabic/400.css'
import '@fontsource/ibm-plex-sans-arabic/500.css'
import '@fontsource/ibm-plex-sans-arabic/700.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { DirectionProvider, MantineProvider, createTheme } from '@mantine/core'
import App from './App'

const font = '"IBM Plex Sans Arabic", system-ui, sans-serif'
const theme = createTheme({
  primaryColor: 'teal',
  defaultRadius: 'md',
  fontFamily: font,
  headings: { fontFamily: font },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <DirectionProvider>
      <MantineProvider theme={theme} defaultColorScheme="auto">
        <App />
      </MantineProvider>
    </DirectionProvider>
  </StrictMode>,
)
