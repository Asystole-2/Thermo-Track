// static/js/sidebar.js

document.addEventListener('DOMContentLoaded', () => {
    const sidebar      = document.getElementById('sidebar');
    const toggleBtn    = document.getElementById('toggle-sidebar-btn');
    const collapseIcon = document.getElementById('collapse-icon');

    const linkTexts        = document.querySelectorAll('.link-text');
    const userGreeting     = document.getElementById('user-greeting');
    const authLinksContainer = document.getElementById('auth-links');

    // If there's no sidebar on this page, bail out quietly
    if (!sidebar || !toggleBtn) return;

    const STORAGE_KEY     = 'sidebarExpanded';
    const EXPANDED_WIDTH  = '250px';
    const COLLAPSED_WIDTH = '80px';

    // Elements whose text we hide when collapsed
    const collapsibleEls = [];
    linkTexts.forEach(el => collapsibleEls.push(el));
    if (userGreeting) collapsibleEls.push(userGreeting);
    if (authLinksContainer) {
        authLinksContainer.querySelectorAll('a').forEach(a => collapsibleEls.push(a));
    }

    // Read last state from localStorage; default = expanded
    const stored = localStorage.getItem(STORAGE_KEY);
    let isExpanded = (stored === null || stored === '1');

    function applyState() {
        // Width of sidebar
        sidebar.style.width = isExpanded ? EXPANDED_WIDTH : COLLAPSED_WIDTH;

        // Arrow rotation (if present)
        if (collapseIcon) {
            collapseIcon.style.transform = isExpanded ? 'rotate(0deg)' : 'rotate(180deg)';
        }

        // Hide/show all text bits (menu labels, greeting, auth links)
        collapsibleEls.forEach(el => {
            if (!el) return;
            if (isExpanded) {
                el.style.opacity    = '1';
                el.style.visibility = 'visible';
            } else {
                el.style.opacity    = '0';
                el.style.visibility = 'hidden';
            }
        });

        // We let your CSS handle centering etc when width is 80px
        // via the #sidebar[style*="80px"] rules in main.css
    }

    // Toggle click
    toggleBtn.addEventListener('click', () => {
        isExpanded = !isExpanded;
        localStorage.setItem(STORAGE_KEY, isExpanded ? '1' : '0');
        applyState();
    });

    // Apply stored state on first load
    applyState();
});
