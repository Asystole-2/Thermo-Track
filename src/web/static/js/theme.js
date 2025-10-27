class ThemeManager {
    constructor() {
        // Get theme that was already set by the critical CSS
        this.theme = document.documentElement.getAttribute('data-theme') || 'dark';
        this.init();
    }

    init() {
        // Theme is already applied by critical CSS, just sync the UI
        this.setupSidebarToggle();
        this.addEventListeners();
        this.updateSidebarIcons();

        // Show content now that everything is synced
        this.revealContent();
    }

    getStoredTheme() {
        return localStorage.getItem('theme');
    }

    applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        this.theme = theme;

        // Update sidebar icons
        this.updateSidebarIcons();

        // Dispatch custom event for other components to listen to
        window.dispatchEvent(new CustomEvent('themeChange', { detail: { theme } }));
    }

    revealContent() {
        // Remove no-flash and add content-loaded for smooth appearance
        document.body.classList.remove('no-flash');
        setTimeout(() => {
            document.body.classList.add('content-loaded');
        }, 10);
    }

    setupSidebarToggle() {
        const sidebarThemeToggle = document.getElementById('sidebar-theme-toggle');
        if (sidebarThemeToggle) {
            // Remove any existing event listeners to prevent duplicates
            sidebarThemeToggle.replaceWith(sidebarThemeToggle.cloneNode(true));

            // Get the fresh reference
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
    }

    addEventListeners() {
        // Listen for theme changes from other components
        window.addEventListener('themeChange', (event) => {
            this.theme = event.detail.theme;
            this.updateSidebarIcons();
        });
    }
}

// Initialize theme manager immediately
new ThemeManager();

// Export for use in other modules
window.ThemeManager = ThemeManager;