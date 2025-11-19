class ThemeManager {
    constructor() {
        this.theme = this.getStoredTheme() || 'dark';
        this.init();
    }

    init() {
        this.applyTheme(this.theme);
        this.setupSidebarToggle();
        this.addEventListeners();
        this.updateSidebarIcons();

        this.revealContent();
    }

    getStoredTheme() {
        // Try localStorage first, then session, then default to dark
        return localStorage.getItem('theme') || 'dark';
    }

    applyTheme(theme) {
        // Apply to document
        document.documentElement.setAttribute('data-theme', theme);

        // Store in localStorage for persistence
        localStorage.setItem('theme', theme);
        this.theme = theme;

        // Update UI
        this.updateSidebarIcons();

        // Dispatch event for other components
        window.dispatchEvent(new CustomEvent('themeChange', { detail: { theme } }));
    }

    revealContent() {
        document.body.classList.remove('no-flash');
        setTimeout(() => {
            document.body.classList.add('content-loaded');
        }, 10);
    }

    setupSidebarToggle() {
        const sidebarThemeToggle = document.getElementById('sidebar-theme-toggle');
        if (sidebarThemeToggle) {
            // Remove any existing event listeners
            sidebarThemeToggle.replaceWith(sidebarThemeToggle.cloneNode(true));

            const freshToggle = document.getElementById('sidebar-theme-toggle');
            freshToggle.addEventListener('click', () => this.toggleTheme());
            freshToggle.setAttribute('aria-label', `Switch to ${this.theme === 'dark' ? 'light' : 'dark'} mode`);
        }
    }

    updateSidebarIcons() {
        const sidebarSunIcon = document.getElementById('sidebar-sun-icon');
        const sidebarMoonIcon = document.getElementById('sidebar-moon-icon');
        const sidebarThemeToggle = document.getElementById('sidebar-theme-toggle');

        if (sidebarSunIcon && sidebarMoonIcon) {
            const isDark = this.theme === 'dark';
            sidebarSunIcon.classList.toggle('hidden', !isDark);
            sidebarMoonIcon.classList.toggle('hidden', isDark);
        }

        if (sidebarThemeToggle) {
            sidebarThemeToggle.setAttribute('aria-label', `Switch to ${this.theme === 'dark' ? 'light' : 'dark'} mode`);
            sidebarThemeToggle.setAttribute('title', `Switch to ${this.theme === 'dark' ? 'light' : 'dark'} mode`);
        }
    }

    toggleTheme() {
        const newTheme = this.theme === 'dark' ? 'light' : 'dark';
        this.applyTheme(newTheme);

        // Update settings page buttons if they exist
        if (typeof updateThemeButtons === 'function') {
            updateThemeButtons(newTheme);
        }
    }

    addEventListeners() {
        window.addEventListener('themeChange', (event) => {
            this.theme = event.detail.theme;
            this.updateSidebarIcons();

            // Update settings page buttons if they exist
            if (typeof updateThemeButtons === 'function') {
                updateThemeButtons(this.theme);
            }
        });
    }
}

// Initialize theme manager immediately
new ThemeManager();

// Export for use in other modules
window.ThemeManager = ThemeManager;