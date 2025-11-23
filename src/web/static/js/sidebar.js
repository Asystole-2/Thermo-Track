// static/js/sidebar.js

document.addEventListener('DOMContentLoaded', () => {
    const sidebar      = document.getElementById('sidebar');
    const toggleBtn    = document.getElementById('toggle-sidebar-btn');
    const collapseIcon = document.getElementById('collapse-icon');

    if (!sidebar || !toggleBtn) return;

    const STORAGE_KEY = 'sidebarExpanded';

    // Last saved state (default = expanded)
    let isExpanded = localStorage.getItem(STORAGE_KEY);
    if (isExpanded === null) {
        isExpanded = true;
    } else {
        isExpanded = isExpanded === '1';
    }

    function applyState() {

        // Add or remove the collapsed class
        if (isExpanded) {
            sidebar.classList.remove('sidebar-collapsed');
        } else {
            sidebar.classList.add('sidebar-collapsed');
        }

        // Rotate icon
        if (collapseIcon) {
            collapseIcon.style.transform = isExpanded
                ? 'rotate(0deg)'
                : 'rotate(180deg)';
        }
    }

    // Toggle click
    toggleBtn.addEventListener('click', () => {
        isExpanded = !isExpanded;
        localStorage.setItem(STORAGE_KEY, isExpanded ? '1' : '0');
        applyState();
    });

    // Initial load
    applyState();
});
