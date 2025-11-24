document.addEventListener('DOMContentLoaded', function() {
    document.documentElement.classList.remove('sidebar-collapsed-initial');
});

document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('toggle-sidebar-btn');
    const logoImage = document.getElementById('logo-image');


    // 1. Check LocalStorage for saved state (default to 'expanded' if not set)
    const storedState = localStorage.getItem('sidebarState');
    let isExpanded = storedState !== 'collapsed'; // Default to true (expanded) if null or not 'collapsed'

    // 2. Helper function to apply the visual state
    const applyState = (expanded) => {
        if (expanded) {
            sidebar.classList.remove('collapsed');
            sidebar.style.width = '250px';

            // Expand logo
           toggleBtn.classList.remove('w-16', 'h-16');
            toggleBtn.classList.add('w-28', 'h-28');
        } else {
            sidebar.classList.add('collapsed');
            sidebar.style.width = '100px';

            // Shrink logo
            toggleBtn.classList.remove('w-28', 'h-28');
            toggleBtn.classList.add('w-16', 'h-16');
        }
    };

    //  Apply state immediately on page load
    applyState(isExpanded);

    //  Handle Toggle Click
    toggleBtn.addEventListener('click', () => {
        isExpanded = !isExpanded;

        // Save new state to browser storage
        localStorage.setItem('sidebarState', isExpanded ? 'expanded' : 'collapsed');
        applyState(isExpanded);
    });

    //  Theme Management for Logo Images
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
            this.updateLogoImage();
        }

        getStoredTheme() {
            return localStorage.getItem('theme') || 'dark';
        }

        applyTheme(theme) {
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('theme', theme);
            this.theme = theme;

            this.updateSidebarIcons();
            this.updateLogoImage();

            window.dispatchEvent(new CustomEvent('themeChange', { detail: { theme } }));
        }

        setupSidebarToggle() {
            const sidebarThemeToggle = document.getElementById('sidebar-theme-toggle');
            if (sidebarThemeToggle) {
                // Remove any existing event listeners
                const newToggle = sidebarThemeToggle.cloneNode(true);
                sidebarThemeToggle.parentNode.replaceChild(newToggle, sidebarThemeToggle);

                // Add fresh event listener
                document.getElementById('sidebar-theme-toggle').addEventListener('click', () => this.toggleTheme());
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

        updateLogoImage() {
            if (logoImage) {
                const logoPath = this.theme === 'dark'
                    ? "/static/images/darkLogo.png"
                    : "/static/images/lightLogo.png";

                logoImage.src = logoPath;
            }
        }

        toggleTheme() {
            const newTheme = this.theme === 'dark' ? 'light' : 'dark';
            this.applyTheme(newTheme);
        }

        addEventListeners() {
            window.addEventListener('themeChange', (event) => {
                this.theme = event.detail.theme;
                this.updateSidebarIcons();
                this.updateLogoImage();
            });
        }
    }

    // Initialize theme manager
    new ThemeManager();
});