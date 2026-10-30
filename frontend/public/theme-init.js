(() => {
        let preference = 'system'
        try { preference = localStorage.getItem('mycollab-theme') || 'system' } catch {}
        const dark = preference === 'dark' || (preference !== 'light' && preference !== 'dark' && window.matchMedia?.('(prefers-color-scheme: dark)').matches)
        document.documentElement.classList.toggle('dark', !!dark)
        document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
      })()
