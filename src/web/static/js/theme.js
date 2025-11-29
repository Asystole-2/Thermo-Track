// static/js/theme.js

document.addEventListener('DOMContentLoaded', () => {
    const root = document.documentElement;          // <html>
    const body = document.body;
    const THEME_KEY = 'tt-theme';

    // Sidebar-specific elements
    const sidebarToggle = document.getElementById('sidebar-theme-toggle');
    const logoLight     = document.getElementById('logo-light');
    const logoDark      = document.getElementById('logo-dark');
    const sunIcon       = document.getElementById('sidebar-sun-icon');
    const moonIcon      = document.getElementById('sidebar-moon-icon');

    function getInitialTheme() {
        // 1. Stored preference
        const stored = localStorage.getItem(THEME_KEY);
        if (stored === 'light' || stored === 'dark') return stored;

        // 2. Attribute on <html>
        const attrTheme = root.getAttribute('data-theme');
        if (attrTheme === 'light' || attrTheme === 'dark') return attrTheme;

        // 3. System preference
        if (window.matchMedia &&
            window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return 'dark';
        }

        return 'light';
    }

    function updateLogoAndIcons(theme) {
        // swap sidebar logos
        if (logoLight && logoDark) {
            if (theme === 'dark') {
                logoLight.classList.add('hidden');
                logoDark.classList.remove('hidden');
            } else {
                logoDark.classList.add('hidden');
                logoLight.classList.remove('hidden');
            }
        }

        // swap sun / moon icons
        if (sunIcon && moonIcon) {
            if (theme === 'dark') {
                sunIcon.classList.remove('hidden');
                moonIcon.classList.add('hidden');
            } else {
                sunIcon.classList.add('hidden');
                moonIcon.classList.remove('hidden');
            }
        }
    }

    function applyTheme(theme) {
        if (theme !== 'light' && theme !== 'dark') {
            theme = 'light';
        }

        root.setAttribute('data-theme', theme);
        localStorage.setItem(THEME_KEY, theme);

        // Let the browser know both schemes are supported
        const colorMeta = document.querySelector('meta[name="color-scheme"]');
        if (colorMeta) {
            colorMeta.setAttribute('content', 'light dark');
        }

        updateLogoAndIcons(theme);
    }

    // ---- Initial setup ----
    const initialTheme = getInitialTheme();
    applyTheme(initialTheme);

    // Remove "no-flash" class and enable transitions
    body.classList.remove('no-flash');
    body.classList.add('content-loaded');

    // ---- Sidebar toggle button ----
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', () => {
            const current = root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
            const next = current === 'dark' ? 'light' : 'dark';
            applyTheme(next);
        });
    }
});
